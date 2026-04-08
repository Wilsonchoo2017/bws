"""Periodic competition sweep -- scans portfolio items for Shopee competition checks."""

import asyncio
import logging

from api.jobs import JobManager

logger = logging.getLogger("bws.shopee.competition.scheduler")

DEFAULT_INTERVAL_MINUTES = 720  # Check every 12 hours
DEFAULT_BATCH_SIZE = 20


async def run_competition_sweep(
    manager: JobManager,
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Run periodic competition sweep for portfolio items.

    Checks every 12 hours but only queues work when items are 7+ days stale.
    """
    logger.info(
        "Competition sweep started (interval=%dm, batch=%d)",
        interval_minutes,
        batch_size,
    )

    while True:
        await asyncio.sleep(interval_minutes * 60)

        try:
            existing = manager.list_jobs()
            has_pending = any(
                j.scraper_id == "shopee_competition"
                and j.status.value in ("queued", "running")
                for j in existing
            )
            if has_pending:
                logger.debug("Competition sweep: job already pending, skipping")
                continue

            from db.connection import get_connection
            from db.schema import init_schema
            from services.shopee.competition_repository import (
                get_portfolio_items_needing_competition_check,
            )

            conn = get_connection()
            try:
                init_schema(conn)
                items = get_portfolio_items_needing_competition_check(
                    conn, limit=batch_size,
                )
            finally:
                conn.close()

            if not items:
                logger.debug("Competition sweep: no items need checking")
                continue

            manager.create_job("shopee_competition", "batch")
            logger.info(
                "Competition sweep: %d portfolio items need checking, queued batch job",
                len(items),
            )

        except Exception:
            logger.exception("Competition sweep failed")
