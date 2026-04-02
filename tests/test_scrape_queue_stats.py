"""GWT tests for scrape task to job response conversion and stats."""

from datetime import datetime, timezone

import pytest

from db.connection import get_memory_connection
from db.schema import init_schema
from api.schemas import JobStatus, ScrapeQueueStats
from services.scrape_queue.models import TaskType
from services.scrape_queue.repository import (
    claim_next,
    complete_task,
    create_task,
    fail_task,
    force_fail_task,
    get_queue_stats,
)


@pytest.fixture
def conn():
    """In-memory DuckDB with schema initialized."""
    c = get_memory_connection()
    init_schema(c)
    yield c
    c.close()


def _convert_tasks(conn, limit: int = 1000):
    """Call the private _scrape_tasks_as_jobs to get ScrapeJobResponse list."""
    from api.routes.scrape import _scrape_tasks_as_jobs

    return _scrape_tasks_as_jobs(conn, limit)


class TestScrapeTasksAsJobs:
    def test_given_pending_task_when_converted_then_status_queued(self, conn):
        """Given a pending task, when converted to job response,
        then status is mapped to QUEUED."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        jobs = _convert_tasks(conn)

        pending_jobs = [j for j in jobs if j.url == "75192" and j.scraper_id == "scrape:bricklink_metadata"]
        assert len(pending_jobs) >= 1
        assert pending_jobs[0].status == JobStatus.QUEUED

    def test_given_blocked_task_when_converted_then_status_queued(self, conn):
        """Given a blocked task, when converted to job response,
        then status is mapped to QUEUED (same as pending)."""
        create_task(conn, "75192", TaskType.MINIFIGURES)

        jobs = _convert_tasks(conn)

        mf_jobs = [j for j in jobs if j.scraper_id == "scrape:minifigures"]
        assert len(mf_jobs) >= 1
        assert mf_jobs[0].status == JobStatus.QUEUED

    def test_given_running_task_when_converted_then_status_running(self, conn):
        """Given a running task, when converted to job response,
        then status is RUNNING."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        jobs = _convert_tasks(conn)

        running_jobs = [j for j in jobs if j.status == JobStatus.RUNNING]
        assert len(running_jobs) == 1
        assert running_jobs[0].scraper_id == "scrape:bricklink_metadata"

    def test_given_completed_task_when_converted_then_items_found_1(self, conn):
        """Given a completed task without error, when converted,
        then items_found is 1."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)
        complete_task(conn, task.task_id)

        jobs = _convert_tasks(conn)

        completed_jobs = [j for j in jobs if j.status == JobStatus.COMPLETED]
        assert len(completed_jobs) >= 1
        assert completed_jobs[0].items_found == 1

    def test_given_running_task_when_converted_then_items_found_0(self, conn):
        """Given a running task, when converted, then items_found is 0."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        jobs = _convert_tasks(conn)

        running_jobs = [j for j in jobs if j.status == JobStatus.RUNNING]
        assert len(running_jobs) == 1
        assert running_jobs[0].items_found == 0

    def test_given_blocked_task_with_depends_on_when_converted_then_progress_shows_waiting(
        self, conn
    ):
        """Given a blocked task with a dependency, when converted,
        then the progress field shows 'waiting for <dep>'."""
        create_task(conn, "75192", TaskType.MINIFIGURES)

        jobs = _convert_tasks(conn)

        mf_jobs = [j for j in jobs if j.scraper_id == "scrape:minifigures"]
        assert len(mf_jobs) >= 1
        assert "waiting for" in (mf_jobs[0].progress or "")

    def test_given_task_with_retries_when_converted_then_progress_shows_attempt_count(
        self, conn
    ):
        """Given a task that has been retried, when converted,
        then the progress field shows 'attempt N/M'."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        # Claim and fail to increment attempt_count
        claimed = claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)
        fail_task(conn, claimed.task_id, "transient error")
        # Claim again (attempt 2)
        claimed2 = claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        jobs = _convert_tasks(conn)

        bl_jobs = [
            j for j in jobs
            if j.scraper_id == "scrape:bricklink_metadata" and j.url == "75192"
        ]
        assert len(bl_jobs) >= 1
        assert "attempt" in (bl_jobs[0].progress or "")


class TestQueueStatsAccuracy:
    def test_given_mixed_statuses_when_get_queue_stats_then_counts_all_tasks(
        self, conn
    ):
        """Given tasks in various statuses including completed, when stats are
        queried from DB, then all statuses are counted accurately regardless
        of any LIMIT on the jobs query."""
        from services.scrape_queue.repository import create_tasks_for_set

        # Create tasks for two sets (10 tasks total)
        create_tasks_for_set(conn, "75192")
        create_tasks_for_set(conn, "42151")

        # Complete some
        bl1 = claim_next(conn, "w1", TaskType.BRICKLINK_METADATA)
        complete_task(conn, bl1.task_id)
        bl2 = claim_next(conn, "w2", TaskType.BRICKLINK_METADATA)
        complete_task(conn, bl2.task_id)

        # Fail one
        be1 = claim_next(conn, "w3", TaskType.BRICKECONOMY)
        force_fail_task(conn, be1.task_id, "test error")

        raw_stats = get_queue_stats(conn)
        stats = ScrapeQueueStats(
            total=sum(raw_stats.values()),
            queued=raw_stats.get("pending", 0) + raw_stats.get("blocked", 0),
            running=raw_stats.get("running", 0),
            completed=raw_stats.get("completed", 0),
            failed=raw_stats.get("failed", 0),
        )

        assert stats.completed >= 2
        assert stats.failed >= 1
        assert stats.total == 10

    def test_given_completed_tasks_beyond_limit_when_jobs_limited_then_stats_still_accurate(
        self, conn
    ):
        """Given more completed tasks than the LIMIT, when _scrape_tasks_as_jobs
        is called with a small limit, completed tasks are truncated from the
        job list but get_queue_stats still counts them."""
        # Create 5 BrickLink tasks (no dependency, so they start as pending)
        for i in range(5):
            create_task(conn, f"set-{i}", TaskType.BRICKLINK_METADATA)

        # Complete all 5
        for _ in range(5):
            claimed = claim_next(conn, "w1", TaskType.BRICKLINK_METADATA)
            if claimed:
                complete_task(conn, claimed.task_id)

        # Jobs list with limit=3 will miss some completed tasks
        jobs = _convert_tasks(conn, limit=3)
        assert len(jobs) == 3

        # But DB stats show all 5 completed
        raw_stats = get_queue_stats(conn)
        assert raw_stats.get("completed", 0) == 5
