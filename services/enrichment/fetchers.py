"""Async fetcher wrappers that bridge existing scrapers to the enrichment orchestrator.

Each fetcher:
1. Checks local cache first (zero-cost DB lookup)
2. Falls back to HTTP scrape if cache is stale or missing
3. Returns a unified SourceResult
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from services.enrichment.source_adapter import (
    adapt_bricklink,
    adapt_brickranker,
    adapt_worldbricks,
    make_failed_result,
)
from services.enrichment.types import SourceId, SourceResult

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.enrichment.fetchers")

# Default freshness: skip HTTP if cached data is younger than this
_DEFAULT_FRESHNESS = timedelta(hours=24)


def fetch_from_bricklink(
    conn: "DuckDBPyConnection",
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
                   last_scraped_at
            FROM bricklink_items
            WHERE item_id = ? OR item_id = ?
            ORDER BY last_scraped_at DESC NULLS LAST
            LIMIT 1
            """,
            [set_number, f"{set_number}-1"],
        ).fetchone()

        if row and row[6] is not None:
            scraped_at = row[6]
            if isinstance(scraped_at, str):
                from db.queries import parse_timestamp
                scraped_at = parse_timestamp(scraped_at)
            if scraped_at and (datetime.now(tz=timezone.utc) - scraped_at) < freshness:
                from bws_types.models import BricklinkData
                cached = BricklinkData(
                    item_id=row[0],
                    item_type=row[1],
                    title=row[2],
                    weight=row[3],
                    year_released=row[4],
                    image_url=row[5],
                )
                logger.info("Bricklink cache hit for %s (age: %s)", set_number, datetime.now(tz=timezone.utc) - scraped_at)
                return adapt_bricklink(cached)
    except Exception:
        logger.debug("Bricklink cache lookup failed for %s, falling back to HTTP", set_number, exc_info=True)

    # HTTP scrape
    try:
        from services.bricklink.scraper import scrape_item_sync
        from services.bricklink.parser import build_price_guide_url

        url = build_price_guide_url("S", f"{set_number}-1")
        scrape_result = scrape_item_sync(conn, url, save=True)

        if not scrape_result.success:
            return make_failed_result(SourceId.BRICKLINK, scrape_result.error or "Unknown error")

        if scrape_result.data is None:
            return make_failed_result(SourceId.BRICKLINK, "No data returned")

        return adapt_bricklink(scrape_result.data)

    except Exception as e:
        logger.exception("Bricklink fetch failed for %s", set_number)
        return make_failed_result(SourceId.BRICKLINK, str(e))


def fetch_from_worldbricks(
    conn: "DuckDBPyConnection",
    set_number: str,
    *,
    freshness: timedelta = _DEFAULT_FRESHNESS,
) -> SourceResult:
    """Fetch metadata from WorldBricks (cache-first, then HTTP)."""
    # Check cache: worldbricks_sets table
    try:
        from services.worldbricks.repository import get_set

        cached = get_set(conn, set_number)
        if cached and cached.get("scraped_at"):
            scraped_at = cached["scraped_at"]
            if isinstance(scraped_at, datetime) and (datetime.now(tz=timezone.utc) - scraped_at) < freshness:
                from services.worldbricks.parser import WorldBricksData
                wb_data = WorldBricksData(
                    set_number=cached["set_number"],
                    set_name=cached.get("set_name"),
                    year_released=cached.get("year_released"),
                    year_retired=cached.get("year_retired"),
                    parts_count=cached.get("parts_count"),
                    dimensions=cached.get("dimensions"),
                    image_url=cached.get("image_url"),
                )
                logger.info("WorldBricks cache hit for %s", set_number)
                return adapt_worldbricks(wb_data)
    except Exception:
        logger.debug("WorldBricks cache lookup failed for %s, falling back to HTTP", set_number, exc_info=True)

    # HTTP scrape
    try:
        from services.worldbricks.scraper import scrape_set_sync

        scrape_result = scrape_set_sync(conn, set_number, save=True)

        if not scrape_result.success:
            return make_failed_result(SourceId.WORLDBRICKS, scrape_result.error or "Unknown error")

        if scrape_result.data is None:
            return make_failed_result(SourceId.WORLDBRICKS, "No data returned")

        return adapt_worldbricks(scrape_result.data)

    except Exception as e:
        logger.exception("WorldBricks fetch failed for %s", set_number)
        return make_failed_result(SourceId.WORLDBRICKS, str(e))


def fetch_from_brickranker(
    conn: "DuckDBPyConnection",
    set_number: str,
    *,
    freshness: timedelta = _DEFAULT_FRESHNESS,
) -> SourceResult:
    """Fetch metadata from BrickRanker (cache-first, then HTTP).

    BrickRanker is a bulk scraper -- it fetches ALL retirement items at once.
    So we strongly prefer cache to avoid unnecessary full-page scrapes.
    """
    # Check cache: brickranker_items table
    try:
        from services.brickranker.repository import get_item

        cached = get_item(conn, set_number)
        if cached and cached.get("scraped_at"):
            scraped_at = cached["scraped_at"]
            if isinstance(scraped_at, datetime) and (datetime.now(tz=timezone.utc) - scraped_at) < freshness:
                from services.brickranker.parser import RetirementItem
                br_item = RetirementItem(
                    set_number=cached["set_number"],
                    set_name=cached.get("set_name", ""),
                    year_released=cached.get("year_released"),
                    retiring_soon=cached.get("retiring_soon", False),
                    expected_retirement_date=cached.get("expected_retirement_date"),
                    theme=cached.get("theme"),
                    image_url=cached.get("image_url"),
                )
                logger.info("BrickRanker cache hit for %s", set_number)
                return adapt_brickranker(br_item)
    except Exception:
        logger.debug("BrickRanker cache lookup failed for %s, falling back to HTTP", set_number, exc_info=True)

    # HTTP scrape (bulk -- scrapes all items)
    try:
        from services.brickranker.scraper import scrape_retirement_tracker_sync

        scrape_result = scrape_retirement_tracker_sync(conn, save=True)

        if not scrape_result.success:
            return make_failed_result(SourceId.BRICKRANKER, scrape_result.error or "Unknown error")

        if scrape_result.data is None:
            return make_failed_result(SourceId.BRICKRANKER, "No data returned")

        # Find the specific set in results
        for item in scrape_result.data.items:
            if item.set_number == set_number:
                return adapt_brickranker(item)

        # Set not found in retirement tracker (not retiring)
        from services.brickranker.parser import RetirementItem
        return adapt_brickranker(RetirementItem(
            set_number=set_number,
            set_name="",
            retiring_soon=False,
        ))

    except Exception as e:
        logger.exception("BrickRanker fetch failed for %s", set_number)
        return make_failed_result(SourceId.BRICKRANKER, str(e))
