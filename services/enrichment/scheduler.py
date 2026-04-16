"""Periodic enrichment sweep -- scans for items with missing metadata and creates scrape tasks."""

import asyncio
import logging

from api.jobs import JobManager
from services.operations.scheduler_registry import (
    is_enabled,
    record_disabled,
    record_run,
)

logger = logging.getLogger("bws.enrichment.scheduler")

DEFAULT_INTERVAL_MINUTES = 30
DEFAULT_BATCH_SIZE = 10
RESCRAPE_INTERVAL_MINUTES = 60


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

        if not is_enabled("enrichment"):
            await record_disabled("enrichment")
            continue

        try:
            async with record_run("enrichment") as run:
                from db.connection import get_connection
                from db.schema import init_schema
                from services.enrichment.repository import (
                    compute_enrichment_reason,
                    get_items_needing_enrichment,
                )
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
                        reason = compute_enrichment_reason(item)
                        tasks = create_tasks_for_set(
                            conn, item["set_number"], reason=reason,
                            source="enrichment_sweep",
                        )
                        if tasks:
                            queued += 1

                    run.items_queued = queued
                    logger.info(
                        "Enrichment sweep: found %d items, created tasks for %d",
                        len(items),
                        queued,
                    )
                finally:
                    conn.close()

        except Exception:
            logger.exception("Enrichment sweep failed")


RETIRING_SOON_INTERVAL_DAYS = 150  # ~5 months


async def run_retiring_soon_sweep(
    *,
    interval_days: int = RETIRING_SOON_INTERVAL_DAYS,
) -> None:
    """Periodically scrape the BrickEconomy retiring-soon list page.

    Runs on startup, then every ~5 months. Updates lego_items.retiring_soon
    based on the scraped list.
    """
    logger.info("Retiring-soon sweep started (interval=%dd)", interval_days)

    first_run = True
    while True:
        if first_run:
            first_run = False
            # Small delay to let other sweeps start first
            await asyncio.sleep(60)
        else:
            await asyncio.sleep(interval_days * 86400)

        if not is_enabled("retiring_soon"):
            await record_disabled("retiring_soon")
            continue

        try:
            async with record_run("retiring_soon") as run:
                marked = await _sync_retiring_soon()
                if marked is not None:
                    run.items_queued = marked
        except Exception:
            logger.exception("Retiring-soon sweep failed")


async def _sync_retiring_soon() -> int | None:
    """Scrape the retiring-soon page and update the database.

    Returns the number of rows flipped to ``retiring_soon=TRUE`` for
    operations tracking. ``None`` on scrape failure or empty result.
    """
    from services.brickeconomy.retiring_soon_scraper import (
        scrape_retiring_soon,
    )

    result = await scrape_retiring_soon()
    if not result.success:
        logger.error("Retiring-soon scrape failed: %s", result.error)
        return None

    if not result.set_numbers:
        logger.info("Retiring-soon sweep: no sets found on page")
        return 0

    from db.connection import get_connection
    from db.schema import init_schema

    retiring_list = list(result.set_numbers)
    placeholders = ", ".join(["?"] * len(retiring_list))

    conn = get_connection()
    try:
        init_schema(conn)
        conn.execute("BEGIN")
        try:
            # Mark sets on the retiring-soon page (skip already retired)
            mark_result = conn.execute(
                f"""UPDATE lego_items SET retiring_soon = TRUE
                    WHERE set_number IN ({placeholders})
                      AND year_retired IS NULL
                      AND (retiring_soon IS NULL OR retiring_soon = FALSE)""",  # noqa: S608
                retiring_list,
            )
            marked = mark_result.rowcount

            # Clear sets no longer on the list
            clear_result = conn.execute(
                f"""UPDATE lego_items SET retiring_soon = FALSE
                    WHERE retiring_soon = TRUE
                      AND set_number NOT IN ({placeholders})""",  # noqa: S608
                retiring_list,
            )
            cleared = clear_result.rowcount

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        logger.info(
            "Retiring-soon sweep: marked %d, cleared %d (total on page: %d)",
            marked,
            cleared,
            len(retiring_list),
        )
        return marked
    finally:
        conn.close()


_RESCRAPE_TASK_TYPES = (
    "BRICKLINK_METADATA",
    "BRICKECONOMY",
    "KEEPA",
    "MINIFIGURES",
)


async def run_priority_rescrape_sweep(
    *,
    interval_minutes: int = RESCRAPE_INTERVAL_MINUTES,
) -> None:
    """Periodically enqueue rescrapes using tiered intervals.

    Tiers (highest priority wins):
      1. Portfolio / watchlist  -> every 30 days
      2. Retiring soon          -> every 60 days
      3. General (not retired or retired <= 48 months) -> every 150 days
      4. Expired (retired > 48 months, not portfolio/watchlist) -> never

    Sources: BrickLink, BrickEconomy, Keepa, Minifigures.
    """
    from services.scrape_queue.models import TaskType

    task_types = [TaskType[t] for t in _RESCRAPE_TASK_TYPES]

    logger.info(
        "Tiered rescrape sweep started (interval=%dm, sources=%s)",
        interval_minutes,
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

        if not is_enabled("rescrape"):
            await record_disabled("rescrape")
            continue

        try:
            async with record_run("rescrape") as run:
                from db.connection import get_connection
                from db.schema import init_schema
                from services.scrape_queue.repository import (
                    create_task,
                    get_rescrape_candidates,
                )

                conn = get_connection()
                try:
                    init_schema(conn)
                    total_queued = 0

                    for task_type in task_types:
                        candidates = get_rescrape_candidates(conn, task_type)
                        if not candidates:
                            continue

                        queued = 0
                        for set_number, reason in candidates:
                            task = create_task(
                                conn, set_number, task_type, reason=reason,
                                source="rescrape_sweep",
                            )
                            if task is not None:
                                queued += 1

                        logger.info(
                            "Tiered rescrape [%s]: %d candidates, queued %d",
                            task_type.value,
                            len(candidates),
                            queued,
                        )
                        total_queued += queued

                    run.items_queued = total_queued
                    if total_queued == 0:
                        logger.debug("Tiered rescrape sweep: nothing to enqueue")

                finally:
                    conn.close()

        except Exception:
            logger.exception("Tiered rescrape sweep failed")
