"""Logged-in browser-based BrickLink scraper.

Replaces the anonymous HTTPX-based scrape path with a single Camoufox
session that holds the user's BrickLink login.  One scrape fetches two
pages:

1. ``v2/catalog/catalogitem.page?S=<item_id>#T=P`` -- item metadata and
   per-store listings (with seller country + ships-to-viewer signal).
2. ``catalogPG.asp?S=<item_id>`` -- legacy price-guide HTML that the
   existing ``parse_price_guide`` / ``parse_monthly_sales`` parsers
   already understand.

Both raw HTMLs are archived to ``logs/bricklink_raw/`` (append-only)
for future debugging.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from config.settings import BRICKLINK_RATE_LIMITER
from bws_types.models import BricklinkData, MonthlySale
from services.bricklink.listings_browser import (
    PROFILE_DIR,
    get_listings_browser,
    profile_exists,
)
from services.bricklink.listings_parser import (
    EXTRACT_JS,
    BricklinkListing,
    build_listings_url,
    parse_listings,
)
from services.bricklink.parser import (
    build_price_guide_url,
    parse_item_info,
    parse_monthly_sales,
    parse_price_guide,
)
from services.bricklink.raw_archive import save_raw_html
from services.bricklink.repository import (
    create_price_history,
    insert_store_listings_snapshot,
    upsert_item,
    upsert_monthly_sales,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("bws.bricklink.browser_scraper")


# Selectors we wait on before scraping each page.  Use static DOM markers
# that are present whenever the page rendered at all, so we don't hang 25s
# waiting on AJAX-injected content that may legitimately be absent for sets
# with no sales history (unreleased, newly added, or otherwise empty).
#
# _idPGContents is the server-rendered wrapper div on the v2
# catalogitem.page and appears before the PG AJAX call completes, so it's
# the earliest reliable "PG section exists" marker.
#
# On the legacy catalogPG.asp page the price-boxes row uses the HTML
# bgcolor attribute when the set has data and is simply absent when it
# does not -- the parser now handles both cases gracefully, so the wait is
# best-effort.
_V2_WAIT_SELECTOR = "div#_idPGContents"
_PG_WAIT_SELECTOR = "tr[bgcolor='#C0C0C0']"
_V2_WAIT_TIMEOUT_MS = 15_000
_PG_WAIT_TIMEOUT_MS = 8_000


class BrowserProfileMissing(RuntimeError):
    """Raised if the Camoufox profile has not been logged in yet."""


@dataclass(frozen=True)
class BrowserFetchResult:
    """What the async browser coro returns (pre-DB)."""

    item_id: str
    data: BricklinkData | None
    monthly_sales: tuple[MonthlySale, ...] = ()
    listings: tuple[BricklinkListing, ...] = ()
    v2_html_bytes: int = 0
    pg_html_bytes: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BrowserScrapeResult:
    """Result of a full scrape + persist cycle."""

    success: bool
    item_id: str
    data: BricklinkData | None = None
    monthly_sales: tuple[MonthlySale, ...] = ()
    listings: tuple[BricklinkListing, ...] = ()
    error: str | None = None
    listings_inserted: int = 0


def _item_id_for(set_number: str) -> str:
    """Normalise a set number into BrickLink's ``<set>-1`` item id."""
    return set_number if "-" in set_number else f"{set_number}-1"


async def fetch_item_browser(page: "Page", set_number: str) -> BrowserFetchResult:
    """Fetch + parse BrickLink data for a set via the authed browser.

    Does NOT touch the database -- caller is responsible for persistence.
    """
    item_id = _item_id_for(set_number)
    errors: list[str] = []

    # ---- 1. v2 catalog page (item metadata + listings) ----
    v2_url = build_listings_url(item_id)
    await BRICKLINK_RATE_LIMITER.acquire()
    logger.info("Navigating to %s", v2_url)
    await page.goto(v2_url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(_V2_WAIT_SELECTOR, timeout=_V2_WAIT_TIMEOUT_MS)
    except Exception as exc:
        errors.append(f"v2 selector timeout: {exc}")
        logger.info("v2 selector wait timed out for %s: %s", item_id, exc)

    await asyncio.sleep(0.4)
    v2_html = await page.content()
    save_raw_html(item_id, "v2", v2_html)

    item_info: dict[str, Any] = {}
    try:
        item_info = parse_item_info(v2_html)
    except Exception as exc:
        errors.append(f"parse_item_info: {exc}")
        logger.warning("parse_item_info failed for %s: %s", item_id, exc)

    listings: list[BricklinkListing] = []
    try:
        raw_rows = await page.evaluate(EXTRACT_JS)
        listings = parse_listings(item_id, raw_rows)
        logger.info(
            "Extracted %d store listings for %s", len(listings), item_id,
        )
    except Exception as exc:
        errors.append(f"listings extract: {exc}")
        logger.warning("EXTRACT_JS failed for %s: %s", item_id, exc)

    # ---- 2. legacy catalogPG.asp (price boxes + monthly sales) ----
    pg_url = build_price_guide_url("S", item_id)
    await BRICKLINK_RATE_LIMITER.acquire()
    logger.info("Navigating to %s", pg_url)
    await page.goto(pg_url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(_PG_WAIT_SELECTOR, timeout=_PG_WAIT_TIMEOUT_MS)
    except Exception as exc:
        # Expected for sets with no sales history -- the price-boxes row
        # is simply absent. parse_price_guide returns all-None instead of
        # raising, so this is informational, not a failure.
        logger.info("pg selector wait timed out for %s (likely no price data): %s", item_id, exc)

    pg_html = await page.content()
    save_raw_html(item_id, "pg", pg_html)

    pricing: dict[str, Any] = {
        "six_month_new": None,
        "six_month_used": None,
        "current_new": None,
        "current_used": None,
    }
    try:
        pricing = parse_price_guide(pg_html)
    except ValueError as exc:
        errors.append(f"parse_price_guide: {exc}")
        logger.warning("parse_price_guide failed for %s: %s", item_id, exc)

    monthly_sales_list = []
    try:
        parsed_sales = parse_monthly_sales(pg_html)
        monthly_sales_list = [
            MonthlySale(
                item_id=item_id,
                year=s.year,
                month=s.month,
                condition=s.condition,
                times_sold=s.times_sold,
                total_quantity=s.total_quantity,
                min_price=s.min_price,
                max_price=s.max_price,
                avg_price=s.avg_price,
                currency=s.currency,
            )
            for s in parsed_sales
        ]
    except Exception as exc:
        errors.append(f"parse_monthly_sales: {exc}")
        logger.warning("parse_monthly_sales failed for %s: %s", item_id, exc)

    data = BricklinkData(
        item_id=item_id,
        item_type="S",
        title=item_info.get("title"),
        weight=item_info.get("weight"),
        year_released=item_info.get("year_released"),
        image_url=item_info.get("image_url"),
        parts_count=item_info.get("parts_count"),
        theme=item_info.get("theme"),
        minifig_count=item_info.get("minifig_count"),
        dimensions=item_info.get("dimensions"),
        has_instructions=item_info.get("has_instructions"),
        six_month_new=pricing.get("six_month_new"),
        six_month_used=pricing.get("six_month_used"),
        current_new=pricing.get("current_new"),
        current_used=pricing.get("current_used"),
    )

    return BrowserFetchResult(
        item_id=item_id,
        data=data,
        monthly_sales=tuple(monthly_sales_list),
        listings=tuple(listings),
        v2_html_bytes=len(v2_html),
        pg_html_bytes=len(pg_html),
        errors=tuple(errors),
    )


def scrape_item_browser_sync(
    conn: Any,
    set_number: str,
    *,
    save: bool = True,
    skip_pricing: bool = False,
    headless: bool = True,
    timeout: float = 180.0,
) -> BrowserScrapeResult:
    """Sync entrypoint mirroring the shape of the old ``scrape_item_sync``.

    Uses the persistent ``bricklink-listings`` Camoufox profile (must be
    logged in via ``scripts/bricklink_login`` first).

    Args:
        conn: Database connection.
        set_number: Set number, e.g. ``"10857-1"`` or bare ``"10857"``.
        save: Whether to persist the parsed data.
        skip_pricing: Skip ``create_price_history`` / monthly sales writes
            (used for cache-warming paths).
        headless: Run the browser headless (default True).
        timeout: Per-set timeout in seconds for the browser run.
    """
    item_id = _item_id_for(set_number)

    if not profile_exists():
        raise BrowserProfileMissing(
            f"BrickLink camoufox profile {PROFILE_DIR} does not exist -- "
            "run `python -m scripts.bricklink_login` first.",
        )

    browser = get_listings_browser(headless=headless)
    reuse = browser.is_alive
    logger.info(
        "BrickLink browser %s for %s",
        "reusing existing session" if reuse else "launching new session",
        item_id,
    )

    try:
        fetch: BrowserFetchResult = browser.run(
            fetch_item_browser, set_number, timeout=timeout,
        )
    except Exception as exc:
        logger.exception("Browser scrape failed for %s", item_id)
        return BrowserScrapeResult(
            success=False, item_id=item_id, error=f"browser run: {exc}",
        )

    if fetch.data is None:
        return BrowserScrapeResult(
            success=False,
            item_id=item_id,
            error="; ".join(fetch.errors) or "no data parsed",
        )

    # Soft-degraded detection (mirrors old scraper behaviour)
    metadata_empty = (
        fetch.data.title is None
        and fetch.data.year_released is None
        and fetch.data.theme is None
    )
    pricing_empty = (
        fetch.data.six_month_new is None
        and fetch.data.six_month_used is None
        and fetch.data.current_new is None
        and fetch.data.current_used is None
    )
    if metadata_empty:
        logger.warning(
            "Degraded metadata for %s (title/year/theme all None)", item_id,
        )
    if pricing_empty:
        logger.warning(
            "Degraded pricing for %s (all boxes None)", item_id,
        )

    listings_inserted = 0
    if save:
        upsert_item(conn, fetch.data)
        if not skip_pricing:
            create_price_history(conn, item_id, fetch.data)
            if fetch.monthly_sales:
                upsert_monthly_sales(conn, item_id, list(fetch.monthly_sales))
        if fetch.listings:
            listings_inserted = insert_store_listings_snapshot(
                conn,
                item_id,
                list(fetch.listings),
                scraped_at=datetime.now(),
            )
            logger.info(
                "Inserted %d store listings for %s",
                listings_inserted, item_id,
            )

    # Only reset the rate-limiter escalation counter if we actually got
    # usable data (mirrors the old _fetch_page success-path behaviour).
    if not pricing_empty:
        BRICKLINK_RATE_LIMITER.record_success()

    return BrowserScrapeResult(
        success=True,
        item_id=item_id,
        data=fetch.data,
        monthly_sales=fetch.monthly_sales,
        listings=fetch.listings,
        listings_inserted=listings_inserted,
        error="; ".join(fetch.errors) or None,
    )
