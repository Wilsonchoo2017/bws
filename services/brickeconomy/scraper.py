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


@dataclass(frozen=True)
class BrickeconomyScrapeResult:
    """Result of a single BrickEconomy set scrape."""

    set_number: str
    success: bool
    snapshot: BrickeconomySnapshot | None = None
    error: str | None = None


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
    """Check if the current page is a Cloudflare challenge."""
    try:
        title = await page.title()
        return any(cf in title.lower() for cf in _CF_CHALLENGE_TITLES)
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

    url = f"{BRICKECONOMY_BASE}/set/{set_number}"

    try:
        if page is not None:
            return await _scrape_page(page, url, set_number)

        async with stealth_browser(
            headless=headless,
            locale=BRICKECONOMY_CONFIG.locale,
            profile_name="brickeconomy",
        ) as browser:
            p = await new_page(browser)
            return await _scrape_page(p, url, set_number)

    except Exception as exc:
        logger.exception("BrickEconomy scrape failed for set: %s", set_number)
        return BrickeconomyScrapeResult(
            set_number=set_number,
            success=False,
            error=str(exc),
        )


async def _scrape_page(page, url: str, set_number: str) -> BrickeconomyScrapeResult:
    """Internal: load a page and parse it."""
    await BRICKECONOMY_RATE_LIMITER.acquire()

    logger.info("Navigating to %s", url)
    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(2_000, 4_000)

    # Check for Cloudflare challenge
    if await _detect_cloudflare(page):
        solved = await _wait_for_cloudflare(page, set_number)
        if not solved:
            return BrickeconomyScrapeResult(
                set_number=set_number,
                success=False,
                error="Cloudflare challenge not solved within timeout",
            )
        # Reload after challenge solved
        await page.goto(url, wait_until="domcontentloaded")
        await human_delay(2_000, 4_000)

    # Wait for page content to fully load
    await page.wait_for_load_state("networkidle")
    await human_delay(1_000, 2_000)

    # Get final URL (after any redirects) and HTML
    final_url = page.url
    html = await page.content()

    # Check for 404 / not found
    title = await page.title()
    if "not found" in title.lower() or "404" in title:
        return BrickeconomyScrapeResult(
            set_number=set_number,
            success=False,
            error=f"Set not found on BrickEconomy: {set_number}",
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
