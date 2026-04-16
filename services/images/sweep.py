"""Background image download sweep -- periodically downloads pending images.

Image downloads are paused entirely while BrickLink metadata scraping has
pending tasks, since both hit the same domain and share rate budget.
"""

from __future__ import annotations

import asyncio
import logging

from db.connection import get_connection
from db.schema import init_schema
from services.images.downloader import download_batch
from services.images.repository import get_download_stats, register_existing_images
from services.operations.scheduler_registry import (
    is_enabled,
    record_disabled,
    record_run,
)

logger = logging.getLogger("bws.images.sweep")

_SWEEP_INTERVAL_S = 300     # 5 min between batches
_PAUSED_CHECK_INTERVAL_S = 60  # check every 60s if metadata is done
_BATCH_SIZE = 50


def _has_pending_metadata() -> bool:
    """Check whether BrickLink metadata scraping still has work to do."""
    try:
        conn = get_connection()
        from services.scrape_queue.repository import has_pending_bricklink_tasks
        result = has_pending_bricklink_tasks(conn)
        conn.close()
        return result
    except Exception:
        return False


async def run_image_download_sweep() -> None:
    """Periodically download pending images in the background.

    Pauses entirely while BrickLink metadata tasks are pending so that
    all rate budget goes to enrichment first.
    """
    await asyncio.sleep(10)
    logger.info("Image download sweep started")

    # Initial registration of existing items
    try:
        conn = get_connection()
        init_schema(conn)
        registered = register_existing_images(conn)
        if registered:
            logger.info("Registered %d existing items for image download", registered)
        conn.close()
    except Exception:
        logger.exception("Failed to register existing images")

    while True:
        # Gate: wait until metadata scraping is done
        if _has_pending_metadata():
            logger.info("Image sweep paused -- BrickLink metadata tasks pending")
            while _has_pending_metadata():
                try:
                    await asyncio.sleep(_PAUSED_CHECK_INTERVAL_S)
                except asyncio.CancelledError:
                    return
            logger.info("Image sweep resuming -- metadata queue empty")

        if not is_enabled("images"):
            await record_disabled("images")
            await asyncio.sleep(_SWEEP_INTERVAL_S)
            continue

        try:
            async with record_run("images") as run:
                conn = get_connection()
                try:
                    init_schema(conn)

                    stats = get_download_stats(conn)
                    pending = (
                        stats["totals"].get("pending", 0)
                        + stats["totals"].get("failed", 0)
                    )

                    if pending > 0:
                        logger.info("Image sweep: %d pending, starting batch download", pending)
                        downloaded, failed = await download_batch(conn, batch_size=_BATCH_SIZE)
                        run.items_queued = downloaded
                        logger.info("Image sweep: downloaded=%d, failed=%d", downloaded, failed)
                    else:
                        logger.debug("Image sweep: no pending downloads")
                finally:
                    conn.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Image sweep error")

        await asyncio.sleep(_SWEEP_INTERVAL_S)
