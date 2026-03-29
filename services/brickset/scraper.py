"""Brickset browser scraper for LEGO set metadata.

Uses Camoufox/Playwright to load Brickset set pages and extract
metadata: RRP, retirement date, theme, subtheme, pieces.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

from services.brickset.parser import BricksetData, parse_brickset_page
from services.browser import human_delay, new_page, stealth_browser

logger = logging.getLogger(__name__)

BRICKSET_BASE_URL = "https://brickset.com/sets"


@dataclass(frozen=True)
class ScrapeResult:
    """Result of scraping a single Brickset set page."""

    set_number: str
    success: bool
    data: BricksetData | None = None
    error: str | None = None


async def scrape_set(
    set_number: str,
    *,
    page: object | None = None,
    headless: bool = True,
) -> ScrapeResult:
    """Scrape a single set page from Brickset.

    Args:
        set_number: LEGO set number (e.g. "75192").
        page: Optional Playwright page to reuse (avoids opening a new browser).
        headless: Run browser in headless mode.

    Returns:
        ScrapeResult with parsed data or error.
    """
    url = f"{BRICKSET_BASE_URL}/{set_number}-1"

    if page is not None:
        return await _scrape_page(page, url, set_number)

    async with stealth_browser(headless=headless, profile_name="brickset") as browser:
        p = await new_page(browser)
        try:
            return await _scrape_page(p, url, set_number)
        finally:
            await p.close()


async def scrape_batch(
    set_numbers: list[str],
    *,
    headless: bool = True,
    progress_callback: Callable[[int, int, ScrapeResult], None] | None = None,
    delay_min_ms: int = 5000,
    delay_max_ms: int = 12000,
) -> list[ScrapeResult]:
    """Scrape metadata for multiple sets from Brickset.

    Reuses a single browser instance for all sets with human-like
    delays between requests.

    Args:
        set_numbers: List of LEGO set numbers to scrape.
        headless: Run browser in headless mode.
        progress_callback: Called after each set with (current, total, result).
        delay_min_ms: Minimum delay between requests in ms.
        delay_max_ms: Maximum delay between requests in ms.

    Returns:
        List of ScrapeResult objects.
    """
    results: list[ScrapeResult] = []

    async with stealth_browser(headless=headless, profile_name="brickset") as browser:
        page = await new_page(browser)
        try:
            for idx, set_number in enumerate(set_numbers):
                if idx > 0:
                    await human_delay(delay_min_ms, delay_max_ms)

                result = await _scrape_page(
                    page,
                    f"{BRICKSET_BASE_URL}/{set_number}-1",
                    set_number,
                )
                results.append(result)

                if progress_callback is not None:
                    progress_callback(idx + 1, len(set_numbers), result)
        finally:
            await page.close()

    return results


def scrape_set_sync(set_number: str, *, headless: bool = True) -> ScrapeResult:
    """Synchronous wrapper for scrape_set."""
    return asyncio.run(scrape_set(set_number, headless=headless))


def scrape_batch_sync(
    set_numbers: list[str],
    *,
    headless: bool = True,
    progress_callback: Callable[[int, int, ScrapeResult], None] | None = None,
) -> list[ScrapeResult]:
    """Synchronous wrapper for scrape_batch."""
    return asyncio.run(
        scrape_batch(
            set_numbers,
            headless=headless,
            progress_callback=progress_callback,
        )
    )


async def _dismiss_consent(page: object) -> None:
    """Dismiss cookie consent dialog if present."""
    for selector in (
        ".qc-cmp2-summary-buttons button:first-child",
        "button.fc-cta-consent",
        'button:has-text("Consent")',
        'button:has-text("Accept")',
    ):
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click()
                await human_delay(1000, 2000)
                return
        except Exception:
            continue


async def _scrape_page(
    page: object,
    url: str,
    set_number: str,
) -> ScrapeResult:
    """Load a Brickset page and parse the HTML."""
    try:
        response = await page.goto(url, wait_until="load", timeout=30_000)

        if response is None or response.status >= 400:
            status = response.status if response else "no response"
            return ScrapeResult(
                set_number=set_number,
                success=False,
                error=f"HTTP {status}",
            )

        # Wait for JS rendering and dismiss cookie consent
        await human_delay(2000, 4000)
        await _dismiss_consent(page)

        html = await page.content()
        data = parse_brickset_page(html, set_number)

        logger.info(
            "Scraped %s: theme=%s, year_retired=%s, rrp=$%s, pieces=%s",
            set_number,
            data.theme,
            data.year_retired,
            f"{data.rrp_usd_cents / 100:.2f}" if data.rrp_usd_cents else "N/A",
            data.pieces,
        )

        return ScrapeResult(
            set_number=set_number,
            success=True,
            data=data,
        )

    except Exception as exc:
        logger.warning("Failed to scrape %s: %s", set_number, exc)
        return ScrapeResult(
            set_number=set_number,
            success=False,
            error=str(exc),
        )
