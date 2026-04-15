"""Shared periodic sweep loop for marketplace competition trackers.

Shopee and Carousell (and any future marketplace, e.g. FB Marketplace)
use the exact same cadence logic: every N minutes, look up the tiered
selection of items that are stale on THIS marketplace's snapshots
table, and queue a batch job on the per-marketplace worker. Only the
scraper_id, snapshots table, and logger differ.

This module owns that loop so per-marketplace schedulers collapse to
thin parameter wrappers.

Tier scope is defined in `tiered_selection.py`:
    cart (7d) -> watchlist (7d) -> holdings (14d) -> retiring_soon (30d)

Retired sets are intentionally excluded -- retiring_soon is the
retirement-lifecycle scope for marketplace saturation checks.
"""

from __future__ import annotations

import asyncio
import logging

from api.jobs import JobManager

WARMUP_SECONDS = 60


async def run_marketplace_competition_sweep(
    manager: JobManager,
    *,
    scraper_id: str,
    snapshots_table: str,
    logger: logging.Logger,
    interval_minutes: int,
    batch_size: int,
) -> None:
    """Tiered competition sweep loop for a marketplace.

    Args:
        manager: Job manager used to enqueue batch jobs.
        scraper_id: Worker scraper_id to dispatch to
            (e.g. "shopee_competition", "carousell_competition").
        snapshots_table: The `{platform}_competition_snapshots` table
            used to compute per-item staleness.
        logger: Per-platform logger (so log lines stay attributable).
        interval_minutes: Loop cadence in minutes.
        batch_size: Max items queued per sweep.

    The first sweep fires after a short `WARMUP_SECONDS` delay rather
    than after a full interval, so fresh app startups don't leave the
    sweeper silent for hours.
    """
    logger.info(
        "%s sweep started (warmup=%ds, interval=%dm, batch=%d)",
        scraper_id,
        WARMUP_SECONDS,
        interval_minutes,
        batch_size,
    )

    await asyncio.sleep(WARMUP_SECONDS)

    while True:
        try:
            await _run_one_sweep(
                manager,
                scraper_id=scraper_id,
                snapshots_table=snapshots_table,
                logger=logger,
                batch_size=batch_size,
            )
        except Exception:
            logger.exception("%s sweep iteration failed", scraper_id)

        await asyncio.sleep(interval_minutes * 60)


async def _run_one_sweep(
    manager: JobManager,
    *,
    scraper_id: str,
    snapshots_table: str,
    logger: logging.Logger,
    batch_size: int,
) -> None:
    """Run a single sweep pass: select stale items and queue one batch."""
    existing = manager.list_jobs()
    has_pending = any(
        j.scraper_id == scraper_id and j.status.value in ("queued", "running")
        for j in existing
    )
    if has_pending:
        logger.debug("%s sweep: job already pending, skipping", scraper_id)
        return

    from db.connection import get_connection
    from db.schema import init_schema
    from services.marketplace_competition.tiered_selection import (
        get_tiered_items_needing_check,
    )

    conn = get_connection()
    try:
        init_schema(conn)
        items = get_tiered_items_needing_check(
            conn,
            snapshots_table=snapshots_table,
            limit=batch_size,
        )
    finally:
        conn.close()

    if not items:
        logger.debug("%s sweep: no items need checking", scraper_id)
        return

    tier_counts: dict[int, int] = {}
    for item in items:
        tier_counts[item["priority"]] = tier_counts.get(item["priority"], 0) + 1
    tier_summary = ", ".join(
        f"t{pri}={cnt}" for pri, cnt in sorted(tier_counts.items())
    )

    manager.create_job(
        scraper_id,
        "batch",
        reason=f"scheduled sweep: {len(items)} items stale ({tier_summary})",
    )
    logger.info(
        "%s sweep: %d items need checking (%s), queued batch job",
        scraper_id,
        len(items),
        tier_summary,
    )
