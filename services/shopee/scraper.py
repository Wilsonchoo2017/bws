"""Shopee search and scraping orchestration."""


import asyncio
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from config.settings import SHOPEE_CONFIG
from db.connection import get_connection
from db.schema import init_schema
from services.shopee.auth import is_logged_in, login
from services.shopee.browser import shopee_browser, human_delay, new_page
from services.shopee.captcha_detection import (
    CaptchaSignals,
    detect_captcha,
    save_snapshot,
    snapshot_relative_path,
)
from services.shopee.captcha_events import record_event as record_captcha_event
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


class CaptchaPendingError(RuntimeError):
    """Raised when a captcha is detected and manual verification is required.

    The scraper persists a shopee_captcha_events row and raises this so the
    worker can return the job to the queue (status=blocked_verify) instead
    of blocking a worker slot for minutes.
    """

    def __init__(
        self,
        event_id: int,
        *,
        source_url: str,
        snapshot_dir: str,
        reason: str,
    ) -> None:
        super().__init__(
            f"Shopee captcha detected (event={event_id}, reason={reason})"
        )
        self.event_id = event_id
        self.source_url = source_url
        self.snapshot_dir = snapshot_dir
        self.reason = reason


def _notify_shopee_captcha(event_id: int | None = None) -> None:
    """Send ntfy alert so user can come solve the captcha."""
    suffix = f" (event #{event_id})" if event_id is not None else ""
    send_notification(
        NtfyMessage(
            title="Shopee: CAPTCHA detected",
            message=(
                "Shopee scraper hit a CAPTCHA / verification page"
                f"{suffix}. Open the Operations page and click "
                "'Verify now' to solve it."
            ),
            priority=5,
            tags=("warning", "robot"),
            topic="bws-alerts",
        )
    )


def _record_event_safely(
    *,
    source_url: str,
    snapshot_dir: Path | None,
    reason: str,
    signals: CaptchaSignals | None,
    job_id: str | None,
) -> int | None:
    """Persist a captcha event. Never raises — returns None on failure."""
    if snapshot_dir is None:
        return None
    try:
        conn = get_connection()
        init_schema(conn)
        event_id = record_captcha_event(
            conn,
            source_url=source_url,
            snapshot_dir=snapshot_relative_path(snapshot_dir),
            detection_reason=reason,
            detection_signals=signals.to_dict() if signals else None,
            job_id=job_id,
        )
        conn.close()
        return event_id
    except Exception:
        logger.exception("Failed to record captcha event")
        return None


async def _handle_captcha_detected(
    page: Page,
    signals: CaptchaSignals,
    *,
    source_url: str,
    job_id: str | None,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Persist event + notify, then either raise or block-wait (legacy mode).

    If SHOPEE_CONFIG.inline_captcha_wait is False (default), raises
    CaptchaPendingError after recording the event. Otherwise, polls for up to
    ~3 minutes waiting for the user to solve it inline.
    """
    reason = signals.reason
    logger.warning(
        "Captcha detected at %s (signals=%s)", signals.url or page.url, reason,
    )
    snap_dir = await save_snapshot(
        page,
        reason=f"captcha_detected:{reason}",
        signals=signals,
        job_id=job_id,
    )
    event_id = _record_event_safely(
        source_url=source_url,
        snapshot_dir=snap_dir,
        reason=reason,
        signals=signals,
        job_id=job_id,
    )
    _notify_shopee_captcha(event_id)
    if on_progress:
        on_progress(
            "CAPTCHA detected — open Operations page to verify"
            if not SHOPEE_CONFIG.inline_captcha_wait
            else "CAPTCHA detected — waiting for you to solve it..."
        )

    if not SHOPEE_CONFIG.inline_captcha_wait:
        raise CaptchaPendingError(
            event_id if event_id is not None else 0,
            source_url=source_url,
            snapshot_dir=str(snap_dir) if snap_dir else "",
            reason=reason,
        )

    # Legacy inline-wait path: poll until captcha is gone
    polls = 180 // 2
    for i in range(polls):
        await human_delay(min_ms=1_800, max_ms=2_200)
        follow_up = await detect_captcha(page)
        if not follow_up.detected:
            elapsed = (i + 1) * 2
            logger.info("Captcha resolved inline after ~%ds", elapsed)
            if on_progress:
                on_progress(f"CAPTCHA solved after ~{elapsed}s — resuming scrape")
            await human_delay(min_ms=1_500, max_ms=3_000)
            return

    logger.error("Captcha not solved within 180s (inline mode)")
    raise CaptchaPendingError(
        event_id if event_id is not None else 0,
        source_url=source_url,
        snapshot_dir=str(snap_dir) if snap_dir else "",
        reason=reason,
    )


async def _wait_for_captcha(
    page: Page,
    *,
    source_url: str = SHOPEE_BASE,
    job_id: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> bool:
    """Check for captcha; if present, record the event and notify.

    Default behaviour (inline_captcha_wait=False) raises CaptchaPendingError.
    Legacy behaviour blocks in-process for up to 3 minutes.

    Returns True if no captcha detected (so scraping can continue), False
    only in legacy mode when a captcha was seen-and-cleared inline.
    """
    signals = await detect_captcha(page)
    if not signals.detected:
        return True
    await _handle_captcha_detected(
        page, signals,
        source_url=source_url, job_id=job_id, on_progress=on_progress,
    )
    return False

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
            await _wait_for_captcha(page, source_url=SHOPEE_BASE)

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
            await _wait_for_captcha(page, source_url=SHOPEE_BASE)
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
    job_id: str | None = None,
) -> ShopeeScrapeResult:
    """Scrape all products from a Shopee shop/collection page.

    Navigates directly to the given URL (e.g. a shop collection page)
    and extracts all visible products. Handles popups, login redirects,
    scrolls to load lazy items, and paginates through all pages.

    Args:
        url: Full Shopee URL to scrape
        max_items: Maximum products to extract
        max_pages: Maximum number of pages to scrape
        job_id: Optional queue job id for correlating captcha events

    Returns:
        ShopeeScrapeResult with parsed products or error

    Raises:
        CaptchaPendingError: propagated (not wrapped) so the worker can
            return the job to the queue in blocked_verify state.
    """
    try:
        async with shopee_browser() as browser:
            page = await new_page(browser)
            setup_dialog_handler(page)

            # Items are saved to DB incrementally after each page inside
            # _scrape_all_pages, so nothing is lost if the job times out.
            items = await _do_shop_scrape(
                page, url, max_items=max_items, max_pages=max_pages,
                on_progress=on_progress, job_id=job_id,
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

    except CaptchaPendingError:
        _save_scrape_error(url, "captcha_pending — awaiting manual verification")
        raise
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
    job_id: str | None = None,
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
        await _wait_for_captcha(
            page, source_url=url, job_id=job_id, on_progress=on_progress,
        )

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
                await _wait_for_captcha(
                    page, source_url=url, job_id=job_id, on_progress=on_progress,
                )
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
            page, max_items, max_pages, on_progress,
            source_url=url, job_id=job_id,
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
        # The timeout itself is the signal even if detect_captcha() sees
        # nothing — we still record a snapshot and raise a pending event so
        # the user can manually clear Shopee's bot-check.
        logger.warning("Playwright timeout during scrape: %s", e)

        signals = await detect_captcha(page)
        reason = f"playwright_timeout:{signals.reason}"
        snap_dir = await save_snapshot(
            page,
            reason=reason,
            signals=signals,
            job_id=job_id,
            extra_meta={"exception": str(e)},
        )
        event_id = _record_event_safely(
            source_url=url,
            snapshot_dir=snap_dir,
            reason=reason,
            signals=signals,
            job_id=job_id,
        )
        _notify_shopee_captcha(event_id)
        if on_progress:
            on_progress(
                "Timeout detected — possible CAPTCHA. "
                "Open Operations page to verify."
            )

        if not SHOPEE_CONFIG.inline_captcha_wait:
            raise CaptchaPendingError(
                event_id if event_id is not None else 0,
                source_url=url,
                snapshot_dir=str(snap_dir) if snap_dir else "",
                reason=reason,
            ) from e

        if _retried:
            raise

        # Legacy inline-wait mode: block up to 3 min for user to solve
        polls = 180 // 2
        for i in range(polls):
            await human_delay(min_ms=1_800, max_ms=2_200)
            follow_up = await detect_captcha(page)
            if not follow_up.detected:
                elapsed = (i + 1) * 2
                logger.info("Page unblocked after ~%ds, retrying scrape", elapsed)
                if on_progress:
                    on_progress(f"Page unblocked after ~{elapsed}s — retrying...")
                await human_delay(min_ms=1_500, max_ms=3_000)
                return await _do_shop_scrape(
                    page, url,
                    max_items=max_items, max_pages=max_pages,
                    on_progress=on_progress, job_id=job_id, _retried=True,
                )
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
    job_id: str | None = None,
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
        # After the first few pages, reduce scroll/simulation intensity
        # to stay within the job timeout while still looking human.
        late_page = page_num >= 5
        await _scroll_to_load(page, max_scrolls=5 if late_page else 10)
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

        # Simulate human browsing before navigating to next page.
        # Skip simulation on late pages to save time — the initial pages
        # already established a human-like pattern.
        if not late_page:
            await _simulate_browsing(page)

        if on_progress:
            on_progress(f"Page {page_num + 1} done, navigating to page {page_num + 2}...")

        has_next = await _click_next_page(page)
        if not has_next:
            break

        # Captcha can appear after pagination
        await _wait_for_captcha(
            page,
            source_url=source_url or SHOPEE_BASE,
            job_id=job_id,
            on_progress=on_progress,
        )

    return tuple(all_items[:max_items])


def scrape_shop_page_sync(
    url: str,
    *,
    max_items: int = 200,
    max_pages: int = 20,
    on_progress: Callable[[str], None] | None = None,
    job_id: str | None = None,
) -> ShopeeScrapeResult:
    """Synchronous wrapper for scrape_shop_page."""
    return asyncio.run(
        scrape_shop_page(
            url, max_items=max_items, max_pages=max_pages,
            on_progress=on_progress, job_id=job_id,
        )
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
