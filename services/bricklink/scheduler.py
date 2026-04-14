"""Periodic sweep that backfills BrickLink store-listings data.

The main BrickLink metadata scraper is a logged-in Camoufox browser
pipeline (see ``services.bricklink.browser_scraper``), which fetches
both the v2 catalog page (item info + per-store listings) and the
legacy catalogPG.asp page (price boxes + monthly sales) in one go.

This sweep hunts for sets whose ``bricklink_store_listings`` snapshot
is missing or stale, ordered by most recent ``year_released``, and
enqueues ``BRICKLINK_METADATA`` tasks so the executor picks them up.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("bws.bricklink.scheduler")

DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_LIMIT = 100
STARTUP_DELAY_SECONDS = 30


async def run_bricklink_listings_sweep(
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    limit: int = DEFAULT_LIMIT,
) -> None:
    """Hourly sweep that queues BrickLink listings rescrapes.

    Picks up to ``limit`` sets where ``bricklink_store_listings`` is
    missing / stale and creates ``BRICKLINK_METADATA`` tasks.  Most
    recently released sets come first.
    """
    logger.info(
        "BrickLink listings sweep started (interval=%dm, limit=%d)",
        interval_minutes,
        limit,
    )

    first_run = True
    while True:
        if first_run:
            first_run = False
            # Let other sweeps boot + the browser profile warm up first.
            await asyncio.sleep(STARTUP_DELAY_SECONDS)
        else:
            await asyncio.sleep(interval_minutes * 60)

        try:
            await asyncio.to_thread(_run_one_pass, limit)
        except Exception:
            logger.exception("BrickLink listings sweep iteration failed")


def _run_one_pass(limit: int) -> None:
    """Synchronous body of one sweep iteration.

    Isolated so tests can call it directly without spinning up a task.
    """
    from db.connection import get_connection
    from db.schema import init_schema
    from services.scrape_queue.models import TaskType
    from services.scrape_queue.repository import (
        create_task,
        get_missing_listings_candidates,
    )

    conn = get_connection()
    try:
        init_schema(conn)
        candidates = get_missing_listings_candidates(conn, limit=limit)

        if not candidates:
            logger.debug("BrickLink listings sweep: no candidates")
            return

        queued = 0
        for set_number, reason in candidates:
            task = create_task(
                conn,
                set_number,
                TaskType.BRICKLINK_METADATA,
                reason=reason,
            )
            if task is not None:
                queued += 1

        logger.info(
            "BrickLink listings sweep: %d candidates, queued %d",
            len(candidates),
            queued,
        )
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            logger.debug("Sweep connection close failed", exc_info=True)
