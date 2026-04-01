"""Scrape task executors -- one function per task type.

Each executor is extracted from the monolithic enrichment worker and reuses
existing fetchers/scrapers.  Every executor returns ``(success, error)``.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.executor")


def execute_bricklink_metadata(
    conn: DuckDBPyConnection,
    set_number: str,
) -> tuple[bool, str | None]:
    """Scrape BrickLink catalog page and store enrichment fields.

    Also calls BrickRanker (bulk, cache-first) for retirement data.
    """
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.fetchers import (
        fetch_from_bricklink,
        fetch_from_brickranker,
    )
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import store_enrichment_result
    from services.enrichment.types import SourceId
    from services.items.repository import get_item_detail

    item = get_item_detail(conn, set_number)
    if not item:
        return False, f"Item {set_number} not found in lego_items"

    fetchers = {
        SourceId.BRICKLINK: lambda sn: fetch_from_bricklink(conn, sn),
        SourceId.BRICKRANKER: lambda sn: fetch_from_brickranker(conn, sn),
    }

    cb_state = CircuitBreakerState()
    result, _ = enrich(set_number, item, fetchers, cb_state)
    store_enrichment_result(conn, result)

    logger.info(
        "BrickLink metadata for %s: %d/%d fields found",
        set_number,
        result.fields_found,
        len(result.field_results),
    )
    return True, None


def execute_brickeconomy(
    conn: DuckDBPyConnection,
    set_number: str,
) -> tuple[bool, str | None]:
    """Scrape BrickEconomy and store enrichment fields + snapshot."""
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.fetchers import fetch_from_brickeconomy
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import store_enrichment_result
    from services.enrichment.types import SourceId
    from services.items.repository import get_item_detail

    item = get_item_detail(conn, set_number)
    if not item:
        return False, f"Item {set_number} not found in lego_items"

    fetchers = {
        SourceId.BRICKECONOMY: lambda sn: fetch_from_brickeconomy(conn, sn),
    }

    cb_state = CircuitBreakerState()
    result, _ = enrich(set_number, item, fetchers, cb_state)
    store_enrichment_result(conn, result)

    logger.info(
        "BrickEconomy for %s: %d/%d fields found",
        set_number,
        result.fields_found,
        len(result.field_results),
    )
    return True, None


def execute_keepa(
    conn: DuckDBPyConnection,
    set_number: str,
) -> tuple[bool, str | None]:
    """Scrape Keepa for Amazon price history.

    Called from a sync thread (via asyncio.to_thread), so asyncio.run()
    is safe and correct -- no event loop exists in this thread.
    """
    import asyncio

    from services.keepa.repository import record_keepa_prices, save_keepa_snapshot
    from services.keepa.scheduler import record_keepa_failure, record_keepa_success
    from services.keepa.scraper import scrape_keepa

    try:
        result = asyncio.run(scrape_keepa(set_number))
    except Exception as exc:
        record_keepa_failure(set_number)
        return False, str(exc)

    if not result.success:
        record_keepa_failure(set_number)
        return False, result.error or "Keepa scrape failed"

    record_keepa_success(set_number)
    save_keepa_snapshot(conn, result.product_data)
    record_keepa_prices(conn, result.product_data)

    logger.info("Keepa for %s: OK", set_number)
    return True, None


def execute_minifigures(
    conn: DuckDBPyConnection,
    set_number: str,
) -> tuple[bool, str | None]:
    """Scrape BrickLink minifigure inventory and individual minifig pages."""
    from services.bricklink.scraper import scrape_set_minifigures_sync
    from services.enrichment.config import PRICING_FRESHNESS

    item_id = f"{set_number}-1"

    bl_row = conn.execute(
        "SELECT item_id FROM bricklink_items WHERE item_id = ?",
        [item_id],
    ).fetchone()
    if not bl_row:
        return False, f"BrickLink item {item_id} not found (metadata not scraped?)"

    mf_result = scrape_set_minifigures_sync(
        conn, item_id, save=True, scrape_prices=True,
        pricing_freshness=PRICING_FRESHNESS,
    )
    logger.info(
        "Minifigures for %s: %d/%d scraped",
        set_number,
        mf_result.minifigures_scraped,
        mf_result.minifig_count,
    )
    return True, None


# Google Trends rate-limit cooldown (module-level, thread-safe).
_TRENDS_COOLDOWN_SECONDS = 3600
_trends_lock = threading.Lock()
_trends_last_failure_at: float | None = None


def execute_google_trends(
    conn: DuckDBPyConnection,
    set_number: str,
) -> tuple[bool, str | None]:
    """Fetch Google Trends interest data for a LEGO set."""
    from datetime import datetime, timedelta, timezone

    from services.enrichment.config import is_placeholder_title
    from services.google_trends.repository import save_trends_snapshot
    from services.google_trends.scraper import fetch_interest

    global _trends_last_failure_at  # noqa: PLW0603

    # Check cooldown (thread-safe)
    with _trends_lock:
        if _trends_last_failure_at is not None:
            elapsed = time.time() - _trends_last_failure_at
            if elapsed < _TRENDS_COOLDOWN_SECONDS:
                return False, f"Google Trends cooldown ({_TRENDS_COOLDOWN_SECONDS - elapsed:.0f}s remaining)"

    # Get prerequisites from DB
    item_row = conn.execute(
        "SELECT title, year_released FROM lego_items WHERE set_number = ?",
        [set_number],
    ).fetchone()
    if not item_row or not item_row[0] or not item_row[1]:
        return False, "Missing title or year_released"

    title, year_released = item_row[0], int(item_row[1])
    if is_placeholder_title(title):
        return False, "Placeholder title"

    # Check freshness
    row = conn.execute(
        """
        SELECT scraped_at FROM google_trends_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC LIMIT 1
        """,
        [set_number],
    ).fetchone()
    if row and row[0]:
        scraped_at = row[0]
        if isinstance(scraped_at, str):
            from db.queries import parse_timestamp
            scraped_at = parse_timestamp(scraped_at)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)
        if scraped_at and scraped_at > cutoff:
            return True, None  # Already fresh

    # Fetch
    trends_result = fetch_interest(set_number, year_released=year_released)
    if not trends_result.success:
        with _trends_lock:
            _trends_last_failure_at = time.time()
        return False, trends_result.error or "Google Trends fetch failed"

    save_trends_snapshot(conn, trends_result.data)
    with _trends_lock:
        _trends_last_failure_at = None

    logger.info(
        "Google Trends for %s: %d pts, peak=%s",
        set_number,
        len(trends_result.data.interest_over_time),
        trends_result.data.peak_value,
    )
    return True, None
