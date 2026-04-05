"""Shopee search and scraping orchestration."""


import asyncio
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

from db.connection import get_connection
from db.schema import init_schema
from services.shopee.auth import is_logged_in, login
from services.shopee.browser import shopee_browser, human_delay, new_page
from services.shopee.humanize import random_click, random_click_element, random_type
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
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:
                pass
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
    max_pages: int = 20,
) -> ShopeeScrapeResult:
    """Scrape all products from a Shopee shop/collection page.

    Navigates directly to the given URL (e.g. a shop collection page)
    and extracts all visible products. Handles popups, login redirects,
    scrolls to load lazy items, and paginates through all pages.

    Args:
        url: Full Shopee URL to scrape
        max_items: Maximum products to extract
        max_pages: Maximum number of pages to scrape

    Returns:
        ShopeeScrapeResult with parsed products or error
    """
    try:
        async with shopee_browser() as browser:
            page = await new_page(browser)
            setup_dialog_handler(page)

            # Navigate directly to the target URL
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
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
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await human_delay(min_ms=2_000, max_ms=3_000)
                    await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=3)

            # Wait for product cards to render (Shopee is a SPA)
            try:
                await page.wait_for_selector(
                    'a[href*="-i."]', timeout=15_000,
                )
            except Exception:
                pass  # Proceed anyway -- page may have no products

            # Scrape all pages: scroll, parse, paginate
            items = await _scrape_all_pages(page, max_items, max_pages)

            # Extract shop name from URL (e.g. /legoshopmy?... -> "legoshopmy")
            shop_name = _extract_shop_name(url)
            if shop_name:
                items = tuple(
                    ShopeeProduct(
                        title=item.title,
                        price_display=item.price_display,
                        sold_count=item.sold_count,
                        rating=item.rating,
                        shop_name=shop_name,
                        product_url=item.product_url,
                        image_url=item.image_url,
                        is_sold_out=item.is_sold_out,
                    )
                    for item in items
                )

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


def _extract_shop_name(url: str) -> str | None:
    """Extract the seller/shop name from a Shopee URL.

    e.g. https://shopee.com.my/legoshopmy?page=0&shopCollection=... -> "legoshopmy"
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    # Shop pages have a single path segment (the shop name)
    # Product pages have longer paths with -i. in them
    # Exclude known Shopee system paths
    system_paths = {"search", "buyer", "verify", "cart", "checkout", "daily_discover"}
    if path and "/" not in path and "-i." not in path and path not in system_paths:
        return path
    return None


async def _scroll_to_load(page, max_scrolls: int = 10) -> None:
    """Scroll down the page to trigger lazy-loading of products."""
    for _ in range(max_scrolls):
        previous_height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await human_delay(min_ms=1_000, max_ms=2_000)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            break


async def _simulate_browsing(page) -> None:
    """Simulate a human slowly scanning the page before moving on.

    Scrolls gradually from top to bottom in small increments, pausing
    at random intervals to "read" or hover over a product. This mimics
    a real user visually scanning the product grid before clicking next.
    """
    # Scroll to top first
    await page.evaluate("window.scrollTo(0, 0)")
    await human_delay(min_ms=500, max_ms=1_000)

    page_height = await page.evaluate("document.body.scrollHeight")
    viewport_height = await page.evaluate("window.innerHeight")
    if page_height <= viewport_height:
        await human_delay(min_ms=1_500, max_ms=3_000)
        return

    # Scroll down in 3-6 incremental steps
    num_steps = secrets.randbelow(4) + 3
    step_size = page_height / num_steps
    current_y = 0.0

    for step in range(num_steps):
        # Vary each scroll distance slightly (+/- 20%)
        jitter = 0.8 + (secrets.randbelow(40) / 100.0)
        current_y = min(current_y + step_size * jitter, page_height)

        await page.evaluate(
            f"window.scrollTo({{top: {current_y}, behavior: 'smooth'}})"
        )
        # Pause 1-3s per step, as if scanning the products
        await human_delay(min_ms=1_000, max_ms=3_000)

        # Occasionally hover over a product card (~40% chance)
        if secrets.randbelow(10) < 4:
            card_count = await page.evaluate(
                'document.querySelectorAll(\'a[href*="-i."]\').length'
            )
            if card_count > 0:
                idx = secrets.randbelow(card_count)
                await page.evaluate(f"""() => {{
                    const cards = document.querySelectorAll('a[href*="-i."]');
                    const card = cards[{idx}];
                    if (card) {{
                        const r = card.getBoundingClientRect();
                        if (r.top >= 0 && r.bottom <= window.innerHeight) {{
                            card.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}));
                        }}
                    }}
                }}""")
                await human_delay(min_ms=600, max_ms=1_500)

        # Occasionally move mouse to a random spot (~30% chance)
        if secrets.randbelow(10) < 3:
            vw = await page.evaluate("window.innerWidth")
            vh = await page.evaluate("window.innerHeight")
            x = secrets.randbelow(max(1, vw - 100)) + 50
            y = secrets.randbelow(max(1, vh - 100)) + 50
            await page.mouse.move(x, y)
            await human_delay(min_ms=300, max_ms=800)

    # Final pause at the bottom before paginating
    await human_delay(min_ms=1_000, max_ms=2_500)


async def _click_next_page(page) -> bool:
    """Find and click the '>' next-page button in Shopee pagination.

    Uses JS evaluation to locate the button, then clicks it with
    human-like randomization for anti-detection.

    Returns:
        True if a next-page button was found and clicked, False otherwise.
    """
    found = await page.evaluate("""() => {
        // Strategy 1: Find a button/link with exact ">" text
        const allBtns = document.querySelectorAll('button, a');
        for (const btn of allBtns) {
            const text = btn.textContent.trim();
            if (text === '>' || text === 'Next') {
                // Skip if disabled
                if (btn.disabled || btn.classList.contains('shopee-disabled')
                    || btn.getAttribute('aria-disabled') === 'true') {
                    return false;
                }
                btn.setAttribute('data-bws-next', 'true');
                return true;
            }
        }

        // Strategy 2: Find pagination container and click last enabled nav button
        const paginators = document.querySelectorAll(
            '[class*="pagination"], [class*="page-controller"], ' +
            '.shopee-mini-page-controller, [role="navigation"]'
        );
        for (const nav of paginators) {
            const btns = nav.querySelectorAll('button, a');
            if (btns.length === 0) continue;
            const lastBtn = btns[btns.length - 1];
            if (lastBtn.disabled || lastBtn.classList.contains('shopee-disabled')
                || lastBtn.getAttribute('aria-disabled') === 'true') {
                return false;
            }
            lastBtn.setAttribute('data-bws-next', 'true');
            return true;
        }
        return false;
    }""")

    if not found:
        return False

    el = await page.query_selector('[data-bws-next="true"]')
    if not el:
        return False

    await page.evaluate("el => el.removeAttribute('data-bws-next')", el)
    await random_click_element(el)
    await human_delay(min_ms=2_000, max_ms=4_000)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass  # Page may already be loaded
    await page.evaluate("window.scrollTo(0, 0)")
    await human_delay(min_ms=500, max_ms=1_000)
    return True


async def _scrape_all_pages(
    page,
    max_items: int = 200,
    max_pages: int = 20,
) -> tuple[ShopeeProduct, ...]:
    """Scroll, parse, and paginate through all pages of results.

    For each page: scrolls to load lazy items, parses products,
    deduplicates, then clicks next. Stops when max_items or max_pages
    is reached, or no next button exists.

    Args:
        page: Playwright page positioned on the first results page
        max_items: Maximum total products to collect
        max_pages: Maximum number of pages to scrape

    Returns:
        Deduplicated tuple of ShopeeProduct, trimmed to max_items
    """
    all_items: list[ShopeeProduct] = []
    seen_urls: set[str] = set()

    for page_num in range(max_pages):
        await _scroll_to_load(page, max_scrolls=10)
        page_items = await parse_search_results(page, max_items)

        for item in page_items:
            url = item.product_url or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            all_items.append(item)

        if len(all_items) >= max_items:
            break

        # Simulate human browsing before navigating to next page
        await _simulate_browsing(page)

        has_next = await _click_next_page(page)
        if not has_next:
            break

    return tuple(all_items[:max_items])


def scrape_shop_page_sync(
    url: str,
    *,
    max_items: int = 200,
    max_pages: int = 20,
) -> ShopeeScrapeResult:
    """Synchronous wrapper for scrape_shop_page."""
    return asyncio.run(scrape_shop_page(url, max_items=max_items, max_pages=max_pages))


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
