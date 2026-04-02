"""GWT tests for scrape queue repository -- task lifecycle, dependencies, recovery."""

import pytest

from db.connection import get_memory_connection
from db.schema import init_schema
from services.items.repository import get_or_create_item
from services.scrape_queue.models import TaskStatus, TaskType
from services.scrape_queue.repository import (
    claim_next,
    complete_task,
    create_task,
    create_tasks_for_set,
    fail_task,
    force_fail_by_worker,
    force_fail_task,
    get_queue_stats,
    get_tasks_for_set,
    re_evaluate_blocked,
    reclaim_stale,
)


@pytest.fixture
def conn():
    """In-memory DuckDB with schema initialized."""
    c = get_memory_connection()
    init_schema(c)
    yield c
    c.close()


def _get_task_status(conn, task_id: str) -> str:
    """Helper: read task status from DB."""
    row = conn.execute(
        "SELECT status FROM scrape_tasks WHERE task_id = ?", [task_id]
    ).fetchone()
    return row[0] if row else None


def _set_task_status(conn, task_id: str, status: str) -> None:
    """Helper: directly set task status in DB."""
    conn.execute(
        "UPDATE scrape_tasks SET status = ? WHERE task_id = ?",
        [status, task_id],
    )


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_given_empty_queue_when_create_task_then_pending(self, conn):
        """Given empty queue, when creating a task without dependency,
        then task status is pending."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        assert task is not None
        assert task.set_number == "75192"
        assert task.task_type == TaskType.BRICKLINK_METADATA
        assert task.status == TaskStatus.PENDING

    def test_given_empty_queue_when_create_task_with_dependency_then_blocked(
        self, conn
    ):
        """Given empty queue, when creating a task that depends on another type,
        then task status is blocked."""
        task = create_task(conn, "75192", TaskType.MINIFIGURES)

        assert task is not None
        assert task.status == TaskStatus.BLOCKED
        assert task.depends_on == TaskType.BRICKLINK_METADATA.value

    def test_given_existing_active_task_when_create_duplicate_then_returns_none(
        self, conn
    ):
        """Given an active (pending) task exists, when creating a duplicate
        for the same set_number + task_type, then returns None."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        duplicate = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        assert duplicate is None

    def test_given_completed_task_when_create_same_type_then_creates_new(
        self, conn
    ):
        """Given a completed task, when creating the same type for the same set,
        then a new task is created (not deduplicated)."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        _set_task_status(conn, task.task_id, "completed")

        new_task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        assert new_task is not None
        assert new_task.task_id != task.task_id


# ---------------------------------------------------------------------------
# create_tasks_for_set
# ---------------------------------------------------------------------------


class TestCreateTasksForSet:
    def test_given_set_number_when_create_tasks_for_set_then_all_types_created(
        self, conn
    ):
        """Given a set_number, when creating all tasks, then one task per
        TaskType is created."""
        tasks = create_tasks_for_set(conn, "75192")

        created_types = {t.task_type for t in tasks}
        assert created_types == set(TaskType)
        assert len(tasks) == len(TaskType)

    def test_given_partial_existing_when_create_tasks_for_set_then_only_missing_created(
        self, conn
    ):
        """Given some task types already exist for a set, when creating all
        tasks, then only missing types are created."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        tasks = create_tasks_for_set(conn, "75192")

        created_types = {t.task_type for t in tasks}
        assert TaskType.BRICKLINK_METADATA not in created_types
        assert len(tasks) == len(TaskType) - 1


# ---------------------------------------------------------------------------
# claim_next
# ---------------------------------------------------------------------------


class TestClaimNext:
    def test_given_pending_task_when_claim_next_then_running_with_worker_id(
        self, conn
    ):
        """Given a pending task, when claiming it, then status becomes running
        and locked_by is set to worker_id."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        claimed = claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        assert claimed is not None
        assert claimed.status == TaskStatus.RUNNING
        assert claimed.locked_by == "worker-1"
        assert claimed.started_at is not None

    def test_given_empty_queue_when_claim_next_then_returns_none(self, conn):
        """Given no pending tasks, when claiming, then returns None."""
        claimed = claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        assert claimed is None

    def test_given_multiple_pending_when_claim_next_with_type_then_only_that_type(
        self, conn
    ):
        """Given pending tasks of different types, when claiming with a specific
        type filter, then only that type is returned."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        create_task(conn, "75192", TaskType.BRICKECONOMY)

        claimed = claim_next(conn, "worker-1", TaskType.BRICKECONOMY)

        assert claimed is not None
        assert claimed.task_type == TaskType.BRICKECONOMY

    def test_given_pending_task_when_claim_next_then_attempt_count_incremented(
        self, conn
    ):
        """Given a pending task with attempt_count=0, when claimed,
        then attempt_count is incremented to 1."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        claimed = claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        assert claimed.attempt_count == 1


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------


class TestCompleteTask:
    def test_given_running_task_when_complete_then_status_completed(self, conn):
        """Given a running task, when completed, then status is completed
        and completed_at is set."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        complete_task(conn, task.task_id)

        assert _get_task_status(conn, task.task_id) == "completed"

    def test_given_completed_bricklink_when_dependent_minifigs_blocked_then_unblocked(
        self, conn
    ):
        """Given a blocked minifigures task depending on bricklink_metadata,
        when bricklink completes, then minifigures is unblocked to pending."""
        # Create a lego_items row with minifig_count > 0 so it doesn't auto-complete
        get_or_create_item(conn, "75192", title="Falcon", minifig_count=4)
        bl_task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        mf_task = create_task(conn, "75192", TaskType.MINIFIGURES)
        assert mf_task.status == TaskStatus.BLOCKED

        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)
        complete_task(conn, bl_task.task_id)

        assert _get_task_status(conn, mf_task.task_id) == "pending"

    def test_given_completed_bricklink_when_minifig_count_zero_then_minifigs_auto_completed(
        self, conn
    ):
        """Given a set with minifig_count=0, when bricklink completes,
        then the minifigures task is auto-completed (skipped)."""
        get_or_create_item(conn, "75192", title="Falcon", minifig_count=0)
        bl_task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        mf_task = create_task(conn, "75192", TaskType.MINIFIGURES)

        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)
        complete_task(conn, bl_task.task_id)

        assert _get_task_status(conn, mf_task.task_id) == "completed"

    def test_given_completed_bricklink_when_no_title_then_google_trends_auto_completed(
        self, conn
    ):
        """Given a set with no title, when bricklink completes,
        then google_trends task is auto-completed (skipped)."""
        # No title or year_released means google_trends is skippable
        get_or_create_item(conn, "75192")
        bl_task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        gt_task = create_task(conn, "75192", TaskType.GOOGLE_TRENDS)

        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)
        complete_task(conn, bl_task.task_id)

        assert _get_task_status(conn, gt_task.task_id) == "completed"


# ---------------------------------------------------------------------------
# fail_task / force_fail_task
# ---------------------------------------------------------------------------


class TestFailTask:
    def test_given_running_task_under_max_attempts_when_fail_then_back_to_pending(
        self, conn
    ):
        """Given a running task with attempts < max, when failed,
        then status goes back to pending for retry."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claimed = claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        fail_task(conn, claimed.task_id, "network error")

        assert _get_task_status(conn, claimed.task_id) == "pending"

    def test_given_running_task_at_max_attempts_when_fail_then_status_failed(
        self, conn
    ):
        """Given a running task that has exhausted all attempts, when failed,
        then status becomes failed permanently."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        # Exhaust attempts by claiming and failing repeatedly
        max_attempts = conn.execute(
            "SELECT max_attempts FROM scrape_tasks WHERE task_id = ?",
            [task.task_id],
        ).fetchone()[0]

        for _ in range(max_attempts):
            claimed = claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)
            if claimed:
                fail_task(conn, claimed.task_id, "network error")

        assert _get_task_status(conn, task.task_id) == "failed"

    def test_given_running_task_when_force_fail_then_immediately_failed(
        self, conn
    ):
        """Given a running task, when force-failed, then status is failed
        regardless of remaining attempts."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        force_fail_task(conn, task.task_id, "Executor timed out")

        assert _get_task_status(conn, task.task_id) == "failed"
        row = conn.execute(
            "SELECT error FROM scrape_tasks WHERE task_id = ?",
            [task.task_id],
        ).fetchone()
        assert row[0] == "Executor timed out"

    def test_given_running_task_when_force_fail_by_worker_then_failed(
        self, conn
    ):
        """Given a running task locked by a worker, when force_fail_by_worker
        is called with that worker_id and task_type, then the task is failed."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        force_fail_by_worker(
            conn, "worker-1", TaskType.BRICKLINK_METADATA.value, "timed out"
        )

        assert _get_task_status(conn, task.task_id) == "failed"
        row = conn.execute(
            "SELECT error FROM scrape_tasks WHERE task_id = ?",
            [task.task_id],
        ).fetchone()
        assert row[0] == "timed out"


# ---------------------------------------------------------------------------
# reclaim_stale
# ---------------------------------------------------------------------------


class TestReclaimStale:
    def test_given_stale_running_task_when_reclaim_then_back_to_pending(
        self, conn
    ):
        """Given a task running for longer than stale_minutes, when reclaiming,
        then task is reset to pending."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        # Backdate the locked_at to make it stale
        conn.execute(
            """UPDATE scrape_tasks
               SET locked_at = CURRENT_TIMESTAMP - INTERVAL '60 minutes'
               WHERE task_id = ?""",
            [task.task_id],
        )

        reclaimed = reclaim_stale(conn, stale_minutes=30)

        assert reclaimed == 1
        assert _get_task_status(conn, task.task_id) == "pending"

    def test_given_fresh_running_task_when_reclaim_then_still_running(
        self, conn
    ):
        """Given a task that just started running, when reclaiming,
        then task remains running (not stale yet)."""
        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        reclaimed = reclaim_stale(conn, stale_minutes=30)

        assert reclaimed == 0
        assert _get_task_status(conn, task.task_id) == "running"


# ---------------------------------------------------------------------------
# re_evaluate_blocked
# ---------------------------------------------------------------------------


class TestReEvaluateBlocked:
    def test_given_blocked_task_with_completed_dep_when_re_evaluate_then_unblocked(
        self, conn
    ):
        """Given a blocked task whose dependency has already completed,
        when re-evaluating on startup, then it becomes pending."""
        get_or_create_item(conn, "75192", title="Falcon", minifig_count=4)
        bl_task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        mf_task = create_task(conn, "75192", TaskType.MINIFIGURES)
        assert mf_task.status == TaskStatus.BLOCKED

        # Complete the dependency manually
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)
        # Manually set completed without triggering _unblock_dependents
        conn.execute(
            "UPDATE scrape_tasks SET status = 'completed' WHERE task_id = ?",
            [bl_task.task_id],
        )

        unblocked = re_evaluate_blocked(conn)

        assert unblocked >= 1
        assert _get_task_status(conn, mf_task.task_id) == "pending"

    def test_given_blocked_task_with_pending_dep_when_re_evaluate_then_still_blocked(
        self, conn
    ):
        """Given a blocked task whose dependency is still pending,
        when re-evaluating, then it stays blocked."""
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        mf_task = create_task(conn, "75192", TaskType.MINIFIGURES)

        unblocked = re_evaluate_blocked(conn)

        # The BL task is pending (not completed), so minifigs stays blocked
        assert _get_task_status(conn, mf_task.task_id) == "blocked"


# ---------------------------------------------------------------------------
# get_queue_stats
# ---------------------------------------------------------------------------


class TestGetQueueStats:
    def test_given_mixed_statuses_when_get_stats_then_correct_counts(
        self, conn
    ):
        """Given tasks in various statuses, when getting stats,
        then counts are accurate per status."""
        tasks = create_tasks_for_set(conn, "75192")

        # Claim and complete one
        bl = claim_next(conn, "w1", TaskType.BRICKLINK_METADATA)
        complete_task(conn, bl.task_id)

        # Claim and fail one
        be = claim_next(conn, "w2", TaskType.BRICKECONOMY)
        force_fail_task(conn, be.task_id, "error")

        stats = get_queue_stats(conn)

        assert stats.get("completed", 0) >= 1
        assert stats.get("failed", 0) >= 1
