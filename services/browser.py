"""Shared Camoufox browser utility for anti-detection scraping.

Extracted from shopee/browser.py for reuse across Brickset, BrickEconomy,
and other browser-based scrapers.
"""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Union

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger("bws.browser")


def _clear_stale_profile_lock(profile_path: Path) -> None:
    """Remove Firefox profile lock files left by a crashed browser.

    Firefox/Camoufox uses .parentlock to prevent two instances from
    sharing a profile. If the browser crashes, the lock persists and
    blocks future launches (browser exits immediately with code 0).
    """
    for lock_name in (".parentlock", "parent.lock", "lock"):
        lock_file = profile_path / lock_name
        if lock_file.exists():
            logger.info("Removing stale profile lock: %s", lock_file)
            lock_file.unlink(missing_ok=True)


@asynccontextmanager
async def stealth_browser(
    *,
    headless: bool = True,
    locale: str = "en-US",
    profile_name: str = "default",
) -> AsyncGenerator[Union[Browser, BrowserContext], None]:
    """Launch a Camoufox browser with anti-detection.

    Uses persistent_context so cookies/fingerprint survive across sessions.

    Args:
        headless: Run in headless mode (True for scraping, False for debug).
        locale: Browser locale string.
        profile_name: Subdirectory under ~/.bws/ for persistent browser profile.

    Yields:
        BrowserContext -- use .new_page() on it.
    """
    user_data_path = Path.home() / ".bws" / f"{profile_name}-profile"
    user_data_path.mkdir(parents=True, exist_ok=True)
    _clear_stale_profile_lock(user_data_path)

    async with AsyncCamoufox(
        headless=headless,
        geoip=True,
        locale=locale,
        os="macos",
        humanize=True,
        persistent_context=True,
        user_data_dir=str(user_data_path),
        window=(1366, 768),
    ) as browser:
        yield browser


async def new_page(browser: Union[Browser, BrowserContext]) -> Page:
    """Create a new page from the browser or context."""
    return await browser.new_page()


async def human_delay(
    min_ms: int = 800,
    max_ms: int = 2500,
) -> None:
    """Random delay to simulate human timing."""
    delay_s = (min_ms + secrets.randbelow(max_ms - min_ms + 1)) / 1000.0
    await asyncio.sleep(delay_s)
