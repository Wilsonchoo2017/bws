"""Periodic saturation sweep -- scans for items needing Shopee saturation checks."""

import asyncio
import logging

from api.jobs import JobManager
from services.operations.scheduler_registry import (
    is_enabled,
    record_disabled,
    record_run,
)

logger = logging.getLogger("bws.shopee.saturation.scheduler")

DEFAULT_INTERVAL_MINUTES = 360  # Every 6 hours
DEFAULT_BATCH_SIZE = 50


async def run_saturation_sweep(
    manager: JobManager,
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Run periodic saturation sweep.

    Infinite loop that:
    1. Waits for interval_minutes
    2. Scans lego_items for sets with RRP but no recent saturation check
    3. Queues a shopee_saturation batch job (deduplicated)
    """
    logger.info(
        "Saturation sweep started (interval=%dm, batch=%d)",
        interval_minutes,
        batch_size,
    )

    while True:
        await asyncio.sleep(interval_minutes * 60)

        if not is_enabled("saturation"):
            await record_disabled("saturation")
            continue

        try:
            async with record_run("saturation") as run:
                # Check if a saturation job is already queued or running
                existing = manager.list_jobs()
                has_pending = any(
                    j.scraper_id == "shopee_saturation"
                    and j.status.value in ("queued", "running")
                    for j in existing
                )
                if has_pending:
                    logger.debug("Saturation sweep: job already pending, skipping")
                    continue

                from db.connection import get_connection
                from db.schema import init_schema
                from services.shopee.saturation_repository import (
                    get_items_needing_saturation_check,
                )

                conn = get_connection()
                try:
                    init_schema(conn)
                    items = get_items_needing_saturation_check(conn, limit=batch_size)
                finally:
                    conn.close()

                if not items:
                    logger.debug("Saturation sweep: no items need checking")
                    continue

                manager.create_job(
                    "shopee_saturation",
                    "batch",
                    reason=f"scheduled sweep: {len(items)} items stale",
                )
                run.items_queued = len(items)
                logger.info(
                    "Saturation sweep: %d items need checking, queued batch job",
                    len(items),
                )

        except Exception:
            logger.exception("Saturation sweep failed")
