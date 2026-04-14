"""Async orchestration for the logged-in BrickLink listings fetch.

Navigates to the v2 catalog page (``#T=P`` tab), waits for the JS-rendered
store rows, then extracts per-listing data via ``page.evaluate``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.bricklink.listings_browser import (
    PROFILE_DIR,
    get_listings_browser,
    profile_exists,
)
from services.bricklink.listings_parser import (
    EXTRACT_JS,
    BricklinkListing,
    build_listings_url,
    parse_listings,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("bws.bricklink.listings_scraper")


_LISTING_ROW_SELECTOR = "table.pcipgInnerTable img[src*='/flagsS/']"
_WAIT_TIMEOUT_MS = 20_000
_SNAPSHOT_DIR = Path("logs/bricklink_snapshots")


class ListingsProfileMissing(RuntimeError):
    """Raised when the Camoufox profile has not been logged in yet."""


async def fetch_listings(page: "Page", set_number: str) -> list[BricklinkListing]:
    """Fetch and parse store listings for a single set.

    Must be called with a Page from the ``bricklink-listings`` profile.
    """
    url = build_listings_url(set_number)
    logger.info("Navigating to %s", url)
    await page.goto(url, wait_until="domcontentloaded")

    try:
        await page.wait_for_selector(_LISTING_ROW_SELECTOR, timeout=_WAIT_TIMEOUT_MS)
    except Exception as exc:
        await _save_snapshot(page, set_number, reason="wait_timeout")
        logger.warning("Listings did not render for %s: %s", set_number, exc)
        # Try activating the Price tab manually in case hash-routing
        # did not auto-select it, then wait once more.
        try:
            await page.evaluate(
                "() => { if (window.location.hash !== '#T=P') { "
                "window.location.hash = '#T=P'; "
                "window.dispatchEvent(new HashChangeEvent('hashchange')); } }",
            )
            await page.wait_for_selector(_LISTING_ROW_SELECTOR, timeout=_WAIT_TIMEOUT_MS)
        except Exception as retry_exc:
            await _save_snapshot(page, set_number, reason="retry_timeout")
            raise RuntimeError(
                f"Listings DOM never rendered for {set_number}: {retry_exc}"
            ) from retry_exc

    # Small settle delay so late-binding rows finish hydrating
    await asyncio.sleep(0.5)

    raw_rows: list[dict[str, Any]] = await page.evaluate(EXTRACT_JS)
    logger.info("Extracted %d raw listing rows for %s", len(raw_rows), set_number)
    listings = parse_listings(set_number, raw_rows)
    if not listings:
        await _save_snapshot(page, set_number, reason="empty_parse")
    return listings


def fetch_listings_sync(
    set_number: str,
    *,
    headless: bool = False,
    timeout: float = 120.0,
) -> list[BricklinkListing]:
    """Blocking wrapper around :func:`fetch_listings`.

    Raises ``ListingsProfileMissing`` if the profile has not been logged
    in yet.
    """
    if not profile_exists():
        raise ListingsProfileMissing(
            f"Profile {PROFILE_DIR} does not exist -- run "
            "`python -m scripts.bricklink_login` first to log in.",
        )

    browser = get_listings_browser(headless=headless)
    return browser.run(fetch_listings, set_number, timeout=timeout)


async def _save_snapshot(page: "Page", set_number: str, *, reason: str) -> Path | None:
    """Persist the rendered DOM to disk for post-mortem debugging."""
    try:
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        html = await page.content()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _SNAPSHOT_DIR / f"listings_{set_number}_{ts}_{reason}.html"
        path.write_text(html, encoding="utf-8")
        logger.info("Saved listings snapshot: %s (%d bytes)", path, len(html))
        return path
    except OSError as exc:
        logger.warning("Failed to save listings snapshot: %s", exc)
        return None
