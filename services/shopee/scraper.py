"""Shopee search and scraping orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from services.shopee.auth import is_logged_in, login
from services.shopee.browser import shopee_browser, human_delay, new_page
from services.shopee.humanize import random_click, random_type
from services.shopee.parser import ShopeeProduct, parse_search_results
from services.shopee.popups import (
    dismiss_popups,
    dismiss_popups_loop,
    select_english,
    setup_dialog_handler,
)

SHOPEE_BASE = "https://shopee.com.my"

# Search bar selectors (multiple fallbacks)
SEL_SEARCH_INPUTS: tuple[str, ...] = (
    'input.shopee-searchbar-input__input',
    'input[name="search"]',
    'input[placeholder*="Search"]',
    'input[placeholder*="search"]',
    '.shopee-searchbar input',
)


@dataclass(frozen=True)
class ShopeeScrapeResult:
    """Result of a Shopee scrape operation."""

    success: bool
    query: str
    items: tuple[ShopeeProduct, ...] = ()
    error: str | None = None


async def _find_element(page, selectors: tuple[str, ...]):
    """Try multiple selectors and return the first visible match."""
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return selector
        except Exception:
            continue
    return None


async def search_shopee(
    query: str,
    *,
    max_items: int = 50,
    require_login: bool = False,
) -> ShopeeScrapeResult:
    """Search Shopee for items matching query.

    Launches a camoufox browser, navigates to shopee.com.my,
    selects English, dismisses popups, optionally logs in,
    and performs a search.

    Args:
        query: Search term (e.g. "LEGO 75192")
        max_items: Maximum products to extract
        require_login: Whether to login before searching

    Returns:
        ShopeeScrapeResult with parsed products or error
    """
    try:
        async with shopee_browser() as browser:
            page = await new_page(browser)
            setup_dialog_handler(page)

            # Navigate to Shopee
            await page.goto(SHOPEE_BASE, wait_until="domcontentloaded")
            await human_delay(min_ms=2_000, max_ms=4_000)

            # Dismiss popups first (promo modal blocks everything)
            await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=5)

            # Then try selecting English (only shows on first visit)
            await select_english(page)

            # Handle login -- if redirected to login page or login required
            if require_login or "/buyer/login" in page.url:
                if not await is_logged_in(page):
                    logged_in = await login(page)
                    if not logged_in:
                        return ShopeeScrapeResult(
                            success=False,
                            query=query,
                            error="Login failed or timed out",
                        )
                    # After login, navigate to home
                    await page.goto(SHOPEE_BASE, wait_until="domcontentloaded")
                    await human_delay(min_ms=2_000, max_ms=3_000)
                    await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=5)
                    await select_english(page)

            # Find and click search input
            search_selector = await _find_element(page, SEL_SEARCH_INPUTS)
            if not search_selector:
                return ShopeeScrapeResult(
                    success=False,
                    query=query,
                    error="Could not find search input",
                )

            # Use randomized click + type for anti-detection
            await random_type(page, search_selector, query)
            await human_delay(min_ms=500, max_ms=1_000)

            # Submit search via Enter key
            await page.keyboard.press("Enter")
            await human_delay(min_ms=2_000, max_ms=4_000)

            # Wait for results to load
            await page.wait_for_load_state("networkidle")
            await dismiss_popups(page)

            # Parse product cards
            items = await parse_search_results(page, max_items)

            return ShopeeScrapeResult(
                success=True,
                query=query,
                items=items,
            )

    except Exception as e:
        return ShopeeScrapeResult(
            success=False,
            query=query,
            error=str(e),
        )


def search_shopee_sync(
    query: str,
    *,
    max_items: int = 50,
    require_login: bool = False,
) -> ShopeeScrapeResult:
    """Synchronous wrapper for search_shopee."""
    return asyncio.run(
        search_shopee(query, max_items=max_items, require_login=require_login)
    )
