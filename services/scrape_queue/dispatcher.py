"""Scrape task dispatcher -- one independent worker per data source.

Each task type (BrickLink, BrickEconomy, Keepa, etc.) gets its own
worker coroutine so all data sources make progress concurrently,
regardless of how many pending tasks other sources have.

All per-type configuration lives in ``TASK_TYPE_CONFIGS`` -- adding a
new scraper means adding ONE entry there, not updating 5+ dicts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import services.scrape_queue.executors as _executors  # noqa: F401 -- triggers @executor registration
from services.scrape_queue.executors import get_trends_cooldown_remaining
from services.scrape_queue.models import (
    ErrorCategory,
    ExecutorResult,
    ScrapeTask,
    TaskType,
    TaskTypeConfig,
)
from services.scrape_queue.registry import REGISTRY
from services.scrape_queue.repository import (
    claim_next,
    complete_task,
    fail_task,
    force_fail_by_worker,
    force_fail_task,
    re_evaluate_blocked,
    record_attempt,
    requeue_for_cooldown,
    reset_running_tasks,
)

if TYPE_CHECKING:
    from db.pg.pg_connection import PgConnection

logger = logging.getLogger("bws.scrape_queue.dispatcher")


# ---------------------------------------------------------------------------
# Executor registry -- populated by @executor decorators on import
# ---------------------------------------------------------------------------

# REGISTRY is populated when services.scrape_queue.executors is imported
# (each executor module uses the @executor decorator to self-register).
# Alias for backward compatibility with code that references TASK_TYPE_CONFIGS.
TASK_TYPE_CONFIGS = REGISTRY


# ---------------------------------------------------------------------------
# Shutdown flag
# ---------------------------------------------------------------------------

_shutting_down = False
_POLL_INTERVAL = 3
_CHECKPOINT_INTERVAL = 30  # seconds between WAL flushes
_schema_initialized = False


def shutdown_scrape_dispatcher() -> None:
    """Signal all dispatcher workers to stop after their current task."""
    global _shutting_down  # noqa: PLW0603
    _shutting_down = True
    logger.info("Scrape dispatcher shutdown requested")


def checkpoint_database() -> None:
    """Run a Postgres CHECKPOINT to flush WAL.

    Called periodically to minimize data loss if the process
    is killed ungracefully.
    """
    from db.connection import get_connection

    conn = get_connection()
    try:
        conn.execute("CHECKPOINT")
        logger.debug("Database checkpoint completed")
    except Exception:
        logger.debug("Database checkpoint skipped", exc_info=True)
    finally:
        conn.close()


async def _periodic_checkpoint() -> None:
    """Flush WAL to the main DB file every CHECKPOINT_INTERVAL seconds."""
    while not _shutting_down:
        try:
            await asyncio.sleep(_CHECKPOINT_INTERVAL)
        except asyncio.CancelledError:
            return
        if _shutting_down:
            return
        try:
            await asyncio.to_thread(checkpoint_database)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.warning("Periodic checkpoint failed", exc_info=True)


# ---------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------


async def recover_scrape_queue() -> None:
    """Crash recovery: reset orphaned running tasks and re-evaluate blocked ones."""
    from db.connection import get_connection
    from db.schema import init_schema

    conn = get_connection()
    try:
        init_schema(conn)
        reclaimed = reset_running_tasks(conn)
        unblocked = re_evaluate_blocked(conn)
        if reclaimed or unblocked:
            logger.info(
                "Scrape queue recovery: reclaimed=%d, unblocked=%d",
                reclaimed, unblocked,
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dispatcher entry point
# ---------------------------------------------------------------------------


async def run_scrape_dispatcher(**_kwargs: object) -> None:
    """Spawn independent workers for each task type."""
    workers: list[asyncio.Task] = []

    for task_type, cfg in TASK_TYPE_CONFIGS.items():
        for i in range(cfg.concurrency):
            worker_id = (
                f"{task_type.value}-{i}" if cfg.concurrency > 1
                else task_type.value
            )
            workers.append(
                asyncio.create_task(_worker_loop(worker_id, cfg, worker_index=i))
            )

    # Periodic checkpoint to flush WAL to the main DB file
    workers.append(asyncio.create_task(_periodic_checkpoint()))

    logger.info(
        "Scrape dispatcher started: %d workers across %d task types",
        len(workers), len(TASK_TYPE_CONFIGS),
    )
    await asyncio.gather(*workers)


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


async def _worker_loop(
    worker_id: str,
    cfg: TaskTypeConfig,
    *,
    worker_index: int = 0,
) -> None:
    """Single worker: claim a task, execute it, repeat."""
    while not _shutting_down:
        try:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        _claim_and_execute, worker_id, cfg,
                        worker_index=worker_index,
                    ),
                    timeout=cfg.timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[%s] Executor timed out after %ds, force-failing task",
                    worker_id, cfg.timeout_seconds,
                )
                _fail_current_task(worker_id, cfg, worker_index=worker_index)
                if cfg.uses_browser:
                    await asyncio.sleep(3)
                if cfg.task_type == TaskType.GOOGLE_TRENDS:
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

        if isinstance(result, float) and result > 0:
            # Source in cooldown -- sleep until available
            logger.info("[%s] Source in cooldown, sleeping %.0fs", worker_id, result)
            try:
                await asyncio.sleep(result)
            except asyncio.CancelledError:
                logger.info("[%s] Worker cancelled during cooldown sleep", worker_id)
                return
        elif result is None:
            # Queue empty
            try:
                await asyncio.sleep(_POLL_INTERVAL)
            except asyncio.CancelledError:
                logger.info("[%s] Worker cancelled during sleep, shutting down", worker_id)
                return


# ---------------------------------------------------------------------------
# Claim + execute (runs in thread via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _classify_exception(exc: Exception) -> ErrorCategory:
    """Best-effort categorisation of unhandled executor exceptions."""
    msg = str(exc).lower()
    if "launch_persistent_context" in msg or "browser" in msg:
        return ErrorCategory.BROWSER_CRASH
    if "targetclosederror" in msg:
        return ErrorCategory.BROWSER_CRASH
    if "timeout" in msg or "timed out" in msg:
        return ErrorCategory.TIMEOUT
    return ErrorCategory.UNKNOWN


def _claim_and_execute(
    worker_id: str,
    cfg: TaskTypeConfig,
    *,
    worker_index: int = 0,
) -> float | None:
    """Claim the next pending task and run its executor.

    Returns:
        None   -- queue was empty OR task executed (success/failure)
        float  -- cooldown seconds; dispatcher should sleep this long
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
            task = claim_next(conn, worker_id, cfg.task_type)
        except Exception as exc:
            if "Conflict" in str(exc):
                logger.debug("[%s] Transaction conflict on claim, will retry", worker_id)
                return None
            raise
        if task is None:
            return None

        logger.info(
            "[%s] %s (attempt %d/%d)",
            worker_id, task.set_number,
            task.attempt_count, task.max_attempts,
        )

        t0 = time.monotonic()
        try:
            result = cfg.executor(conn, task.set_number, worker_index=worker_index)
        except Exception as exc:
            duration = time.monotonic() - t0
            category = _classify_exception(exc)
            logger.exception("[%s] %s crashed", worker_id, task.set_number)
            fail_task(conn, task.task_id, str(exc))
            record_attempt(
                conn,
                task.task_id,
                task.attempt_count,
                error_category=category,
                error_message=str(exc),
                duration_seconds=duration,
            )
            return None

        duration = time.monotonic() - t0
        return _handle_result(conn, worker_id, task, result, duration)
    finally:
        conn.close()


def _handle_result(
    conn: "PgConnection",
    worker_id: str,
    task: ScrapeTask,
    result: ExecutorResult,
    duration: float,
) -> float | None:
    """Process an ExecutorResult -- no magic strings, just typed fields."""
    if result.success:
        complete_task(conn, task.task_id)
        record_attempt(
            conn, task.task_id, task.attempt_count,
            duration_seconds=duration,
        )
        logger.info("[%s] %s completed", worker_id, task.set_number)
        return None

    if result.is_cooldown:
        requeue_for_cooldown(conn, task.task_id)
        record_attempt(
            conn, task.task_id, task.attempt_count,
            error_category=ErrorCategory.RATE_LIMITED,
            error_message="Source in cooldown",
            duration_seconds=duration,
        )
        logger.debug(
            "[%s] %s returned to queue (source cooldown, %.0fs remaining)",
            worker_id, task.set_number, result.cooldown_seconds,
        )
        return result.cooldown_seconds

    # Regular or permanent failure
    error_msg = result.error or "Unknown error"
    if result.permanent:
        force_fail_task(conn, task.task_id, error_msg)
    else:
        fail_task(conn, task.task_id, error_msg)
    record_attempt(
        conn, task.task_id, task.attempt_count,
        error_category=result.error_category,
        error_message=error_msg,
        duration_seconds=duration,
    )
    logger.warning("[%s] %s failed: %s", worker_id, task.set_number, error_msg)
    return None


# ---------------------------------------------------------------------------
# Timeout cleanup
# ---------------------------------------------------------------------------


def _fail_current_task(
    worker_id: str,
    cfg: TaskTypeConfig,
    *,
    worker_index: int = 0,
) -> None:
    """Force-fail the timed-out task and kill orphaned browsers."""
    from db.connection import get_connection

    conn = get_connection()
    try:
        # Find the task before force-failing so we can record the attempt
        row = conn.execute(
            "SELECT task_id, attempt_count FROM scrape_tasks "
            "WHERE locked_by = ? AND task_type = ? AND status = 'running'",
            [worker_id, cfg.task_type.value],
        ).fetchone()

        force_fail_by_worker(
            conn, worker_id, cfg.task_type.value, "Executor timed out"
        )

        if row:
            record_attempt(
                conn, row[0], row[1],
                error_category=ErrorCategory.TIMEOUT,
                error_message="Executor timed out",
                duration_seconds=cfg.timeout_seconds,
            )
    finally:
        conn.close()

    if cfg.uses_browser:
        _kill_orphaned_browsers(cfg.browser_profile_for(worker_index))


def _kill_orphaned_browsers(profile: str | None) -> None:
    """Kill Camoufox/Firefox processes using the given profile directory."""
    if not profile:
        return
    from services.browser.process_guard import kill_browser_processes_graceful
    kill_browser_processes_graceful(profile)
