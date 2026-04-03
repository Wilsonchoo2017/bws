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
