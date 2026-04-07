"""Async fetcher wrappers that bridge existing scrapers to the enrichment orchestrator.

Each fetcher:
1. Checks local cache first (zero-cost DB lookup)
2. Falls back to HTTP scrape if cache is stale or missing
3. Returns a unified SourceResult
"""

import logging
from datetime import datetime, timedelta, timezone

from services.enrichment.source_adapter import (
    adapt_brickeconomy,
    adapt_bricklink,
    make_failed_result,
)
from services.enrichment.types import SourceId, SourceResult
from typing import Any


logger = logging.getLogger("bws.enrichment.fetchers")

# Default freshness: skip HTTP if cached data is younger than this
_DEFAULT_FRESHNESS = timedelta(hours=24)


def fetch_from_bricklink(
    conn: Any,
    set_number: str,
    *,
    freshness: timedelta = _DEFAULT_FRESHNESS,
) -> SourceResult:
    """Fetch metadata from Bricklink (cache-first, then HTTP).

    Uses synchronous scraper since enrichment runs in a background worker.
    """
    # Check cache: bricklink_items table
    try:
        row = conn.execute(
            """
            SELECT item_id, item_type, title, weight, year_released, image_url,
                   parts_count, theme, last_scraped_at, minifig_count, dimensions
            FROM bricklink_items
            WHERE item_id = ? OR item_id = ?
            ORDER BY last_scraped_at DESC NULLS LAST
            LIMIT 1
            """,
            [set_number, f"{set_number}-1"],
        ).fetchone()

        if row and row[8] is not None:
            from db.queries import is_fresh

            if is_fresh(row[8], freshness):
                from bws_types.models import BricklinkData
                cached = BricklinkData(
                    item_id=row[0],
                    item_type=row[1],
                    title=row[2],
                    weight=row[3],
                    year_released=row[4],
                    image_url=row[5],
                    parts_count=row[6],
                    theme=row[7],
                    minifig_count=row[9],
                    dimensions=row[10],
                )
                logger.info("Bricklink cache hit for %s (last_scraped: %s)", set_number, row[8])
                return adapt_bricklink(cached)
    except Exception:
        logger.debug("Bricklink cache lookup failed for %s, falling back to HTTP", set_number, exc_info=True)

    # Short-circuit if BrickLink quota cooldown is active
    from config.settings import BRICKLINK_RATE_LIMITER

    if BRICKLINK_RATE_LIMITER.is_blocked():
        logger.warning("BrickLink quota cooldown active, skipping HTTP for %s", set_number)
        return make_failed_result(SourceId.BRICKLINK, "Quota cooldown active")

    # HTTP scrape
    try:
        from services.bricklink.repository import has_recent_pricing
        from services.bricklink.scraper import scrape_item_sync
        from services.bricklink.parser import build_price_guide_url
        from services.enrichment.config import PRICING_FRESHNESS

        item_id = f"{set_number}-1"
        skip_pricing = has_recent_pricing(conn, item_id, PRICING_FRESHNESS)
        if skip_pricing:
            logger.info("Skipping pricing write for %s (fresh within 7 days)", set_number)

        url = build_price_guide_url("S", f"{set_number}-1")
        scrape_result = scrape_item_sync(conn, url, save=True, skip_pricing=skip_pricing)

        if not scrape_result.success:
            return make_failed_result(SourceId.BRICKLINK, scrape_result.error or "Unknown error")

        if scrape_result.data is None:
            return make_failed_result(SourceId.BRICKLINK, "No data returned")

        result = adapt_bricklink(scrape_result.data)
        non_null_fields = [k.value for k, v in result.fields.items() if v is not None]
        null_fields = [k.value for k, v in result.fields.items() if v is None]
        if null_fields:
            logger.info(
                "BrickLink for %s: got %d fields (%s), missing %d (%s)",
                set_number, len(non_null_fields), non_null_fields,
                len(null_fields), null_fields,
            )
        return result

    except Exception as e:
        logger.exception("Bricklink fetch failed for %s", set_number)
        return make_failed_result(SourceId.BRICKLINK, str(e))


def fetch_from_brickeconomy(
    conn: Any,
    set_number: str,
    *,
    freshness: timedelta = _DEFAULT_FRESHNESS,
) -> SourceResult:
    """Fetch metadata from BrickEconomy (cache-first, then browser scrape).

    Also saves the snapshot and records the current value as a side effect,
    mirroring the standalone BrickEconomy worker behaviour.
    """
    # Check cache: brickeconomy_snapshots table
    try:
        from services.brickeconomy.repository import get_latest_snapshot

        cached = get_latest_snapshot(conn, set_number)
        if cached and cached.get("scraped_at"):
            from db.queries import is_fresh

            if is_fresh(cached["scraped_at"], freshness):
                from services.brickeconomy.parser import BrickeconomySnapshot
                snapshot = BrickeconomySnapshot(
                    set_number=cached["set_number"],
                    scraped_at=cached["scraped_at"],
                    title=cached.get("title"),
                    theme=cached.get("theme"),
                    subtheme=cached.get("subtheme"),
                    year_released=cached.get("year_released"),
                    pieces=cached.get("pieces"),
                    minifigs=cached.get("minifigs"),
                    availability=cached.get("availability"),
                    image_url=cached.get("image_url"),
                    brickeconomy_url=cached.get("brickeconomy_url"),
                    value_new_cents=cached.get("value_new_cents"),
                    value_used_cents=cached.get("value_used_cents"),
                )
                logger.info("BrickEconomy cache hit for %s", set_number)
                return adapt_brickeconomy(snapshot)
    except Exception:
        logger.debug("BrickEconomy cache lookup failed for %s, falling back to scrape", set_number, exc_info=True)

    # Browser scrape
    try:
        from services.brickeconomy.repository import record_current_value, save_snapshot
        from services.brickeconomy.scraper import scrape_set_sync

        scrape_result = scrape_set_sync(set_number)

        if not scrape_result.success:
            return make_failed_result(SourceId.BRICKECONOMY, scrape_result.error or "Unknown error")

        if scrape_result.snapshot is None:
            return make_failed_result(SourceId.BRICKECONOMY, "No data returned")

        # Persist snapshot and price record (same as standalone worker)
        save_snapshot(conn, scrape_result.snapshot)
        record_current_value(conn, scrape_result.snapshot)

        return adapt_brickeconomy(scrape_result.snapshot)

    except Exception as e:
        logger.exception("BrickEconomy fetch failed for %s", set_number)
        return make_failed_result(SourceId.BRICKECONOMY, str(e))


