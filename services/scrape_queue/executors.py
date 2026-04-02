"""Scrape task executors -- one function per task type.

Each executor returns an ``ExecutorResult`` (typed, not a raw tuple).
Browser-based executors use ``PersistentBrowser`` to reuse a single
Firefox instance across tasks.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from services.scrape_queue.models import ExecutorResult

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.executor")


# ---------------------------------------------------------------------------
# BrickLink -- tracks consecutive 0-field responses for silent ban detection
# ---------------------------------------------------------------------------


class _BrickLinkBanTracker:
    """Thread-safe tracker for consecutive 0-field BrickLink responses.

    Triggers a "silent ban" cooldown after N consecutive zero-field results,
    indicating BrickLink is serving empty pages without an explicit 429.
    """

    THRESHOLD = 5

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consecutive_zeros = 0

    def record_zero(self) -> bool:
        """Record a 0-field response. Returns True if threshold hit."""
        with self._lock:
            self._consecutive_zeros += 1
            return self._consecutive_zeros >= self.THRESHOLD

    def reset(self) -> None:
        with self._lock:
            self._consecutive_zeros = 0

    @property
    def count(self) -> int:
        with self._lock:
            return self._consecutive_zeros


_bl_ban_tracker = _BrickLinkBanTracker()


def execute_bricklink_metadata(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape BrickLink catalog page and store enrichment fields."""
    from config.settings import BRICKLINK_RATE_LIMITER
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.fetchers import fetch_from_bricklink
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import store_enrichment_result
    from services.enrichment.types import SourceId
    from services.items.repository import get_item_detail

    remaining = BRICKLINK_RATE_LIMITER.cooldown_remaining()
    if remaining > 0:
        logger.info("BrickLink in cooldown -- %d min remaining", int(remaining / 60))
        return ExecutorResult.cooldown(remaining)

    item = get_item_detail(conn, set_number)
    if not item:
        return ExecutorResult.fail(f"Item {set_number} not found in lego_items")

    fetchers = {
        SourceId.BRICKLINK: lambda sn: fetch_from_bricklink(conn, sn),
    }

    cb_state = CircuitBreakerState()
    result, _ = enrich(set_number, item, fetchers, cb_state)

    if result.fields_found == 0:
        if _bl_ban_tracker.record_zero():
            logger.warning(
                "Silent ban detected: %d consecutive 0-field responses "
                "-- tripping circuit breaker",
                _bl_ban_tracker.count,
            )
            BRICKLINK_RATE_LIMITER.trip_silent_ban()
            _bl_ban_tracker.reset()
            return ExecutorResult.cooldown(BRICKLINK_RATE_LIMITER.cooldown_remaining())
        return ExecutorResult.fail("No data returned (0 fields)")

    _bl_ban_tracker.reset()
    BRICKLINK_RATE_LIMITER.record_success()
    store_enrichment_result(conn, result)

    logger.info(
        "BrickLink metadata for %s: %d/%d fields found",
        set_number,
        result.fields_found,
        len(result.field_results),
    )
    return ExecutorResult.ok()


# ---------------------------------------------------------------------------
# BrickEconomy -- browser-based, uses PersistentBrowser
# ---------------------------------------------------------------------------


def execute_brickeconomy(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape BrickEconomy and store enrichment fields + snapshot."""
    from config.settings import BRICKECONOMY_CONFIG
    from services.brickeconomy.scraper import scrape_with_search
    from services.browser import BrowserConfig, get_persistent_browser
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import store_enrichment_result
    from services.enrichment.source_adapter import adapt_brickeconomy, make_failed_result
    from services.enrichment.types import SourceId
    from services.items.repository import get_item_detail

    item = get_item_detail(conn, set_number)
    if not item:
        return ExecutorResult.fail(f"Item {set_number} not found in lego_items")

    browser = get_persistent_browser(BrowserConfig(
        profile_name="brickeconomy",
        headless=BRICKECONOMY_CONFIG.headless,
        locale=BRICKECONOMY_CONFIG.locale,
    ))

    def _fetch_be(sn: str):
        from services.brickeconomy.repository import record_current_value, save_snapshot

        scrape_result = browser.run(scrape_with_search, sn)

        if not scrape_result.success:
            return make_failed_result(SourceId.BRICKECONOMY, scrape_result.error or "Unknown error")
        if scrape_result.snapshot is None:
            return make_failed_result(SourceId.BRICKECONOMY, "No data returned")

        save_snapshot(conn, scrape_result.snapshot)
        record_current_value(conn, scrape_result.snapshot)
        return adapt_brickeconomy(scrape_result.snapshot)

    fetchers = {SourceId.BRICKECONOMY: _fetch_be}
    cb_state = CircuitBreakerState()
    result, _ = enrich(set_number, item, fetchers, cb_state)

    if result.fields_found == 0:
        browser.restart()
        return ExecutorResult.fail("BrickEconomy returned no data (0 fields)")

    store_enrichment_result(conn, result)

    logger.info(
        "BrickEconomy for %s: %d/%d fields found",
        set_number,
        result.fields_found,
        len(result.field_results),
    )
    return ExecutorResult.ok()


# ---------------------------------------------------------------------------
# Keepa -- browser-based, uses PersistentBrowser
# ---------------------------------------------------------------------------


def execute_keepa(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape Keepa for Amazon price history."""
    from config.settings import KEEPA_CONFIG
    from services.browser import BrowserConfig, get_persistent_browser
    from services.keepa.repository import record_keepa_prices, save_keepa_snapshot
    from services.keepa.scheduler import record_keepa_failure, record_keepa_success
    from services.keepa.scraper import scrape_with_page

    browser = get_persistent_browser(BrowserConfig(
        profile_name=f"keepa-{worker_index}",
        headless=KEEPA_CONFIG.headless,
        locale=KEEPA_CONFIG.locale,
        window=(KEEPA_CONFIG.viewport_width, KEEPA_CONFIG.viewport_height),
    ))

    try:
        result = browser.run(scrape_with_page, set_number)
    except Exception as exc:
        record_keepa_failure(set_number)
        browser.restart()
        return ExecutorResult.fail(str(exc))

    if not result.success:
        record_keepa_failure(set_number)
        browser.restart()
        return ExecutorResult.fail(result.error or "Keepa scrape failed")

    record_keepa_success(set_number)
    try:
        save_keepa_snapshot(conn, result.product_data)
    except Exception:
        logger.error("Keepa snapshot insert failed for %s", set_number, exc_info=True)
        return ExecutorResult.fail("Failed to save Keepa snapshot")
    record_keepa_prices(conn, result.product_data)

    logger.info("Keepa for %s: OK", set_number)
    return ExecutorResult.ok()


# ---------------------------------------------------------------------------
# Minifigures
# ---------------------------------------------------------------------------


def execute_minifigures(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape BrickLink minifigure inventory and individual minifig pages."""
    from services.bricklink.scraper import scrape_set_minifigures_sync
    from services.enrichment.config import PRICING_FRESHNESS

    item_id = f"{set_number}-1"

    bl_row = conn.execute(
        "SELECT item_id FROM bricklink_items WHERE item_id = ?",
        [item_id],
    ).fetchone()
    if not bl_row:
        return ExecutorResult.fail(
            f"BrickLink item {item_id} not found (metadata not scraped?)"
        )

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
    return ExecutorResult.ok()


# ---------------------------------------------------------------------------
# Google Trends -- thread-safe cooldown tracker
# ---------------------------------------------------------------------------


class _TrendsCooldown:
    """Thread-safe cooldown state for Google Trends rate limiting.

    Only enters cooldown on actual rate-limit responses (429), not on
    data errors like invalid year_released values.
    """

    DURATION_SECONDS = 3600

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_failure_at: float | None = None

    def remaining(self) -> float:
        """Seconds remaining in cooldown, or 0 if inactive."""
        with self._lock:
            if self._last_failure_at is None:
                return 0.0
            elapsed = time.time() - self._last_failure_at
            return max(self.DURATION_SECONDS - elapsed, 0.0)

    def activate(self) -> None:
        """Enter cooldown (called on rate-limit only)."""
        with self._lock:
            self._last_failure_at = time.time()
        logger.warning(
            "Google Trends rate limited -- entering %ds cooldown",
            self.DURATION_SECONDS,
        )

    def clear(self) -> None:
        """Clear cooldown after a successful request."""
        with self._lock:
            self._last_failure_at = None


_trends_cooldown = _TrendsCooldown()


def get_trends_cooldown_remaining() -> float:
    """Public accessor for the dispatcher timeout handler."""
    return _trends_cooldown.remaining()


def execute_google_trends(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Fetch Google Trends interest data for a LEGO set."""
    from datetime import datetime, timedelta, timezone

    from services.enrichment.config import is_placeholder_title
    from services.google_trends.repository import save_trends_snapshot
    from services.google_trends.scraper import fetch_interest

    # Check cooldown
    remaining = _trends_cooldown.remaining()
    if remaining > 0:
        return ExecutorResult.cooldown(remaining)

    # Prerequisites
    item_row = conn.execute(
        "SELECT title, year_released FROM lego_items WHERE set_number = ?",
        [set_number],
    ).fetchone()
    if not item_row or not item_row[0] or not item_row[1]:
        return ExecutorResult.fail("Missing title or year_released")

    title, year_released = item_row[0], int(item_row[1])
    if is_placeholder_title(title):
        return ExecutorResult.fail("Placeholder title")

    # Freshness check
    row = conn.execute(
        """SELECT scraped_at FROM google_trends_snapshots
           WHERE set_number = ?
           ORDER BY scraped_at DESC LIMIT 1""",
        [set_number],
    ).fetchone()
    if row and row[0]:
        scraped_at = row[0]
        if isinstance(scraped_at, str):
            from db.queries import parse_timestamp
            scraped_at = parse_timestamp(scraped_at)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)
        if scraped_at and scraped_at > cutoff:
            return ExecutorResult.ok()  # Already fresh

    # Fetch
    trends_result = fetch_interest(set_number, year_released=year_released)
    if not trends_result.success:
        if trends_result.rate_limited:
            _trends_cooldown.activate()
            return ExecutorResult.cooldown(_trends_cooldown.DURATION_SECONDS)
        return ExecutorResult.fail(
            trends_result.error or "Google Trends fetch failed"
        )

    save_trends_snapshot(conn, trends_result.data)
    _trends_cooldown.clear()

    logger.info(
        "Google Trends for %s: %d pts, peak=%s",
        set_number,
        len(trends_result.data.interest_over_time),
        trends_result.data.peak_value,
    )
    return ExecutorResult.ok()
