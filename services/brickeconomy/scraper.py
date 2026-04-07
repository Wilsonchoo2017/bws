"""BrickEconomy scraper using Camoufox browser automation.

Navigates to BrickEconomy set pages, bypasses Cloudflare challenges,
and extracts all available data via the parser module.
"""

import asyncio
import logging
from dataclasses import dataclass

from config.settings import BRICKECONOMY_CONFIG, BRICKECONOMY_RATE_LIMITER
from services.brickeconomy.parser import BrickeconomySnapshot, parse_brickeconomy_page
from services.browser import human_delay, new_page, stealth_browser
from services.notifications.ntfy import NtfyMessage, send_notification

logger = logging.getLogger("bws.brickeconomy.scraper")

BRICKECONOMY_BASE = BRICKECONOMY_CONFIG.base_url

# Cloudflare challenge indicators (shared with Carousell)
_CF_CHALLENGE_TITLES = (
    "just a moment",
    "attention required",
    "checking your browser",
)

# DOM selectors that indicate a Cloudflare challenge page
_CF_CHALLENGE_SELECTORS = (
    "#challenge-running",
    "#challenge-stage",
    "#cf-challenge-running",
    ".cf-browser-verification",
    "#turnstile-wrapper",
    "#challenge-form",
)


@dataclass(frozen=True)
class BrickeconomyScrapeResult:
    """Result of a single BrickEconomy set scrape."""

    set_number: str
    success: bool
    snapshot: BrickeconomySnapshot | None = None
    error: str | None = None
    not_found: bool = False


def _notify_captcha(set_number: str) -> None:
    """Send ntfy notification asking user to solve a Cloudflare challenge."""
    send_notification(
        NtfyMessage(
            title="BrickEconomy: Cloudflare challenge",
            message=(
                f"BrickEconomy scrape for '{set_number}' hit a Cloudflare challenge. "
                "Please open the browser window and solve the captcha."
            ),
            priority=5,
            tags=("warning", "robot"),
        )
    )


async def _detect_cloudflare(page) -> bool:
    """Check if the current page is a Cloudflare challenge.

    Uses both title-based and DOM-based detection to catch silent
    CF blocks that don't set the usual challenge titles.
    """
    try:
        title = await page.title()
        if any(cf in title.lower() for cf in _CF_CHALLENGE_TITLES):
            return True
        # DOM-based detection for JS challenges / Turnstile
        cf_found = await page.evaluate(
            """() => {
                const selectors = %s;
                return selectors.some(s => document.querySelector(s) !== null);
            }"""
            % str(list(_CF_CHALLENGE_SELECTORS))
        )
        return cf_found
    except Exception:
        return False


async def _wait_for_cloudflare(
    page, set_number: str, timeout_s: int | None = None
) -> bool:
    """Wait for a Cloudflare challenge to be solved.

    Sends an ntfy notification, then polls until the challenge page
    is gone or the timeout is reached.

    Returns True if challenge was solved, False on timeout.
    """
    timeout = timeout_s or BRICKECONOMY_CONFIG.captcha_timeout_s
    logger.warning("Cloudflare challenge detected for set: %s", set_number)
    _notify_captcha(set_number)

    elapsed = 0
    poll_interval = 3
    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        if not await _detect_cloudflare(page):
            logger.info("Cloudflare challenge solved after %ds", elapsed)
            return True

    logger.error(
        "Cloudflare challenge timeout after %ds for set: %s", timeout, set_number
    )
    return False


async def scrape_set(
    set_number: str,
    *,
    headless: bool | None = None,
    page=None,
) -> BrickeconomyScrapeResult:
    """Scrape a single BrickEconomy set page.

    Args:
        set_number: LEGO set number (e.g. "40346-1").
        headless: Override headless setting. Defaults to config value.
        page: Reuse an existing Playwright page (for batch scraping).

    Returns:
        BrickeconomyScrapeResult with parsed snapshot or error.
    """
    if headless is None:
        headless = BRICKECONOMY_CONFIG.headless

    try:
        if page is not None:
            return await scrape_with_search(page, set_number)

        async with stealth_browser(
            headless=headless,
            locale=BRICKECONOMY_CONFIG.locale,
            profile_name="brickeconomy",
        ) as browser:
            p = await new_page(browser)
            return await scrape_with_search(p, set_number)

    except Exception as exc:
        logger.exception("BrickEconomy scrape failed for set: %s", set_number)
        return BrickeconomyScrapeResult(
            set_number=set_number,
            success=False,
            error=str(exc),
        )


async def _navigate_and_bypass_cf(page, url: str, set_number: str) -> bool:
    """Navigate to URL and handle Cloudflare. Returns True if successful."""
    await BRICKECONOMY_RATE_LIMITER.acquire()

    logger.info("Navigating to %s", url)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
    except Exception:
        logger.warning("Navigation timeout (15s) for %s", url)
        return False
    await human_delay(2_000, 4_000)

    if await _detect_cloudflare(page):
        solved = await _wait_for_cloudflare(page, set_number)
        if not solved:
            return False
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        except Exception:
            logger.warning("Navigation timeout (15s) after CF solve for %s", url)
            return False
        await human_delay(2_000, 4_000)

    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        logger.debug("networkidle timeout on %s, continuing anyway", url)
    await human_delay(1_000, 2_000)
    return True


async def _resolve_set_url(page, set_number: str) -> list[str]:
    """Use BrickEconomy search bar to find candidate set page URLs.

    Navigates to the homepage, types the set number into the search input,
    submits the ASP.NET form, then collects matching set links from results.

    Returns a list of candidate URLs ordered by relevance (best first).
    """
    # Navigate to homepage first
    if not await _navigate_and_bypass_cf(page, BRICKECONOMY_BASE, set_number):
        return []

    # Canary check: if the search input is missing, the page didn't
    # load properly (likely a silent Cloudflare block).
    has_search = await page.evaluate(
        "!!document.getElementById('txtSearchHeader')"
    )
    if not has_search:
        # Double-check for CF elements we might have missed
        if await _detect_cloudflare(page):
            logger.warning("Silent Cloudflare block detected on homepage for %s", set_number)
        else:
            logger.warning("Homepage loaded but search input missing for %s -- possible layout change or block", set_number)
        return []

    # Type the set number (just the number part, without -1 suffix)
    bare_number = set_number.split("-")[0]

    # Set value and submit via JS to bypass any overlays blocking clicks.
    # ASP.NET form postback causes full page navigation.
    async with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
        await page.evaluate(
            """(value) => {
                const input = document.getElementById('txtSearchHeader');
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                const btn = document.getElementById('cmdSearchHeader');
                if (btn) btn.click();
                else input.closest('form')?.submit();
            }""",
            bare_number,
        )

    await human_delay(2_000, 4_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        logger.debug("networkidle timeout on search results, continuing")
    await human_delay(1_000, 2_000)

    final_url = page.url

    # Check if the search redirected directly to a set page
    if "/set/" in final_url and bare_number in final_url:
        logger.info("Search redirected to %s", final_url)
        return [final_url]

    # Otherwise we're on a search results page -- find matching set links
    links = await page.evaluate(
        """(bareNumber) => {
            const results = [];
            const seen = new Set();
            const allLinks = document.querySelectorAll('a[href*="/set/"]');

            // First pass: exact set number matches (highest confidence)
            for (const a of allLinks) {
                const href = a.href || a.getAttribute('href') || '';
                if (seen.has(href)) continue;
                if (href.includes('/set/' + bareNumber + '-')
                    || href.includes('/set/' + bareNumber + '/')) {
                    results.push(href);
                    seen.add(href);
                }
            }

            // Second pass: number appears anywhere in URL
            for (const a of allLinks) {
                const href = a.href || a.getAttribute('href') || '';
                if (seen.has(href)) continue;
                if (href.includes(bareNumber)) {
                    results.push(href);
                    seen.add(href);
                }
            }

            // Third pass: remaining /set/ links (try in order)
            for (const a of allLinks) {
                const href = a.href || a.getAttribute('href') || '';
                if (seen.has(href)) continue;
                results.push(href);
                seen.add(href);
                if (results.length >= 5) break;
            }

            return results;
        }""",
        bare_number,
    )

    if links:
        logger.info("Found %d candidate URLs for %s: %s", len(links), set_number, links[0])
        return links

    logger.warning("Could not find set URL for %s in search results", set_number)
    return []


async def scrape_with_search(page, set_number: str) -> BrickeconomyScrapeResult:
    """Resolve the set URL via search bar, then scrape the page.

    Tries multiple search results in order of relevance before giving up.
    """
    candidates = await _resolve_set_url(page, set_number)
    if not candidates:
        return BrickeconomyScrapeResult(
            set_number=set_number,
            success=False,
            error=f"Could not find set on BrickEconomy: {set_number}",
            not_found=True,
        )

    # If _resolve_set_url already landed us on the set page, scrape current content
    current_url = page.url
    if "/set/" in current_url:
        result = await _scrape_current_page(page, set_number)
        if result.success:
            return result
        # Page was a 404/not-found -- try remaining candidates
        candidates = candidates[1:] if len(candidates) > 1 else []

    # Try each candidate URL until one succeeds
    for i, url in enumerate(candidates):
        logger.info("Trying search result %d/%d for %s: %s", i + 1, len(candidates), set_number, url)
        result = await _scrape_page(page, url, set_number)
        if result.success:
            return result
        logger.info("Result %d/%d for %s was not usable, trying next", i + 1, len(candidates), set_number)

    return BrickeconomyScrapeResult(
        set_number=set_number,
        success=False,
        error=f"Could not find set on BrickEconomy: {set_number}",
        not_found=True,
    )


async def _scrape_current_page(page, set_number: str) -> BrickeconomyScrapeResult:
    """Parse the page currently loaded in the browser."""
    final_url = page.url
    html = await page.content()
    title = await page.title()

    if _is_not_found(title, final_url):
        return BrickeconomyScrapeResult(
            set_number=set_number,
            success=False,
            error=f"Set not found on BrickEconomy: {set_number}",
            not_found=True,
        )

    snapshot = parse_brickeconomy_page(html, set_number, url=final_url)

    logger.info(
        "Scraped %s: value=%s, chart_points=%d, sales_months=%d",
        set_number,
        f"${snapshot.value_new_cents / 100:.2f}" if snapshot.value_new_cents else "N/A",
        len(snapshot.value_chart),
        len(snapshot.sales_trend),
    )

    return BrickeconomyScrapeResult(
        set_number=set_number,
        success=True,
        snapshot=snapshot,
    )


def _is_not_found(title: str, url: str) -> bool:
    """Check if the page is a 404 or search/not-found page."""
    t = title.lower()
    return (
        "not found" in t
        or "404" in t
        or "search" in t
        or "/search" in url
    )


async def _scrape_page(page, url: str, set_number: str) -> BrickeconomyScrapeResult:
    """Internal: navigate to a known set URL and parse it."""
    if not await _navigate_and_bypass_cf(page, url, set_number):
        return BrickeconomyScrapeResult(
            set_number=set_number,
            success=False,
            error="Cloudflare challenge not solved within timeout",
        )

    return await _scrape_current_page(page, set_number)


async def scrape_batch(
    set_numbers: list[str],
    *,
    headless: bool | None = None,
    on_progress: object | None = None,
) -> list[BrickeconomyScrapeResult]:
    """Scrape multiple sets with a single browser instance.

    Args:
        set_numbers: List of set numbers to scrape.
        headless: Override headless setting.
        on_progress: Callback(current, total, set_number) for progress reporting.

    Returns:
        List of BrickeconomyScrapeResult, one per set.
    """
    if headless is None:
        headless = BRICKECONOMY_CONFIG.headless

    results: list[BrickeconomyScrapeResult] = []

    try:
        async with stealth_browser(
            headless=headless,
            locale=BRICKECONOMY_CONFIG.locale,
            profile_name="brickeconomy",
        ) as browser:
            page = await new_page(browser)

            for i, set_number in enumerate(set_numbers):
                if on_progress:
                    on_progress(i + 1, len(set_numbers), set_number)

                result = await scrape_set(set_number, headless=headless, page=page)
                results.append(result)

                # Delay between sets
                if i < len(set_numbers) - 1:
                    await human_delay(
                        BRICKECONOMY_CONFIG.min_delay_ms,
                        BRICKECONOMY_CONFIG.max_delay_ms,
                    )

    except Exception as exc:
        logger.exception("BrickEconomy batch scrape failed")
        # Add error results for remaining sets
        scraped = {r.set_number for r in results}
        for sn in set_numbers:
            if sn not in scraped:
                results.append(
                    BrickeconomyScrapeResult(
                        set_number=sn,
                        success=False,
                        error=str(exc),
                    )
                )

    return results


def scrape_set_sync(
    set_number: str, *, headless: bool | None = None
) -> BrickeconomyScrapeResult:
    """Synchronous wrapper for scrape_set."""
    return asyncio.run(scrape_set(set_number, headless=headless))


def scrape_batch_sync(
    set_numbers: list[str], *, headless: bool | None = None
) -> list[BrickeconomyScrapeResult]:
    """Synchronous wrapper for scrape_batch."""
    return asyncio.run(scrape_batch(set_numbers, headless=headless))
