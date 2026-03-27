"""Periodic enrichment sweep -- scans for items with missing metadata and queues jobs."""

import asyncio
import logging

from api.jobs import JobManager
from services.enrichment.auto import queue_enrichment_batch

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
    3. Queues enrichment jobs (deduplicated against pending jobs)
    """
    logger.info(
        "Enrichment sweep started (interval=%dm, batch=%d)",
        interval_minutes,
        batch_size,
    )

    while True:
        await asyncio.sleep(interval_minutes * 60)

        try:
            from db.connection import get_connection
            from db.schema import init_schema
            from services.enrichment.repository import get_items_needing_enrichment

            conn = get_connection()
            try:
                init_schema(conn)
                items = get_items_needing_enrichment(conn, limit=batch_size)
            finally:
                conn.close()

            if not items:
                logger.debug("Enrichment sweep: no items need enrichment")
                continue

            set_numbers = [item["set_number"] for item in items]
            queued = queue_enrichment_batch(manager, set_numbers)

            logger.info(
                "Enrichment sweep: found %d items, queued %d jobs",
                len(items),
                queued,
            )

        except Exception:
            logger.exception("Enrichment sweep failed")
