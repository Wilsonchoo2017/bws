"""Batch Shopee competition scraper for portfolio items.

Searches Shopee for each portfolio LEGO set, captures per-listing data,
and revisits previously-known URLs that no longer appear in search results.
Reuses the existing saturation scraper infrastructure (Camoufox, anti-ban).
"""

import asyncio
import logging
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Union
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, Page

from config.settings import (
    COMPETITION_CONFIG,
    SATURATION_CONFIG,
    calculate_backoff,
    get_random_delay,
)
from services.enrichment.circuit_breaker import (
    CircuitBreakerState,
    is_available,
    record_failure,
    record_success,
)
from services.shopee.browser import human_delay, new_page, shopee_browser
from services.shopee.competition_types import (
    CompetitionBatchResult,
    CompetitionListing,
    CompetitionSnapshot,
)
from services.shopee.parser import ShopeeProduct, parse_search_results, parse_sold_count
from services.shopee.popups import (
    dismiss_popups,
    dismiss_popups_loop,
    select_english,
    setup_dialog_handler,
)
from services.shopee.repository import _parse_price_cents
from services.shopee.saturation_scorer import (
    compute_saturation,
    filter_relevant_products,
)
from services.shopee.saturation_scraper import _enrich_with_shop_ids

logger = logging.getLogger("bws.shopee.competition")

SHOPEE_SEARCH_URL = "https://shopee.com.my/search?keyword={query}"
SOURCE_ID = "shopee_competition"

_SHOP_ID_PATTERN = re.compile(r"-i\.(\d+)\.\d+")
_PRODUCT_CARD_SELECTOR = 'a[href*="-i."].contents'


def _product_to_listing(
    product: ShopeeProduct,
    discovery_method: str = "search",
) -> CompetitionListing:
    """Convert a ShopeeProduct to a CompetitionListing."""
    shop_id = ""
    if product.product_url:
        match = _SHOP_ID_PATTERN.search(product.product_url)
        if match:
            shop_id = match.group(1)

    return CompetitionListing(
        product_url=product.product_url or "",
        shop_id=shop_id or product.shop_name or "",
        title=product.title,
        price_cents=_parse_price_cents(product.price_display),
        price_display=product.price_display,
        sold_count_raw=product.sold_count,
        sold_count_numeric=parse_sold_count(product.sold_count),
        rating=product.rating,
        image_url=product.image_url,
        is_sold_out=product.is_sold_out,
        is_delisted=False,
        discovery_method=discovery_method,
    )


def _build_snapshot(
    set_number: str,
    listings: tuple[CompetitionListing, ...],
    saturation_score: float,
    saturation_level: str,
) -> CompetitionSnapshot:
    """Build a CompetitionSnapshot from listings and saturation data."""
    import statistics as stats_mod

    from services.shopee.saturation_types import SaturationLevel

    active = tuple(li for li in listings if not li.is_delisted)
    prices = [li.price_cents for li in active if li.price_cents is not None]
    sold_counts = [li.sold_count_numeric for li in active if li.sold_count_numeric is not None]
    shop_ids = frozenset(li.shop_id for li in active if li.shop_id)

    level = SaturationLevel(saturation_level)

    return CompetitionSnapshot(
        set_number=set_number,
        listings_count=len(active),
        unique_sellers=len(shop_ids),
        total_sold_count=sum(sold_counts) if sold_counts else None,
        min_price_cents=min(prices) if prices else None,
        max_price_cents=max(prices) if prices else None,
        avg_price_cents=int(stats_mod.mean(prices)) if prices else None,
        median_price_cents=int(stats_mod.median(prices)) if prices else None,
        saturation_score=saturation_score,
        saturation_level=level,
        scraped_at=datetime.now(timezone.utc),
        listings=listings,
    )


async def _search_and_collect(
    page: Page,
    set_number: str,
    rrp_cents: int | None,
    *,
    is_first_in_session: bool = False,
) -> tuple[tuple[ShopeeProduct, ...], float, str]:
    """Search Shopee and return filtered products with saturation data.

    Returns (filtered_products, saturation_score, saturation_level).
    """
    query = f"LEGO {set_number}"
    url = SHOPEE_SEARCH_URL.format(query=quote(query))

    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(min_ms=3_000, max_ms=5_000)

    if is_first_in_session:
        await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=3)
        await select_english(page)

    await dismiss_popups(page)

    try:
        await page.wait_for_selector(_PRODUCT_CARD_SELECTOR, timeout=15_000)
    except Exception:
        logger.debug("Set %s: no product cards appeared within 15s", set_number)

    products = await parse_search_results(page, max_items=60)
    products = _enrich_with_shop_ids(products)

    # Filter out own shop
    own_shop_id = COMPETITION_CONFIG.own_shop_id
    products = tuple(p for p in products if p.shop_name != own_shop_id)

    # Filter relevant products (set number in title)
    relevant = filter_relevant_products(products, set_number)

    # Compute saturation score
    sat = compute_saturation(set_number, query, relevant, rrp_cents)

    logger.info(
        "Set %s: found %d relevant listings from %d sellers (score=%.1f)",
        set_number,
        len(relevant),
        sat.unique_sellers,
        sat.saturation_score,
    )

    return relevant, sat.saturation_score, sat.saturation_level.value


async def _revisit_single_url(
    page: Page,
    url: str,
    prev_listing: dict,
) -> CompetitionListing:
    """Visit a single product URL and extract current state."""
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        await human_delay(min_ms=2_000, max_ms=4_000)

        # Check for 404 or redirect to homepage
        if response and (response.status == 404 or response.url == "https://shopee.com.my/"):
            return CompetitionListing(
                product_url=url,
                shop_id=prev_listing.get("shop_id", ""),
                title=prev_listing.get("title", ""),
                price_cents=None,
                price_display="",
                sold_count_raw=None,
                sold_count_numeric=None,
                rating=None,
                image_url=None,
                is_sold_out=False,
                is_delisted=True,
                discovery_method="revisit",
            )

        # Extract data from product detail page via JS
        data = await page.evaluate("""() => {
            const text = document.body.textContent || '';

            // Price
            const priceMatch = text.match(/RM[\\d,]+\\.?\\d*/);
            const price = priceMatch ? priceMatch[0] : '';

            // Sold count
            const soldMatch = text.match(/(\\d[\\d,.]*[kK]?)\\s*sold/);
            const sold = soldMatch ? soldMatch[1] + ' sold' : null;

            // Rating
            const ratingMatch = text.match(/(\\d\\.\\d)\\s*out of\\s*5/);
            const rating = ratingMatch ? ratingMatch[1] : null;

            // Sold out
            const isSoldOut = /sold\\s*out/i.test(text);

            // Title from og:title or h1
            const ogTitle = document.querySelector('meta[property="og:title"]');
            const h1 = document.querySelector('h1');
            const title = ogTitle?.content || h1?.textContent?.trim() || '';

            // Image
            const ogImage = document.querySelector('meta[property="og:image"]');
            const img = ogImage?.content || null;

            return { price, sold, rating, isSoldOut, title, image: img };
        }""")

        shop_id = prev_listing.get("shop_id", "")
        if not shop_id:
            match = _SHOP_ID_PATTERN.search(url)
            if match:
                shop_id = match.group(1)

        return CompetitionListing(
            product_url=url,
            shop_id=shop_id,
            title=data.get("title") or prev_listing.get("title", ""),
            price_cents=_parse_price_cents(data.get("price", "")),
            price_display=data.get("price", ""),
            sold_count_raw=data.get("sold"),
            sold_count_numeric=parse_sold_count(data.get("sold")),
            rating=data.get("rating"),
            image_url=data.get("image"),
            is_sold_out=data.get("isSoldOut", False),
            is_delisted=False,
            discovery_method="revisit",
        )

    except Exception as e:
        # Transient failure (timeout, network error) -- do NOT mark as
        # delisted so the URL is retried on the next cycle.
        logger.warning("Revisit failed for %s (transient): %s", url, e)
        return CompetitionListing(
            product_url=url,
            shop_id=prev_listing.get("shop_id", ""),
            title=prev_listing.get("title", ""),
            price_cents=None,
            price_display="",
            sold_count_raw=None,
            sold_count_numeric=prev_listing.get("sold_count_numeric"),
            rating=None,
            image_url=None,
            is_sold_out=False,
            is_delisted=False,
            discovery_method="revisit",
        )


async def _scrape_single_item(
    page: Page,
    set_number: str,
    rrp_cents: int | None,
    conn: Any | None,
    *,
    is_first_in_session: bool = False,
) -> CompetitionSnapshot:
    """Scrape competition data for a single set.

    Phase 1: Search page 1 for current listings.
    Phase 2: Revisit previously-known URLs not in search results.
    Phase 3: Build and save snapshot.
    """
    # Phase 1: Search
    relevant, score, level = await _search_and_collect(
        page, set_number, rrp_cents, is_first_in_session=is_first_in_session,
    )

    search_listings = tuple(
        _product_to_listing(p, "search") for p in relevant
    )
    search_urls = frozenset(li.product_url for li in search_listings)

    # Phase 2: Revisit known URLs not found in search
    revisit_listings: list[CompetitionListing] = []
    if conn is not None:
        from services.shopee.competition_repository import get_previous_listing_urls

        prev = get_previous_listing_urls(conn, set_number)
        urls_to_revisit = [
            p for p in prev
            if p["product_url"] not in search_urls
        ]

        if urls_to_revisit:
            logger.info(
                "Set %s: revisiting %d previously-known URLs",
                set_number,
                len(urls_to_revisit),
            )

        for prev_listing in urls_to_revisit:
            listing = await _revisit_single_url(
                page, prev_listing["product_url"], prev_listing,
            )
            revisit_listings.append(listing)

            # Small delay between revisits
            await human_delay(min_ms=3_000, max_ms=6_000)

    all_listings = search_listings + tuple(revisit_listings)

    return _build_snapshot(set_number, all_listings, score, level)


async def run_competition_batch(
    items: list[dict],
    conn: Any | None = None,
) -> CompetitionBatchResult:
    """Search Shopee for multiple portfolio LEGO sets and track competition.

    Uses the same browser/anti-ban infrastructure as the saturation scraper.
    """
    cfg = SATURATION_CONFIG
    cb_state = CircuitBreakerState()
    errors: list[tuple[str, str]] = []
    skipped = 0
    successful = 0
    searches_in_session = 0
    consecutive_failures = 0

    total = len(items)
    remaining = deque(items)

    logger.info("Starting competition batch: %d items to check", total)

    while remaining:
        if not is_available(cb_state, SOURCE_ID, cfg.circuit_breaker_cooldown_s):
            logger.warning("Circuit breaker tripped -- stopping batch")
            skipped += len(remaining)
            break

        try:
            async with shopee_browser() as browser:
                page = await _setup_browser_session(browser)
                searches_in_session = 0

                while remaining and searches_in_session < cfg.max_searches_per_session:
                    if not is_available(
                        cb_state, SOURCE_ID, cfg.circuit_breaker_cooldown_s
                    ):
                        skipped += len(remaining)
                        remaining.clear()
                        break

                    item = remaining.popleft()
                    set_number = item["set_number"]
                    rrp_cents = item.get("rrp_cents")

                    try:
                        snapshot = await _scrape_single_item(
                            page,
                            set_number,
                            rrp_cents,
                            conn,
                            is_first_in_session=(searches_in_session == 0),
                        )

                        _save_snapshot(snapshot, conn)

                        cb_state = record_success(cb_state, SOURCE_ID)
                        consecutive_failures = 0
                        searches_in_session += 1
                        successful += 1

                        logger.info(
                            "Set %s: score=%.1f, %d listings (%d search, %d revisit), %d sellers",
                            set_number,
                            snapshot.saturation_score,
                            snapshot.listings_count,
                            sum(1 for li in snapshot.listings if li.discovery_method == "search"),
                            sum(1 for li in snapshot.listings if li.discovery_method == "revisit"),
                            snapshot.unique_sellers,
                        )

                    except Exception as e:
                        consecutive_failures += 1
                        cb_state = record_failure(
                            cb_state, SOURCE_ID, cfg.circuit_breaker_threshold,
                        )
                        errors.append((set_number, str(e)))

                        logger.warning(
                            "Set %s failed (attempt %d): %s",
                            set_number,
                            consecutive_failures,
                            e,
                        )

                        backoff_s = calculate_backoff(consecutive_failures)
                        logger.info("Backing off for %.1f seconds", backoff_s)
                        await asyncio.sleep(backoff_s)
                        continue

                    if remaining and searches_in_session < cfg.max_searches_per_session:
                        delay = get_random_delay(
                            min_ms=cfg.min_search_delay_ms,
                            max_ms=cfg.max_search_delay_ms,
                        )
                        logger.debug("Waiting %.1f seconds before next search", delay)
                        await asyncio.sleep(delay)

                await page.close()

        except Exception as e:
            logger.exception("Browser session failed: %s", e)
            consecutive_failures += 1
            cb_state = record_failure(
                cb_state, SOURCE_ID, cfg.circuit_breaker_threshold,
            )

        if remaining:
            cooldown = get_random_delay(
                min_ms=cfg.session_cooldown_min_ms,
                max_ms=cfg.session_cooldown_max_ms,
            )
            logger.info(
                "Session complete (%d searches). Cooling down %.1f seconds",
                searches_in_session,
                cooldown,
            )
            await asyncio.sleep(cooldown)

    result = CompetitionBatchResult(
        total_items=total,
        successful=successful,
        failed=len(errors),
        skipped=skipped,
        errors=tuple(errors),
    )

    logger.info(
        "Competition batch complete: %d/%d successful, %d failed, %d skipped",
        result.successful,
        result.total_items,
        result.failed,
        result.skipped,
    )

    return result


async def _setup_browser_session(
    browser: Union[Browser, BrowserContext],
) -> Page:
    """Create a page and do initial Shopee setup."""
    page = await new_page(browser)
    setup_dialog_handler(page)
    return page


def _save_snapshot(
    snapshot: CompetitionSnapshot,
    conn: Any | None = None,
) -> None:
    """Persist a competition snapshot to the database."""
    from services.shopee.competition_repository import save_competition_snapshot

    if conn is not None:
        save_competition_snapshot(conn, snapshot)
        return

    from db.connection import get_connection
    from db.schema import init_schema

    own_conn = get_connection()
    try:
        init_schema(own_conn)
        save_competition_snapshot(own_conn, snapshot)
    finally:
        own_conn.close()
