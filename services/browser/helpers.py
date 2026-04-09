"""Standalone browser helpers -- context manager and utilities."""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Union

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext, Page

from services.browser.process_guard import clear_stale_profile_lock


@asynccontextmanager
async def stealth_browser(
    *,
    headless: bool = True,
    locale: str = "en-US",
    profile_name: str = "default",
) -> AsyncGenerator[Union[Browser, BrowserContext], None]:
    """Launch a one-off Camoufox browser with anti-detection."""
    user_data_path = Path.home() / ".bws" / f"{profile_name}-profile"
    user_data_path.mkdir(parents=True, exist_ok=True)
    clear_stale_profile_lock(user_data_path)

    async with AsyncCamoufox(
        headless=headless,
        geoip=True,
        locale=locale,
        os="macos",
        humanize=0.5,
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
    """Random delay to simulate human timing.

    Uses a weighted distribution that clusters delays toward the lower
    end of the range (more natural than uniform) with occasional longer
    pauses. ~10% chance of an extra "distraction" delay.
    """
    spread = max_ms - min_ms
    # Take the minimum of two random samples to skew toward the lower end
    # (humans are usually quick with occasional slower moments)
    r1 = secrets.randbelow(spread + 1)
    r2 = secrets.randbelow(spread + 1)
    base_ms = min_ms + min(r1, r2)

    # ~10% chance of a longer "distraction" pause (checking phone, etc.)
    if secrets.randbelow(100) < 10:
        base_ms += secrets.randbelow(spread // 2 + 1)

    await asyncio.sleep(base_ms / 1000.0)
