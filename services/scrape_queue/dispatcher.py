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
)
from services.scrape_queue.models import TaskType
from services.scrape_queue.repository import (
    claim_next,
    complete_task,
    fail_task,
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
    while not _shutting_down:
        try:
            claimed = await asyncio.to_thread(
                _claim_and_execute, worker_id, task_type
            )
        except asyncio.CancelledError:
            logger.info("[%s] Worker cancelled, shutting down", worker_id)
            return
        if not claimed:
            try:
                await asyncio.sleep(_POLL_INTERVAL)
            except asyncio.CancelledError:
                logger.info("[%s] Worker cancelled during sleep, shutting down", worker_id)
                return


def _claim_and_execute(worker_id: str, task_type: TaskType) -> bool:
    """Claim the next pending task of the given type and run its executor.

    Returns True if a task was executed, False if the queue was empty.
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
        elif error and "cooldown" in error.lower():
            # Cooldown errors are non-retriable — mark as final failure immediately
            # to avoid burning through all retry attempts pointlessly.
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
