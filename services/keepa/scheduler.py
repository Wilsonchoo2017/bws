"""Keepa sweep -- ensures all items have at least one Keepa snapshot.

Runs periodically, finds items without Keepa data,
and queues scrape jobs for them.  Tracks failed attempts so the
same items are not retried endlessly.
"""

import asyncio
import logging
from datetime import datetime, timezone

from api.jobs import JobManager

logger = logging.getLogger("bws.keepa.scheduler")

DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_BATCH_SIZE = 1000

# Max consecutive failures before a set number is skipped for 24 hours.
_MAX_FAILURES = 3

# Cooldown after max failures (seconds).
_FAILURE_COOLDOWN_S = 24 * 3600

# Track per-set failure counts and last-failure timestamps.
# Key: set_number, Value: (failure_count, last_failure_utc)
_failure_tracker: dict[str, tuple[int, datetime]] = {}


def _get_items_without_keepa(limit: int = 5) -> list[str]:
    """Find set numbers that have no Keepa snapshot."""
    from db.connection import get_connection
    from db.schema import init_schema

    conn = get_connection()
    try:
        init_schema(conn)

        rows = conn.execute(
            """
            SELECT li.set_number
            FROM lego_items li
            WHERE NOT EXISTS (
                SELECT 1 FROM keepa_snapshots ks
                WHERE ks.set_number = li.set_number
            )
            ORDER BY li.created_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()

        return [row[0] for row in rows]
    finally:
        conn.close()


def _is_on_cooldown(set_number: str) -> bool:
    """Check if a set number has exceeded max failures and is still in cooldown."""
    entry = _failure_tracker.get(set_number)
    if not entry:
        return False

    count, last_fail = entry
    if count < _MAX_FAILURES:
        return False

    elapsed = (datetime.now(tz=timezone.utc) - last_fail).total_seconds()
    if elapsed >= _FAILURE_COOLDOWN_S:
        # Cooldown expired -- reset tracker
        del _failure_tracker[set_number]
        return False

    return True


def record_keepa_failure(set_number: str) -> None:
    """Record a Keepa scrape failure for cooldown tracking."""
    from services.notifications.scraper_alerts import alert_keepa_cooldown

    entry = _failure_tracker.get(set_number)
    now = datetime.now(tz=timezone.utc)
    if entry:
        _failure_tracker[set_number] = (entry[0] + 1, now)
    else:
        _failure_tracker[set_number] = (1, now)

    count = _failure_tracker[set_number][0]
    if count >= _MAX_FAILURES:
        cooldown_hours = _FAILURE_COOLDOWN_S // 3600
        logger.warning(
            "Keepa: %s has failed %d times, cooling down for %dh",
            set_number, count, cooldown_hours,
        )
        alert_keepa_cooldown(set_number, count, cooldown_hours)


def record_keepa_success(set_number: str) -> None:
    """Clear failure tracking for a successfully scraped set."""
    from services.notifications.scraper_alerts import alert_keepa_recovered

    had_failures = set_number in _failure_tracker
    _failure_tracker.pop(set_number, None)
    if had_failures:
        alert_keepa_recovered(set_number)


def queue_keepa_batch(manager: JobManager, set_numbers: list[str]) -> int:
    """Queue Keepa scrape jobs for the given set numbers.

    Deduplicates against already-queued/running keepa jobs and
    skips items on failure cooldown.
    Returns the number of new jobs queued.
    """
    from api.schemas import JobStatus

    # Check existing pending/running/recently-failed keepa jobs
    existing = set()
    for job in manager.list_jobs():
        if job.scraper_id != "keepa":
            continue
        url = job.url.strip()
        if job.status in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED):
            existing.add(url)

    queued = 0
    for set_number in set_numbers:
        if set_number in existing:
            continue
        if _is_on_cooldown(set_number):
            logger.debug("Keepa sweep: skipping %s (on cooldown)", set_number)
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
    """Run periodic Keepa sweep for all items.

    Infinite loop that:
    1. Waits for `interval_minutes`
    2. Finds items without Keepa data
    3. Queues Keepa scrape jobs (deduplicated, with failure tracking)
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
            missing = _get_items_without_keepa(limit=batch_size)

            if not missing:
                logger.debug("Keepa sweep: all items have Keepa data")
                continue

            queued = queue_keepa_batch(manager, missing)
            if queued > 0:
                logger.info(
                    "Keepa sweep: %d items missing Keepa data, "
                    "queued %d jobs (sets: %s)",
                    len(missing),
                    queued,
                    ", ".join(missing[:10]),
                )
            else:
                logger.debug(
                    "Keepa sweep: %d items missing but all skipped "
                    "(already queued or on cooldown)",
                    len(missing),
                )
        except Exception:
            logger.exception("Keepa sweep failed")
