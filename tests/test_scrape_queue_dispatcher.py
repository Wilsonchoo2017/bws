"""GWT tests for scrape queue dispatcher -- worker loops, timeouts, failures."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from db.connection import get_memory_connection
from db.schema import init_schema
from services.scrape_queue.models import ExecutorResult, TaskType, TaskTypeConfig
from services.scrape_queue.repository import claim_next, create_task


class _NoCloseConn:
    """Wrapper that delegates everything to the real conn but ignores close()."""

    def __init__(self, real_conn):
        self._real = real_conn

    def close(self):
        pass  # no-op

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def conn():
    """In-memory DuckDB with schema initialized."""
    c = get_memory_connection()
    init_schema(c)
    yield c
    c.close()


@pytest.fixture
def no_close_conn(conn):
    """Conn wrapper that ignores close() calls (safe for _claim_and_execute)."""
    return _NoCloseConn(conn)


def _get_task_status(conn, task_id: str) -> str:
    row = conn.execute(
        "SELECT status FROM scrape_tasks WHERE task_id = ?", [task_id]
    ).fetchone()
    return row[0] if row else None


def _make_test_config(
    task_type: TaskType = TaskType.BRICKLINK_METADATA,
    executor=None,
) -> TaskTypeConfig:
    """Create a TaskTypeConfig with a mock or real executor for testing."""
    return TaskTypeConfig(
        task_type=task_type,
        executor=executor or MagicMock(return_value=ExecutorResult.ok()),
        concurrency=1,
        timeout_seconds=300,
    )


# ---------------------------------------------------------------------------
# _claim_and_execute
# ---------------------------------------------------------------------------


class TestClaimAndExecute:
    def test_given_pending_task_when_executor_succeeds_then_task_completed(
        self, conn, no_close_conn
    ):
        """Given a pending BrickLink task, when the executor succeeds,
        then the task is marked completed."""
        import services.scrape_queue.dispatcher as dispatcher

        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        mock_executor = MagicMock(return_value=ExecutorResult.ok())
        cfg = _make_test_config(executor=mock_executor)

        with patch(
            "db.connection.get_connection", return_value=no_close_conn
        ), patch.object(
            dispatcher, "_schema_initialized", True
        ):
            result = dispatcher._claim_and_execute("worker-1", cfg)

        assert result is None  # None = task handled, no cooldown
        mock_executor.assert_called_once()
        assert _get_task_status(conn, task.task_id) == "completed"

    def test_given_pending_task_when_executor_raises_then_task_failed(
        self, conn, no_close_conn
    ):
        """Given a pending task, when the executor raises an exception,
        then the task is marked failed (or pending for retry)."""
        import services.scrape_queue.dispatcher as dispatcher

        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        mock_executor = MagicMock(side_effect=RuntimeError("browser crash"))
        cfg = _make_test_config(executor=mock_executor)

        with patch(
            "db.connection.get_connection", return_value=no_close_conn
        ), patch.object(
            dispatcher, "_schema_initialized", True
        ):
            result = dispatcher._claim_and_execute("worker-1", cfg)

        assert result is None
        status = _get_task_status(conn, task.task_id)
        # First attempt fails -> back to pending for retry
        assert status in ("pending", "failed")

    def test_given_empty_queue_when_claim_and_execute_then_returns_none(
        self, conn, no_close_conn
    ):
        """Given no pending tasks, when _claim_and_execute is called,
        then it returns None (nothing to do)."""
        import services.scrape_queue.dispatcher as dispatcher

        cfg = _make_test_config()

        with patch(
            "db.connection.get_connection", return_value=no_close_conn
        ), patch.object(
            dispatcher, "_schema_initialized", True
        ):
            result = dispatcher._claim_and_execute("worker-1", cfg)

        assert result is None

    def test_given_executor_returns_cooldown_then_task_requeued(
        self, conn, no_close_conn
    ):
        """Given an executor that returns a cooldown result, when processed,
        then the task is requeued and the cooldown seconds are returned."""
        import services.scrape_queue.dispatcher as dispatcher

        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        mock_executor = MagicMock(return_value=ExecutorResult.cooldown(3600))
        cfg = _make_test_config(executor=mock_executor)

        with patch(
            "db.connection.get_connection", return_value=no_close_conn
        ), patch.object(
            dispatcher, "_schema_initialized", True
        ):
            result = dispatcher._claim_and_execute("worker-1", cfg)

        assert result == 3600  # cooldown seconds
        assert _get_task_status(conn, task.task_id) == "pending"

    def test_given_executor_returns_failure_then_task_failed(
        self, conn, no_close_conn
    ):
        """Given an executor that returns a failure, when processed,
        then the task is marked pending (for retry) or failed."""
        import services.scrape_queue.dispatcher as dispatcher

        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        mock_executor = MagicMock(
            return_value=ExecutorResult.fail("No data returned")
        )
        cfg = _make_test_config(executor=mock_executor)

        with patch(
            "db.connection.get_connection", return_value=no_close_conn
        ), patch.object(
            dispatcher, "_schema_initialized", True
        ):
            result = dispatcher._claim_and_execute("worker-1", cfg)

        assert result is None
        status = _get_task_status(conn, task.task_id)
        assert status in ("pending", "failed")


# ---------------------------------------------------------------------------
# Worker loop: shutdown
# ---------------------------------------------------------------------------


class TestWorkerLoopShutdown:
    def test_given_shutdown_flag_when_worker_loop_then_exits(self):
        """Given the shutdown flag is set, when the worker loop checks it,
        then it exits without processing."""
        import services.scrape_queue.dispatcher as dispatcher

        cfg = _make_test_config()
        original = dispatcher._shutting_down
        dispatcher._shutting_down = True
        try:
            asyncio.run(dispatcher._worker_loop("worker-1", cfg))
        finally:
            dispatcher._shutting_down = original


# ---------------------------------------------------------------------------
# Timeout mechanism
# ---------------------------------------------------------------------------


class TestExecutorTimeout:
    def test_given_slow_executor_when_wait_for_timeout_then_timeout_raised(self):
        """Given an executor that blocks for 10s, when wrapped in
        asyncio.wait_for with 0.1s timeout, then TimeoutError is raised."""

        def slow_executor():
            time.sleep(10)

        async def _run():
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.to_thread(slow_executor), timeout=0.1
                )

        asyncio.run(_run())

    def test_given_running_task_when_fail_current_task_called_then_task_failed(
        self, conn
    ):
        """Given a running task locked by worker-1, when _fail_current_task
        is called, then the task is marked failed with timeout error."""
        import services.scrape_queue.dispatcher as dispatcher

        task = create_task(conn, "75192", TaskType.BRICKLINK_METADATA)
        claim_next(conn, "worker-1", TaskType.BRICKLINK_METADATA)

        cfg = _make_test_config()

        with patch(
            "db.connection.get_connection",
            return_value=_NoCloseConn(conn),
        ):
            dispatcher._fail_current_task("worker-1", cfg)

        assert _get_task_status(conn, task.task_id) == "failed"
        row = conn.execute(
            "SELECT error FROM scrape_tasks WHERE task_id = ?",
            [task.task_id],
        ).fetchone()
        assert row[0] == "Executor timed out"
