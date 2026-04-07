"""Batch Shopee saturation scraper with anti-ban protection.

Navigates directly to Shopee search URLs for each LEGO set, scrapes the
first page of results, and computes market saturation scores. Uses direct
URL navigation (faster and more reliable than typing in the search bar).
"""

import asyncio
import logging
import re
from collections import deque
from typing import Any, Union
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, Page


from config.settings import (
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
from services.shopee.parser import ShopeeProduct, parse_search_results
from services.shopee.popups import (
    dismiss_popups,
    dismiss_popups_loop,
    select_english,
    setup_dialog_handler,
)
from services.shopee.saturation_scorer import compute_saturation
from services.shopee.saturation_types import (
    SaturationBatchResult,
    SaturationSnapshot,
)

logger = logging.getLogger("bws.shopee.saturation")

SHOPEE_SEARCH_URL = "https://shopee.com.my/search?keyword={query}"
SOURCE_ID = "shopee_saturation"

# Pattern to extract shop ID from product URL: -i.SHOP_ID.ITEM_ID
_SHOP_ID_PATTERN = re.compile(r"-i\.(\d+)\.\d+")

# CSS selector for product cards
_PRODUCT_CARD_SELECTOR = 'a[href*="-i."].contents'


def _extract_shop_ids(products: tuple[ShopeeProduct, ...]) -> frozenset[str]:
    """Extract unique shop IDs from product URLs.

    Shopee search results don't show seller names in the card DOM,
    but each product URL contains the shop ID: /Product-Name-i.SHOP_ID.ITEM_ID
    """
    shop_ids: set[str] = set()
    for p in products:
        if p.product_url:
            match = _SHOP_ID_PATTERN.search(p.product_url)
            if match:
                shop_ids.add(match.group(1))
    return frozenset(shop_ids)


def _enrich_with_shop_ids(
    products: tuple[ShopeeProduct, ...],
) -> tuple[ShopeeProduct, ...]:
    """Fill in shop_name from the product URL's shop ID.

    This allows the scorer's unique_sellers count to work correctly.
    """
    enriched: list[ShopeeProduct] = []
    for p in products:
        shop_id = None
        if p.product_url:
            match = _SHOP_ID_PATTERN.search(p.product_url)
            if match:
                shop_id = match.group(1)
        enriched.append(
            ShopeeProduct(
                title=p.title,
                price_display=p.price_display,
                sold_count=p.sold_count,
                rating=p.rating,
                shop_name=shop_id or p.shop_name,
                product_url=p.product_url,
                image_url=p.image_url,
            )
        )
    return tuple(enriched)


async def _setup_browser_session(
    browser: Union[Browser, BrowserContext],
) -> Page:
    """Create a page and do initial Shopee setup (popups, language).

    Returns:
        Page ready for search URL navigation.
    """
    page = await new_page(browser)
    setup_dialog_handler(page)
    return page


async def _search_single_item(
    page: Page,
    set_number: str,
    rrp_cents: int | None,
    *,
    is_first_in_session: bool = False,
) -> SaturationSnapshot:
    """Navigate to a search URL and return a saturation snapshot."""
    query = f"LEGO {set_number}"
    url = SHOPEE_SEARCH_URL.format(query=quote(query))

    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(min_ms=3_000, max_ms=5_000)

    # Dismiss popups on first navigation in session
    if is_first_in_session:
        await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=3)
        await select_english(page)

    await dismiss_popups(page)

    # Wait for product cards to appear (more reliable than networkidle)
    try:
        await page.wait_for_selector(_PRODUCT_CARD_SELECTOR, timeout=15_000)
    except Exception:
        logger.debug("Set %s: no product cards appeared within 15s", set_number)

    # Parse first page of results
    products = await parse_search_results(page, max_items=60)

    # Enrich products with shop IDs extracted from URLs
    products = _enrich_with_shop_ids(products)

    logger.info(
        "Set %s: found %d listings from %d sellers on Shopee",
        set_number,
        len(products),
        len(_extract_shop_ids(products)),
    )

    return compute_saturation(
        set_number=set_number,
        search_query=query,
        products=products,
        rrp_cents=rrp_cents,
    )


async def run_saturation_batch(
    items: list[dict],
    conn: Any | None = None,
) -> SaturationBatchResult:
    """Search Shopee for multiple LEGO sets and compute saturation scores.

    Opens one browser session and navigates directly to search URLs.
    Rotates browser sessions after max_searches_per_session to reduce
    fingerprinting risk. Uses circuit breaker to stop on repeated failures.

    Args:
        items: List of dicts with keys: set_number, title, rrp_cents
        conn: Optional database connection for saving results. If None,
              opens and closes its own connection per save.

    Returns:
        SaturationBatchResult with all snapshots and error details
    """
    cfg = SATURATION_CONFIG
    cb_state = CircuitBreakerState()
    snapshots: list[SaturationSnapshot] = []
    errors: list[tuple[str, str]] = []
    skipped = 0
    searches_in_session = 0
    consecutive_failures = 0

    total = len(items)
    remaining = deque(items)

    logger.info("Starting saturation batch: %d items to check", total)

    while remaining:
        # Check circuit breaker before opening a new session
        if not is_available(cb_state, SOURCE_ID, cfg.circuit_breaker_cooldown_s):
            logger.warning("Circuit breaker tripped -- stopping batch")
            skipped += len(remaining)
            break

        try:
            async with shopee_browser() as browser:
                page = await _setup_browser_session(browser)
                searches_in_session = 0

                while remaining and searches_in_session < cfg.max_searches_per_session:
                    # Check circuit breaker each iteration
                    if not is_available(
                        cb_state, SOURCE_ID, cfg.circuit_breaker_cooldown_s
                    ):
                        logger.warning(
                            "Circuit breaker tripped mid-session -- stopping"
                        )
                        skipped += len(remaining)
                        remaining.clear()
                        break

                    item = remaining.popleft()
                    set_number = item["set_number"]
                    rrp_cents = item.get("rrp_cents")

                    try:
                        snapshot = await _search_single_item(
                            page,
                            set_number,
                            rrp_cents,
                            is_first_in_session=(searches_in_session == 0),
                        )

                        # Save to database
                        _save_snapshot(snapshot, conn)

                        snapshots.append(snapshot)
                        cb_state = record_success(cb_state, SOURCE_ID)
                        consecutive_failures = 0
                        searches_in_session += 1

                        logger.info(
                            "Set %s: score=%.1f level=%s (%d listings, %d sellers)",
                            set_number,
                            snapshot.saturation_score,
                            snapshot.saturation_level.value,
                            snapshot.listings_count,
                            snapshot.unique_sellers,
                        )

                    except Exception as e:
                        consecutive_failures += 1
                        cb_state = record_failure(
                            cb_state, SOURCE_ID, cfg.circuit_breaker_threshold
                        )
                        errors.append((set_number, str(e)))

                        logger.warning(
                            "Set %s failed (attempt %d): %s",
                            set_number,
                            consecutive_failures,
                            e,
                        )

                        # Exponential backoff on failure
                        backoff_s = calculate_backoff(consecutive_failures)
                        logger.info("Backing off for %.1f seconds", backoff_s)
                        await asyncio.sleep(backoff_s)
                        continue

                    # Random delay between searches (30-90 seconds)
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
                cb_state, SOURCE_ID, cfg.circuit_breaker_threshold
            )

        # Session cooldown before opening a new browser
        if remaining:
            cooldown = get_random_delay(
                min_ms=cfg.session_cooldown_min_ms,
                max_ms=cfg.session_cooldown_max_ms,
            )
            logger.info(
                "Session complete (%d searches). Cooling down %.1f seconds before next session",
                searches_in_session,
                cooldown,
            )
            await asyncio.sleep(cooldown)

    result = SaturationBatchResult(
        total_items=total,
        successful=len(snapshots),
        failed=len(errors),
        skipped=skipped,
        snapshots=tuple(snapshots),
        errors=tuple(errors),
    )

    logger.info(
        "Saturation batch complete: %d/%d successful, %d failed, %d skipped",
        result.successful,
        result.total_items,
        result.failed,
        result.skipped,
    )

    return result


def _save_snapshot(
    snapshot: SaturationSnapshot,
    conn: Any | None = None,
) -> None:
    """Persist a saturation snapshot to the database."""
    from services.shopee.saturation_repository import save_saturation_snapshot

    if conn is not None:
        save_saturation_snapshot(conn, snapshot)
        return

    from db.connection import get_connection
    from db.schema import init_schema

    own_conn = get_connection()
    try:
        init_schema(own_conn)
        save_saturation_snapshot(own_conn, snapshot)
    finally:
        own_conn.close()
