"""Keepa sweep -- ensures all portfolio items have at least one Keepa snapshot.

Runs periodically, finds portfolio holdings without Keepa data,
and queues scrape jobs for them.
"""

import asyncio
import logging

from api.jobs import JobManager

logger = logging.getLogger("bws.keepa.scheduler")

DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_BATCH_SIZE = 5


def _get_portfolio_items_without_keepa(limit: int = 5) -> list[str]:
    """Find portfolio set numbers that have no Keepa snapshot."""
    from db.connection import get_connection
    from db.schema import init_schema

    conn = get_connection()
    try:
        init_schema(conn)

        rows = conn.execute(
            """
            SELECT DISTINCT pt.set_number
            FROM portfolio_transactions pt
            WHERE pt.set_number NOT IN (
                SELECT DISTINCT set_number FROM keepa_snapshots
            )
            ORDER BY pt.set_number
            LIMIT ?
            """,
            [limit],
        ).fetchall()

        return [row[0] for row in rows]
    finally:
        conn.close()


def queue_keepa_batch(manager: JobManager, set_numbers: list[str]) -> int:
    """Queue Keepa scrape jobs for the given set numbers.

    Deduplicates against already-queued/running keepa jobs.
    Returns the number of new jobs queued.
    """
    # Check existing pending/running keepa jobs
    existing = {
        job.url.strip()
        for job in manager.list_jobs()
        if job.scraper_id == "keepa" and job.status in ("QUEUED", "RUNNING")
    }

    queued = 0
    for set_number in set_numbers:
        if set_number in existing:
            continue
        manager.create_job("keepa", set_number)
        queued += 1

    return queued


async def run_keepa_sweep(
    manager: JobManager,
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Run periodic Keepa sweep for portfolio items.

    Infinite loop that:
    1. Waits for `interval_minutes`
    2. Finds portfolio items without Keepa data
    3. Queues Keepa scrape jobs (deduplicated)
    """
    logger.info(
        "Keepa sweep started (interval=%dm, batch=%d)",
        interval_minutes,
        batch_size,
    )

    first_run = True
    while True:
        if first_run:
            first_run = False
            # Delay initial run to let other services start
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(interval_minutes * 60)

        try:
            missing = _get_portfolio_items_without_keepa(limit=batch_size)

            if not missing:
                logger.debug("Keepa sweep: all portfolio items have Keepa data")
                continue

            queued = queue_keepa_batch(manager, missing)
            logger.info(
                "Keepa sweep: %d portfolio items missing Keepa data, "
                "queued %d jobs (sets: %s)",
                len(missing),
                queued,
                ", ".join(missing[:10]),
            )
        except Exception:
            logger.exception("Keepa sweep failed")
