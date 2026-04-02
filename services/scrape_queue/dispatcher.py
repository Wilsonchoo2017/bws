"""Scrape task dispatcher -- one independent worker per data source.

Each task type (BrickLink, BrickEconomy, Keepa, etc.) gets its own
worker coroutine so all data sources make progress concurrently,
regardless of how many pending tasks other sources have.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from services.scrape_queue.executors import (
    execute_brickeconomy,
    execute_bricklink_metadata,
    execute_google_trends,
    execute_keepa,
    execute_minifigures,
    get_trends_cooldown_remaining,
)
from services.scrape_queue.models import TaskType
from services.scrape_queue.repository import (
    claim_next,
    complete_task,
    fail_task,
    force_fail_by_worker,
    force_fail_task,
    re_evaluate_blocked,
    reclaim_stale,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.dispatcher")

# Shutdown flag -- set by the lifespan handler to signal workers to stop
_shutting_down = False

_EXECUTOR_MAP: dict[TaskType, Callable] = {
    TaskType.BRICKLINK_METADATA: execute_bricklink_metadata,
    TaskType.BRICKECONOMY: execute_brickeconomy,
    TaskType.KEEPA: execute_keepa,
    TaskType.MINIFIGURES: execute_minifigures,
    TaskType.GOOGLE_TRENDS: execute_google_trends,
}

# Max concurrent workers per task type.
# Browser-based scrapers (Keepa, BrickEconomy) limited to 1.
_MAX_CONCURRENCY: dict[TaskType, int] = {
    TaskType.BRICKLINK_METADATA: 2,
    TaskType.BRICKECONOMY: 1,
    TaskType.KEEPA: 1,
    TaskType.MINIFIGURES: 1,
    TaskType.GOOGLE_TRENDS: 1,
}

# Seconds to sleep when a type's queue is empty.
_POLL_INTERVAL = 3

# Per-type executor timeout (seconds).  Prevents tasks from hanging
# indefinitely due to browser/network issues and breaking the reclaim loop.
_EXECUTOR_TIMEOUT: dict[TaskType, float] = {
    TaskType.BRICKLINK_METADATA: 300,   # 5 min
    TaskType.BRICKECONOMY: 300,         # 5 min
    TaskType.KEEPA: 300,                # 5 min
    TaskType.MINIFIGURES: 600,          # 10 min (sets with many minifigs)
    TaskType.GOOGLE_TRENDS: 180,        # 3 min (60s request delay + overhead)
}

# Schema initialization flag (set once, read by all workers).
_schema_initialized = False


def shutdown_scrape_dispatcher() -> None:
    """Signal all dispatcher workers to stop after their current task."""
    global _shutting_down  # noqa: PLW0603
    _shutting_down = True
    logger.info("Scrape dispatcher shutdown requested")


async def recover_scrape_queue() -> None:
    """Crash recovery: reclaim stale tasks and re-evaluate blocked ones.

    Called once during application startup before the dispatcher starts.
    """
    from db.connection import get_connection
    from db.schema import init_schema

    conn = get_connection()
    try:
        init_schema(conn)
        reclaimed = reclaim_stale(conn)
        unblocked = re_evaluate_blocked(conn)
        if reclaimed or unblocked:
            logger.info(
                "Scrape queue recovery: reclaimed=%d, unblocked=%d",
                reclaimed,
                unblocked,
            )
    finally:
        conn.close()


async def run_scrape_dispatcher(**_kwargs: object) -> None:
    """Spawn independent workers for each task type.

    Each data source gets its own worker(s) so BrickEconomy, Keepa,
    Google Trends etc. all make progress simultaneously.
    """
    workers: list[asyncio.Task] = []

    for task_type in TaskType:
        concurrency = _MAX_CONCURRENCY.get(task_type, 1)
        for i in range(concurrency):
            worker_id = (
                f"{task_type.value}-{i}" if concurrency > 1
                else task_type.value
            )
            workers.append(
                asyncio.create_task(_worker_loop(worker_id, task_type))
            )

    logger.info(
        "Scrape dispatcher started: %d workers across %d task types",
        len(workers),
        len(TaskType),
    )
    await asyncio.gather(*workers)


async def _worker_loop(worker_id: str, task_type: TaskType) -> None:
    """Single worker: claim a task of the given type, execute it, repeat."""
    timeout = _EXECUTOR_TIMEOUT.get(task_type, 300)
    while not _shutting_down:
        try:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        _claim_and_execute, worker_id, task_type
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[%s] Executor timed out after %ds, force-failing task",
                    worker_id, timeout,
                )
                _fail_current_task(worker_id, task_type)
                if task_type == TaskType.GOOGLE_TRENDS:
                    remaining = get_trends_cooldown_remaining()
                    if remaining > 0:
                        logger.info(
                            "[%s] Cooldown active after timeout, sleeping %.0fs",
                            worker_id, remaining,
                        )
                        try:
                            await asyncio.sleep(remaining)
                        except asyncio.CancelledError:
                            logger.info("[%s] Worker cancelled during cooldown sleep", worker_id)
                            return
                continue
        except asyncio.CancelledError:
            logger.info("[%s] Worker cancelled, shutting down", worker_id)
            return

        # float return = cooldown seconds, sleep until source is available
        if isinstance(result, float):
            logger.info(
                "[%s] Source in cooldown, sleeping %.0fs",
                worker_id, result,
            )
            try:
                await asyncio.sleep(result)
            except asyncio.CancelledError:
                logger.info("[%s] Worker cancelled during cooldown sleep", worker_id)
                return
        elif not result:
            try:
                await asyncio.sleep(_POLL_INTERVAL)
            except asyncio.CancelledError:
                logger.info("[%s] Worker cancelled during sleep, shutting down", worker_id)
                return


def _fail_current_task(worker_id: str, task_type: TaskType) -> None:
    """Force-fail whatever task this worker currently has locked.

    Opens a fresh DB connection so it works even when the executor's
    connection is still in use by the (now-orphaned) thread.
    Timeouts are non-retriable -- the task is failed immediately.
    """
    from db.connection import get_connection

    conn = get_connection()
    try:
        force_fail_by_worker(
            conn, worker_id, task_type.value, "Executor timed out"
        )
    finally:
        conn.close()


def _claim_and_execute(worker_id: str, task_type: TaskType) -> bool | float:
    """Claim the next pending task of the given type and run its executor.

    Returns:
        True  — a task was executed (success or failure)
        False — the queue was empty
        float — executor returned a cooldown; value is seconds to sleep
    """
    global _schema_initialized  # noqa: PLW0603

    from db.connection import get_connection
    from db.schema import init_schema

    conn = get_connection()
    if not _schema_initialized:
        init_schema(conn)
        _schema_initialized = True

    try:
        try:
            task = claim_next(conn, worker_id, task_type)
        except Exception as exc:
            if "Conflict" in str(exc):
                logger.debug("[%s] Transaction conflict on claim, will retry", worker_id)
                return False
            raise
        if task is None:
            return False

        logger.info(
            "[%s] %s (attempt %d/%d)",
            worker_id,
            task.set_number,
            task.attempt_count,
            task.max_attempts,
        )

        executor = _EXECUTOR_MAP.get(task.task_type)
        if executor is None:
            fail_task(conn, task.task_id, f"No executor for {task.task_type.value}")
            return True

        try:
            success, error = executor(conn, task.set_number)
        except Exception as exc:
            logger.exception(
                "[%s] %s failed", worker_id, task.set_number,
            )
            fail_task(conn, task.task_id, str(exc))
            return True

        if success:
            complete_task(conn, task.task_id)
            logger.info("[%s] %s completed", worker_id, task.set_number)
        elif error and error.startswith("cooldown:"):
            # Source is in cooldown — put task back to pending (don't burn
            # attempts) and tell the worker loop to sleep until cooldown ends.
            sleep_seconds = float(error.split(":", 1)[1])
            conn.execute(
                """UPDATE scrape_tasks
                   SET status = 'pending', locked_by = NULL, locked_at = NULL,
                       attempt_count = attempt_count - 1
                   WHERE task_id = ?""",
                [task.task_id],
            )
            logger.info(
                "[%s] %s returned to queue (source cooldown, %.0fs remaining)",
                worker_id, task.set_number, sleep_seconds,
            )
            return sleep_seconds
        elif error and "cooldown" in error.lower():
            # Other cooldown errors (e.g. Google Trends) — non-retriable
            force_fail_task(conn, task.task_id, error)
            logger.warning(
                "[%s] %s failed (non-retriable): %s", worker_id, task.set_number, error,
            )
        else:
            fail_task(conn, task.task_id, error or "Unknown error")
            logger.warning(
                "[%s] %s failed: %s", worker_id, task.set_number, error,
            )

        return True
    finally:
        conn.close()
