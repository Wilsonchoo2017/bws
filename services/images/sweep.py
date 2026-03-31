"""Background image download sweep -- periodically downloads pending images."""

from __future__ import annotations

import asyncio
import logging

from db.connection import get_connection
from db.schema import init_schema
from services.images.downloader import download_batch
from services.images.repository import get_download_stats, register_existing_images

logger = logging.getLogger("bws.images.sweep")

# Run every 5 minutes
_SWEEP_INTERVAL_S = 300
_BATCH_SIZE = 50


async def run_image_download_sweep() -> None:
    """Periodically download pending images in the background.

    On first run, registers existing items that don't have image_assets entries.
    Then continuously processes pending downloads in batches.
    """
    # Wait a bit for the app to fully start
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
        try:
            conn = get_connection()
            init_schema(conn)

            stats = get_download_stats(conn)
            pending = stats["totals"].get("pending", 0) + stats["totals"].get("failed", 0)

            if pending > 0:
                logger.info("Image sweep: %d pending, starting batch download", pending)
                downloaded, failed = await download_batch(conn, batch_size=_BATCH_SIZE)
                logger.info("Image sweep: downloaded=%d, failed=%d", downloaded, failed)
            else:
                logger.debug("Image sweep: no pending downloads")

            conn.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Image sweep error")

        await asyncio.sleep(_SWEEP_INTERVAL_S)
