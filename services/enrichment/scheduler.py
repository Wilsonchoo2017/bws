"""Periodic enrichment sweep -- scans for items with missing metadata and creates scrape tasks."""

import asyncio
import logging

from api.jobs import JobManager

logger = logging.getLogger("bws.enrichment.scheduler")

DEFAULT_INTERVAL_MINUTES = 30
DEFAULT_BATCH_SIZE = 10


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
