"""Shopee search and scraping orchestration."""


import asyncio
import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

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
from services.notifications.ntfy import NtfyMessage, send_notification

logger = logging.getLogger("bws.shopee.scraper")

SHOPEE_BASE = "https://shopee.com.my"

# Directory where captcha snapshots are stored for future analysis
_SNAPSHOT_DIR = Path(__file__).resolve().parent / "captcha_snapshots"

# URL fragments / page indicators that signal a captcha or verification challenge
_CAPTCHA_URL_PATTERNS: tuple[str, ...] = (
    "/verify/",
    "/captcha",
    "security-check",
    "challenge",
)


async def _save_snapshot(page: Page, *, reason: str = "unknown") -> Path | None:
    """Save a full page snapshot (screenshot + HTML + metadata) for analysis.

    Snapshots are stored under services/shopee/captcha_snapshots/ with a
    timestamp prefix so they sort chronologically.

    Returns the snapshot directory path, or None on failure.
    """
    try:
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        snap_dir = _SNAPSHOT_DIR / ts
        snap_dir.mkdir(parents=True, exist_ok=True)

        # Screenshot
        await page.screenshot(path=str(snap_dir / "screenshot.png"), full_page=True)

        # Full HTML
        html = await page.content()
        (snap_dir / "page.html").write_text(html, encoding="utf-8")

        # Metadata
        meta = {
            "url": page.url,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "reason": reason,
            "title": await page.title(),
        }
        (snap_dir / "meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        logger.info("Captcha snapshot saved to %s", snap_dir)
        return snap_dir
    except Exception:
        logger.exception("Failed to save captcha snapshot")
        return None


def _is_captcha_url(url: str) -> bool:
    """Return True if the URL looks like a Shopee captcha/verification page."""
    lower = url.lower()
    return any(pat in lower for pat in _CAPTCHA_URL_PATTERNS)


async def _detect_captcha_page(page: Page) -> bool:
    """Check both URL and page content for captcha indicators."""
    if _is_captcha_url(page.url):
        return True
    # Some captcha pages keep the original URL but inject a challenge overlay
    has_captcha_el = await page.evaluate("""() => {
        const sel = [
            '[class*="captcha"]', '[id*="captcha"]',
            '[class*="verify"]', '[id*="verify"]',
            'iframe[src*="captcha"]', 'iframe[src*="challenge"]',
        ];
        return sel.some(s => document.querySelector(s) !== null);
    }""")
    return bool(has_captcha_el)


def _notify_shopee_captcha() -> None:
    """Send ntfy alert so user can come solve the captcha."""
    send_notification(
        NtfyMessage(
            title="Shopee: CAPTCHA detected",
            message=(
                "Shopee scraper hit a CAPTCHA / verification page. "
                "Please open the browser window and solve it within 3 minutes."
            ),
            priority=5,
            tags=("warning", "robot"),
            topic="bws-alerts",
        )
    )


async def _wait_for_captcha(
    page: Page,
    *,
    timeout_s: int = 180,
    on_progress: Callable[[str], None] | None = None,
) -> bool:
    """If the page is a captcha, notify the user and wait for resolution.

    Returns True if captcha was detected (and either solved or timed out).
    Returns False if no captcha was detected.
    """
    if not await _detect_captcha_page(page):
        return False

    logger.warning("Captcha detected at %s — sending ntfy and waiting", page.url)
    await _save_snapshot(page, reason="captcha_detected")
    if on_progress:
        on_progress("CAPTCHA detected — waiting for you to solve it...")
    _notify_shopee_captcha()

    # Poll every 2 seconds until the captcha is gone or timeout
    polls = timeout_s // 2
    for i in range(polls):
        await human_delay(min_ms=1_800, max_ms=2_200)
        if not await _detect_captcha_page(page):
            elapsed = (i + 1) * 2
            logger.info("Captcha resolved after ~%ds", elapsed)
            if on_progress:
                on_progress(f"CAPTCHA solved after ~{elapsed}s — resuming scrape")
            # Small grace period for page to finish loading
            await human_delay(min_ms=1_500, max_ms=3_000)
            return True

    logger.error("Captcha not solved within %ds", timeout_s)
    if on_progress:
        on_progress(f"CAPTCHA not solved within {timeout_s}s — aborting")
    return True


async def _handle_click_timeout(
    page: Page,
    error: Exception,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> bool:
    """Handle a Playwright click/interaction timeout as a potential captcha.

    Saves a snapshot for analysis, then triggers the captcha wait flow.
    Returns True if it looks like a captcha (waited for user), False otherwise.
    """
    err_msg = str(error).lower()
    if "timeout" not in err_msg:
        return False

    logger.warning("Click timeout — possible captcha. Saving snapshot...")
    await _save_snapshot(page, reason=f"click_timeout: {error}")

    # Notify and wait regardless of detection — the timeout itself is the signal
    if on_progress:
        on_progress("Interaction blocked — possible CAPTCHA. Waiting for you...")
    _notify_shopee_captcha()

    # Wait up to 3 min for page to become interactive again
    polls = 180 // 2
    for i in range(polls):
        await human_delay(min_ms=1_800, max_ms=2_200)
        # Consider resolved if URL changed away from captcha,
        # or if the original page elements become interactable
        if not await _detect_captcha_page(page):
            # Try a basic interaction to confirm page is usable
            try:
                await page.evaluate("document.title")
                elapsed = (i + 1) * 2
                logger.info("Page responsive after ~%ds", elapsed)
                if on_progress:
                    on_progress(f"Page unblocked after ~{elapsed}s — resuming")
                await human_delay(min_ms=1_500, max_ms=3_000)
                return True
            except Exception:
                continue

    logger.error("Page still blocked after 3 minutes")
    if on_progress:
        on_progress("Page still blocked after 3 minutes — aborting")
    return True

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

            # Check for captcha right after landing
            await _wait_for_captcha(page)

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

            # Check for captcha after search redirect
            await _wait_for_captcha(page)
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
    on_progress: Callable[[str], None] | None = None,
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

            # Items are saved to DB incrementally after each page inside
            # _scrape_all_pages, so nothing is lost if the job times out.
            items = await _do_shop_scrape(
                page, url, max_items=max_items, max_pages=max_pages,
                on_progress=on_progress,
            )

            # Record the overall scrape success
            try:
                conn = get_connection()
                init_schema(conn)
                record_scrape(conn, url, len(items), success=True)
                conn.close()
            except Exception:
                pass

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


async def _do_shop_scrape(
    page: Page,
    url: str,
    *,
    max_items: int = 200,
    max_pages: int = 20,
    on_progress: Callable[[str], None] | None = None,
    _retried: bool = False,
) -> tuple[ShopeeProduct, ...]:
    """Inner scrape logic for a shop page, with captcha-aware retry.

    If any Playwright timeout occurs, we snapshot the page, trigger the
    captcha notification + wait flow, then retry from navigation once.
    """
    try:
        # Navigate directly to the target URL
        if on_progress:
            on_progress("Navigating to shop page...")
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await human_delay(min_ms=2_000, max_ms=4_000)

        # Check for captcha right after landing
        await _wait_for_captcha(page, on_progress=on_progress)

        await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=5)
        await select_english(page)

        # Handle login if Shopee redirected us
        if "/buyer/login" in page.url:
            if on_progress:
                on_progress("Login required, authenticating...")
            if not await is_logged_in(page):
                logged_in = await login(page)
                if not logged_in:
                    return ()
                # After login, go to the actual target
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await human_delay(min_ms=2_000, max_ms=3_000)
                await _wait_for_captcha(page, on_progress=on_progress)
                await dismiss_popups_loop(page, interval_ms=2_000, max_rounds=3)

        # Wait for product cards to render (Shopee is a SPA)
        try:
            await page.wait_for_selector('a[href*="-i."]', timeout=15_000)
        except Exception:
            pass  # Proceed anyway -- page may have no products

        # Scrape all pages: scroll, parse, paginate
        # Items are saved to DB after each page so nothing is lost on timeout.
        if on_progress:
            on_progress("Scraping page 1...")
        items = await _scrape_all_pages(
            page, max_items, max_pages, on_progress, source_url=url,
        )

        # Extract shop name from URL
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

        return items

    except PlaywrightTimeout as e:
        # Any Playwright timeout is likely a captcha blocking interaction.
        # Snapshot the page state for analysis, notify, wait, then retry once.
        logger.warning("Playwright timeout during scrape: %s", e)
        await _save_snapshot(page, reason=f"playwright_timeout: {e}")

        if _retried:
            # Already retried once — give up
            raise

        if on_progress:
            on_progress("Timeout detected — possible CAPTCHA. Notifying...")
        _notify_shopee_captcha()

        # Wait up to 3 min for user to solve captcha
        polls = 180 // 2
        for i in range(polls):
            await human_delay(min_ms=1_800, max_ms=2_200)
            if not await _detect_captcha_page(page):
                elapsed = (i + 1) * 2
                logger.info("Page unblocked after ~%ds, retrying scrape", elapsed)
                if on_progress:
                    on_progress(f"Page unblocked after ~{elapsed}s — retrying...")
                await human_delay(min_ms=1_500, max_ms=3_000)
                return await _do_shop_scrape(
                    page, url,
                    max_items=max_items, max_pages=max_pages,
                    on_progress=on_progress, _retried=True,
                )

        # Timeout expired — re-raise so outer handler marks job as failed
        raise


def _save_to_db(source_url: str, items: tuple[ShopeeProduct, ...]) -> None:
    """Upsert scraped products to the database (no scrape log entry).

    Safe to call multiple times — uses upsert so duplicates are handled.
    """
    if not items:
        return
    try:
        conn = get_connection()
        init_schema(conn)
        upsert_products(conn, items, source_url)
        conn.close()
    except Exception as e:
        logger.warning("Failed to save %d items to database: %s", len(items), e)


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


async def _get_grid_bounds(page) -> tuple[float, float]:
    """Return the (top, bottom) Y offsets of the product grid on the page.

    Falls back to the middle 60% of the page if no product cards are found.
    """
    bounds = await page.evaluate("""() => {
        const cards = document.querySelectorAll('a[href*="-i."]');
        if (cards.length === 0) return null;
        let minTop = Infinity, maxBottom = 0;
        for (const card of cards) {
            const r = card.getBoundingClientRect();
            const absTop = r.top + window.scrollY;
            const absBottom = r.bottom + window.scrollY;
            if (absTop < minTop) minTop = absTop;
            if (absBottom > maxBottom) maxBottom = absBottom;
        }
        return { top: minTop, bottom: maxBottom };
    }""")
    if bounds:
        return (bounds["top"], bounds["bottom"])
    # Fallback: middle 60% of page
    page_height = await page.evaluate("document.body.scrollHeight")
    return (page_height * 0.2, page_height * 0.8)


async def _scroll_to_load(page, max_scrolls: int = 10) -> None:
    """Scroll through the product grid area to trigger lazy-loading.

    Instead of jumping to the very bottom (bot-like), scroll in
    increments within the grid region, like a user browsing products.
    """
    grid_top, grid_bottom = await _get_grid_bounds(page)
    viewport_h = await page.evaluate("window.innerHeight")

    # Start just above the grid
    current_y = max(0, grid_top - viewport_h * 0.3)
    await page.evaluate(
        f"window.scrollTo({{top: {current_y}, behavior: 'smooth'}})"
    )
    await human_delay(min_ms=800, max_ms=1_500)

    for _ in range(max_scrolls):
        previous_height = await page.evaluate("document.body.scrollHeight")

        # Scroll by roughly one viewport, with jitter
        step = viewport_h * (0.6 + secrets.randbelow(40) / 100.0)
        current_y = min(current_y + step, grid_bottom + viewport_h * 0.2)

        await page.evaluate(
            f"window.scrollTo({{top: {current_y}, behavior: 'smooth'}})"
        )
        await human_delay(min_ms=1_000, max_ms=2_000)

        new_height = await page.evaluate("document.body.scrollHeight")
        # Update grid bounds as more products load
        _, grid_bottom = await _get_grid_bounds(page)

        if new_height == previous_height and current_y >= grid_bottom:
            break


async def _hover_visible_card(page) -> None:
    """Move the mouse over a randomly chosen visible product card."""
    await page.evaluate("""() => {
        const cards = document.querySelectorAll('a[href*="-i."]');
        const visible = [];
        for (const card of cards) {
            const r = card.getBoundingClientRect();
            if (r.top >= 0 && r.bottom <= window.innerHeight) {
                visible.push(card);
            }
        }
        if (visible.length > 0) {
            const pick = visible[Math.floor(Math.random() * visible.length)];
            const r = pick.getBoundingClientRect();
            const x = r.left + r.width * (0.2 + Math.random() * 0.6);
            const y = r.top + r.height * (0.2 + Math.random() * 0.6);
            pick.dispatchEvent(new MouseEvent('mouseover', {
                bubbles: true, clientX: x, clientY: y
            }));
        }
    }""")


async def _simulate_browsing(page) -> None:
    """Simulate a human scanning the product grid before paginating.

    Each page visit gets a random "interest level":
      - LOW  (~40%): quick skim, 2-3 scroll steps, few hovers, short dwell
      - MED  (~35%): normal browse, 3-5 steps, some hovers, moderate dwell
      - HIGH (~25%): found something interesting — more steps, extra hovers,
                     scroll-backs, longer pauses (like reading descriptions)

    This produces highly variable per-page timing (2s - 25s+) which looks
    much more natural than a fixed cadence.
    """
    grid_top, grid_bottom = await _get_grid_bounds(page)
    viewport_h = await page.evaluate("window.innerHeight")
    viewport_w = await page.evaluate("window.innerWidth")
    grid_range = max(1, grid_bottom - grid_top - viewport_h)

    # Pick interest level for this page
    roll = secrets.randbelow(100)
    if roll < 40:
        interest = "low"
    elif roll < 75:
        interest = "med"
    else:
        interest = "high"

    # Tuning knobs per interest level
    config = {
        "low":  {"steps": (2, 3), "hover_pct": 20, "scroll_back": False,
                 "step_pause": (600, 1_500),  "hover_pause": (400, 900),
                 "end_pause": (500, 1_200)},
        "med":  {"steps": (3, 5), "hover_pct": 45, "scroll_back": False,
                 "step_pause": (1_000, 3_000), "hover_pause": (600, 1_500),
                 "end_pause": (1_000, 2_500)},
        "high": {"steps": (4, 7), "hover_pct": 65, "scroll_back": True,
                 "step_pause": (1_500, 5_000), "hover_pause": (800, 2_500),
                 "end_pause": (2_000, 5_000)},
    }
    cfg = config[interest]
    min_steps, max_steps = cfg["steps"]
    num_steps = min_steps + secrets.randbelow(max_steps - min_steps + 1)

    # Start at a random position within the top third of the grid
    start_offset = grid_top + secrets.randbelow(max(1, int(grid_range * 0.3)))
    await page.evaluate(
        f"window.scrollTo({{top: {start_offset}, behavior: 'smooth'}})"
    )
    await human_delay(min_ms=800, max_ms=1_500)

    step_size = grid_range / max(1, num_steps)
    current_y = float(start_offset)

    for step in range(num_steps):
        jitter = 0.75 + (secrets.randbelow(50) / 100.0)
        current_y = min(current_y + step_size * jitter, grid_bottom)

        await page.evaluate(
            f"window.scrollTo({{top: {current_y}, behavior: 'smooth'}})"
        )
        lo, hi = cfg["step_pause"]
        await human_delay(min_ms=lo, max_ms=hi)

        # Hover over a visible product card
        if secrets.randbelow(100) < cfg["hover_pct"]:
            await _hover_visible_card(page)
            lo, hi = cfg["hover_pause"]
            await human_delay(min_ms=lo, max_ms=hi)

        # Move mouse within the grid area (~30% chance)
        if secrets.randbelow(10) < 3:
            x = int(viewport_w * 0.2) + secrets.randbelow(max(1, int(viewport_w * 0.6)))
            y = int(viewport_h * 0.2) + secrets.randbelow(max(1, int(viewport_h * 0.6)))
            await page.mouse.move(x, y)
            await human_delay(min_ms=300, max_ms=800)

    # HIGH interest: scroll back up to re-check a product (~60% chance)
    if cfg["scroll_back"] and secrets.randbelow(10) < 6:
        back_to = grid_top + secrets.randbelow(max(1, int(grid_range * 0.5)))
        await page.evaluate(
            f"window.scrollTo({{top: {back_to}, behavior: 'smooth'}})"
        )
        await human_delay(min_ms=1_500, max_ms=4_000)
        # Hover the card they "came back for"
        await _hover_visible_card(page)
        await human_delay(min_ms=1_000, max_ms=3_000)

    # Final pause before paginating
    lo, hi = cfg["end_pause"]
    await human_delay(min_ms=lo, max_ms=hi)


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
    on_progress: Callable[[str], None] | None = None,
    source_url: str | None = None,
) -> tuple[ShopeeProduct, ...]:
    """Scroll, parse, and paginate through all pages of results.

    For each page: scrolls to load lazy items, parses products,
    deduplicates, then clicks next. Stops when max_items or max_pages
    is reached, or no next button exists.

    Saves to DB after each page so items are not lost if the job
    times out or hits a captcha mid-pagination.

    Args:
        page: Playwright page positioned on the first results page
        max_items: Maximum total products to collect
        max_pages: Maximum number of pages to scrape
        source_url: Original scrape URL, used for incremental DB saves

    Returns:
        Deduplicated tuple of ShopeeProduct, trimmed to max_items
    """
    all_items: list[ShopeeProduct] = []
    seen_urls: set[str] = set()

    for page_num in range(max_pages):
        await _scroll_to_load(page, max_scrolls=10)
        page_items = await parse_search_results(page, max_items)

        new_items: list[ShopeeProduct] = []
        for item in page_items:
            item_url = item.product_url or ""
            if item_url and item_url in seen_urls:
                continue
            if item_url:
                seen_urls.add(item_url)
            all_items.append(item)
            new_items.append(item)

        if on_progress:
            on_progress(f"Page {page_num + 1} — {len(all_items)} products")

        # Save new items immediately so they survive a timeout
        if new_items and source_url:
            _save_to_db(source_url, tuple(new_items))

        if len(all_items) >= max_items:
            break

        # Simulate human browsing before navigating to next page
        await _simulate_browsing(page)

        if on_progress:
            on_progress(f"Page {page_num + 1} done, navigating to page {page_num + 2}...")

        has_next = await _click_next_page(page)
        if not has_next:
            break

        # Captcha can appear after pagination
        await _wait_for_captcha(page, on_progress=on_progress)

    return tuple(all_items[:max_items])


def scrape_shop_page_sync(
    url: str,
    *,
    max_items: int = 200,
    max_pages: int = 20,
    on_progress: Callable[[str], None] | None = None,
) -> ShopeeScrapeResult:
    """Synchronous wrapper for scrape_shop_page."""
    return asyncio.run(
        scrape_shop_page(url, max_items=max_items, max_pages=max_pages, on_progress=on_progress)
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
