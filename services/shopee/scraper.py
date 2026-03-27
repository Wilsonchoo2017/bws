"""Shopee search and scraping orchestration."""


import asyncio
from dataclasses import dataclass

from db.connection import get_connection
from db.schema import init_schema
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
from services.shopee.repository import record_scrape, upsert_products

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


async def scrape_shop_page(
    url: str,
    *,
    max_items: int = 200,
) -> ShopeeScrapeResult:
    """Scrape all products from a Shopee shop/collection page.

    Navigates directly to the given URL (e.g. a shop collection page)
    and extracts all visible products. Handles popups, login redirects,
    and scrolls down to load lazy-loaded items.

    Args:
        url: Full Shopee URL to scrape
        max_items: Maximum products to extract

    Returns:
        ShopeeScrapeResult with parsed products or error
    """
    try:
        async with shopee_browser() as browser:
            page = await new_page(browser)
            setup_dialog_handler(page)

            # Navigate directly to the target URL
            await page.goto(url, wait_until="domcontentloaded")
            await human_delay(min_ms=2_000, max_ms=4_000)
            await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=5)
            await select_english(page)

            # Handle login if Shopee redirected us
            if "/buyer/login" in page.url:
                if not await is_logged_in(page):
                    logged_in = await login(page)
                    if not logged_in:
                        return ShopeeScrapeResult(
                            success=False,
                            query=url,
                            error="Login failed or timed out",
                        )
                    # After login, go to the actual target
                    await page.goto(url, wait_until="domcontentloaded")
                    await human_delay(min_ms=2_000, max_ms=3_000)
                    await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=3)

            # Scroll down to trigger lazy-loading of product cards
            await _scroll_to_load(page, max_scrolls=10)

            # Parse products (same DOM structure as search results)
            items = await parse_search_results(page, max_items)

            # Save to database
            _save_to_db(url, items)

            return ShopeeScrapeResult(
                success=True,
                query=url,
                items=items,
            )

    except Exception as e:
        _save_scrape_error(url, str(e))
        return ShopeeScrapeResult(
            success=False,
            query=url,
            error=str(e),
        )


def _save_to_db(source_url: str, items: tuple[ShopeeProduct, ...]) -> None:
    """Save scraped products to the database."""
    try:
        conn = get_connection()
        init_schema(conn)
        saved = upsert_products(conn, items, source_url)
        record_scrape(conn, source_url, saved, success=True)
        conn.close()
    except Exception as e:
        print(f"Warning: failed to save to database: {e}")


def _save_scrape_error(source_url: str, error: str) -> None:
    """Record a failed scrape attempt."""
    try:
        conn = get_connection()
        init_schema(conn)
        record_scrape(conn, source_url, 0, success=False, error=error)
        conn.close()
    except Exception:
        pass


async def _scroll_to_load(page, max_scrolls: int = 10) -> None:
    """Scroll down the page to trigger lazy-loading of products."""
    for _ in range(max_scrolls):
        previous_height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await human_delay(min_ms=1_000, max_ms=2_000)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            break


def scrape_shop_page_sync(
    url: str,
    *,
    max_items: int = 200,
) -> ShopeeScrapeResult:
    """Synchronous wrapper for scrape_shop_page."""
    return asyncio.run(scrape_shop_page(url, max_items=max_items))


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
