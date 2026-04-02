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
import os
import signal
import subprocess
from typing import TYPE_CHECKING

from services.scrape_queue.executors import (
    execute_brickeconomy,
    execute_bricklink_metadata,
    execute_google_trends,
    execute_keepa,
    execute_minifigures,
    get_trends_cooldown_remaining,
)
from services.scrape_queue.models import (
    ExecutorResult,
    TaskType,
    TaskTypeConfig,
)
from services.scrape_queue.repository import (
    claim_next,
    complete_task,
    fail_task,
    force_fail_by_worker,
    force_fail_task,
    re_evaluate_blocked,
    reclaim_stale,
    requeue_for_cooldown,
)

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.dispatcher")


# ---------------------------------------------------------------------------
# Single source of truth -- one entry per task type
# ---------------------------------------------------------------------------

TASK_TYPE_CONFIGS: dict[TaskType, TaskTypeConfig] = {
    TaskType.BRICKLINK_METADATA: TaskTypeConfig(
        task_type=TaskType.BRICKLINK_METADATA,
        executor=execute_bricklink_metadata,
        concurrency=2,
        timeout_seconds=300,
    ),
    TaskType.BRICKECONOMY: TaskTypeConfig(
        task_type=TaskType.BRICKECONOMY,
        executor=execute_brickeconomy,
        concurrency=1,
        timeout_seconds=300,
        browser_profile="brickeconomy-profile",
    ),
    TaskType.KEEPA: TaskTypeConfig(
        task_type=TaskType.KEEPA,
        executor=execute_keepa,
        concurrency=2,
        timeout_seconds=300,
        browser_profile="keepa-profile",
    ),
    TaskType.MINIFIGURES: TaskTypeConfig(
        task_type=TaskType.MINIFIGURES,
        executor=execute_minifigures,
        concurrency=1,
        timeout_seconds=600,
    ),
    TaskType.GOOGLE_TRENDS: TaskTypeConfig(
        task_type=TaskType.GOOGLE_TRENDS,
        executor=execute_google_trends,
        concurrency=1,
        timeout_seconds=180,
    ),
}


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
    """Flush the WAL to the main DB file.

    Called during shutdown and periodically to minimize data loss
    if the process is killed ungracefully.
    """
    from db.connection import get_connection

    conn = get_connection()
    try:
        conn.execute("FORCE CHECKPOINT")
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
    """Crash recovery: reclaim stale tasks and re-evaluate blocked ones."""
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

        try:
            result = cfg.executor(conn, task.set_number, worker_index=worker_index)
        except Exception as exc:
            logger.exception("[%s] %s crashed", worker_id, task.set_number)
            fail_task(conn, task.task_id, str(exc))
            return None

        return _handle_result(conn, worker_id, task, result)
    finally:
        conn.close()


def _handle_result(
    conn: DuckDBPyConnection,
    worker_id: str,
    task: object,
    result: ExecutorResult,
) -> float | None:
    """Process an ExecutorResult -- no magic strings, just typed fields."""
    if result.success:
        complete_task(conn, task.task_id)
        logger.info("[%s] %s completed", worker_id, task.set_number)
        return None

    if result.is_cooldown:
        requeue_for_cooldown(conn, task.task_id)
        logger.info(
            "[%s] %s returned to queue (source cooldown, %.0fs remaining)",
            worker_id, task.set_number, result.cooldown_seconds,
        )
        return result.cooldown_seconds

    # Regular failure
    fail_task(conn, task.task_id, result.error or "Unknown error")
    logger.warning("[%s] %s failed: %s", worker_id, task.set_number, result.error)
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
        force_fail_by_worker(
            conn, worker_id, cfg.task_type.value, "Executor timed out"
        )
    finally:
        conn.close()

    if cfg.uses_browser:
        _kill_orphaned_browsers(cfg.browser_profile_for(worker_index))


def _kill_orphaned_browsers(profile: str | None) -> None:
    """Kill Camoufox/Firefox processes using the given profile directory."""
    if not profile:
        return

    try:
        proc = subprocess.run(
            ["pgrep", "-f", profile],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p) for p in proc.stdout.strip().split() if p.isdigit()]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                logger.warning(
                    "Killed orphaned browser process pid=%d (%s)", pid, profile,
                )
            except ProcessLookupError:
                pass
    except Exception:
        logger.debug("Failed to clean up orphaned browsers for %s", profile)
