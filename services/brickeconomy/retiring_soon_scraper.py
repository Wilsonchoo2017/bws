"""Scrape the BrickEconomy 'Retiring Soon' list page.

Navigates to https://www.brickeconomy.com/sets/retiring-soon and extracts
set numbers from the listing. Uses the same Camoufox browser infrastructure
as the main BrickEconomy scraper.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from config.settings import BRICKECONOMY_CONFIG, BRICKECONOMY_RATE_LIMITER
from services.brickeconomy.scraper import _detect_cloudflare, _wait_for_cloudflare
from services.browser import human_delay, new_page, stealth_browser

logger = logging.getLogger("bws.brickeconomy.retiring_soon")

RETIRING_SOON_URL = f"{BRICKECONOMY_CONFIG.base_url}/sets/retiring-soon"


@dataclass(frozen=True)
class RetiringSoonResult:
    """Result of scraping the retiring-soon list page."""

    success: bool
    set_numbers: tuple[str, ...]
    error: str | None = None


def _extract_set_numbers_from_html(html: str) -> list[str]:
    """Extract set numbers from /set/ links in the HTML.

    Looks for links like /set/12345-1/lego-... and extracts the bare
    set number (without -1 suffix).
    """
    # Match /set/NNNNN-N/ patterns in href attributes
    pattern = re.compile(r'/set/(\d{3,6})-\d+/')
    matches = pattern.findall(html)
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


async def scrape_retiring_soon(
    *,
    headless: bool | None = None,
) -> RetiringSoonResult:
    """Scrape the BrickEconomy retiring-soon list page.

    Returns set numbers of all sets marked as retiring soon.
    """
    if headless is None:
        headless = BRICKECONOMY_CONFIG.headless

    try:
        async with stealth_browser(
            headless=headless,
            locale=BRICKECONOMY_CONFIG.locale,
            profile_name="brickeconomy",
        ) as browser:
            page = await new_page(browser)
            return await _scrape_retiring_soon_page(page)
    except Exception as exc:
        logger.exception("Failed to scrape retiring-soon page")
        return RetiringSoonResult(
            success=False,
            set_numbers=(),
            error=str(exc),
        )


async def _scrape_retiring_soon_page(page) -> RetiringSoonResult:
    """Navigate to the retiring-soon page and extract set numbers."""
    await BRICKECONOMY_RATE_LIMITER.acquire()

    logger.info("Navigating to %s", RETIRING_SOON_URL)
    try:
        await page.goto(
            RETIRING_SOON_URL,
            wait_until="domcontentloaded",
            timeout=30_000,
        )
    except Exception:
        logger.warning("Navigation timeout for retiring-soon page")
        return RetiringSoonResult(
            success=False, set_numbers=(), error="Navigation timeout"
        )

    await human_delay(2_000, 4_000)

    if await _detect_cloudflare(page):
        solved = await _wait_for_cloudflare(page, "retiring-soon-list")
        if not solved:
            return RetiringSoonResult(
                success=False,
                set_numbers=(),
                error="Cloudflare challenge not solved",
            )
        try:
            await page.goto(
                RETIRING_SOON_URL,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        except Exception:
            return RetiringSoonResult(
                success=False,
                set_numbers=(),
                error="Post-CF navigation timeout",
            )
        await human_delay(2_000, 4_000)

    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        logger.debug("networkidle timeout on retiring-soon, continuing")

    await human_delay(1_000, 2_000)

    # Extract set numbers from the page via JS for robustness
    set_numbers = await page.evaluate(
        """() => {
            const links = document.querySelectorAll('a[href*="/set/"]');
            const seen = new Set();
            const results = [];
            for (const a of links) {
                const href = a.href || a.getAttribute('href') || '';
                const match = href.match(/\\/set\\/(\\d{3,6})-\\d+\\//);
                if (match && !seen.has(match[1])) {
                    seen.add(match[1]);
                    results.push(match[1]);
                }
            }
            return results;
        }"""
    )

    # Fallback: parse HTML directly if JS extraction returned nothing
    if not set_numbers:
        html = await page.content()
        set_numbers = _extract_set_numbers_from_html(html)

    title = await page.title()
    logger.info(
        "Retiring-soon page: title='%s', found %d set numbers",
        title,
        len(set_numbers),
    )

    return RetiringSoonResult(
        success=True,
        set_numbers=tuple(set_numbers),
    )


def scrape_retiring_soon_sync(
    *, headless: bool | None = None,
) -> RetiringSoonResult:
    """Synchronous wrapper for scrape_retiring_soon."""
    return asyncio.run(scrape_retiring_soon(headless=headless))
