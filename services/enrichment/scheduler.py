"""Periodic enrichment sweep -- scans for items with missing metadata and creates scrape tasks."""

import asyncio
import logging

from api.jobs import JobManager

logger = logging.getLogger("bws.enrichment.scheduler")

DEFAULT_INTERVAL_MINUTES = 30
DEFAULT_BATCH_SIZE = 10
RESCRAPE_INTERVAL_MINUTES = 60
RESCRAPE_STALE_DAYS = 30


async def run_enrichment_sweep(
    manager: JobManager,
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Run periodic enrichment sweep.

    Infinite loop that:
    1. Waits for `interval_minutes`
    2. Scans lego_items for rows with NULL metadata
    3. Creates persistent scrape tasks (deduplicated)
    """
    logger.info(
        "Enrichment sweep started (interval=%dm, batch=%d)",
        interval_minutes,
        batch_size,
    )

    first_run = True
    while True:
        if first_run:
            first_run = False
            logger.info("Enrichment sweep: running initial sweep on startup")
        else:
            await asyncio.sleep(interval_minutes * 60)

        try:
            from db.connection import get_connection
            from db.schema import init_schema
            from services.enrichment.repository import get_items_needing_enrichment
            from services.scrape_queue.repository import create_tasks_for_set

            conn = get_connection()
            try:
                init_schema(conn)
                items = get_items_needing_enrichment(conn, limit=batch_size)

                if not items:
                    logger.debug("Enrichment sweep: no items need enrichment")
                    continue

                queued = 0
                for item in items:
                    tasks = create_tasks_for_set(conn, item["set_number"])
                    if tasks:
                        queued += 1

                logger.info(
                    "Enrichment sweep: found %d items, created tasks for %d",
                    len(items),
                    queued,
                )
            finally:
                conn.close()

        except Exception:
            logger.exception("Enrichment sweep failed")


_RESCRAPE_TASK_TYPES = (
    "BRICKLINK_METADATA",
    "BRICKECONOMY",
    "KEEPA",
    "MINIFIGURES",
)


async def run_priority_rescrape_sweep(
    *,
    interval_minutes: int = RESCRAPE_INTERVAL_MINUTES,
    stale_days: int = RESCRAPE_STALE_DAYS,
) -> None:
    """Periodically enqueue rescrapes for priority sets across all pricing sources.

    Targets sets that are retiring soon, recently retired (last 6 months),
    or held in the portfolio -- but only when the last scrape for each
    source is older than ``stale_days``.

    Sources: BrickLink, BrickEconomy, Keepa, Minifigures.
    """
    from services.scrape_queue.models import TaskType

    task_types = [TaskType[t] for t in _RESCRAPE_TASK_TYPES]

    logger.info(
        "Priority rescrape sweep started (interval=%dm, stale_days=%d, sources=%s)",
        interval_minutes,
        stale_days,
        ", ".join(t.value for t in task_types),
    )

    first_run = True
    while True:
        if first_run:
            first_run = False
            # Small delay to let the enrichment sweep run first
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(interval_minutes * 60)

        try:
            from db.connection import get_connection
            from db.schema import init_schema
            from services.scrape_queue.repository import (
                create_task,
                get_priority_rescrape_candidates,
            )

            conn = get_connection()
            try:
                init_schema(conn)
                total_queued = 0

                for task_type in task_types:
                    candidates = get_priority_rescrape_candidates(
                        conn, task_type, stale_days=stale_days,
                    )
                    if not candidates:
                        continue

                    queued = 0
                    for set_number in candidates:
                        task = create_task(conn, set_number, task_type)
                        if task is not None:
                            queued += 1

                    logger.info(
                        "Priority rescrape [%s]: %d candidates, queued %d",
                        task_type.value,
                        len(candidates),
                        queued,
                    )
                    total_queued += queued

                if total_queued == 0:
                    logger.debug("Priority rescrape sweep: nothing to enqueue")

            finally:
                conn.close()

        except Exception:
            logger.exception("Priority rescrape sweep failed")
