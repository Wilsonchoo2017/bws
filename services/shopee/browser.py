"""Camoufox browser lifecycle management with anti-detection."""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Union

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext, Page

from config.settings import SHOPEE_CONFIG


@asynccontextmanager
async def shopee_browser() -> AsyncGenerator[Union[Browser, BrowserContext], None]:
    """Launch a camoufox browser with anti-detection as an async context manager.

    Uses persistent_context so cookies/fingerprint survive across sessions.
    This is the strongest anti-detection measure -- Shopee sees a returning device.

    Yields:
        BrowserContext (persistent) -- use .new_page() on it.
    """
    user_data_path = Path(SHOPEE_CONFIG.user_data_dir).expanduser()
    user_data_path.mkdir(parents=True, exist_ok=True)

    async with AsyncCamoufox(
        headless=SHOPEE_CONFIG.headless,
        geoip=True,
        locale=SHOPEE_CONFIG.locale,
        os="macos",
        humanize=True,
        persistent_context=True,
        user_data_dir=str(user_data_path),
        window=(SHOPEE_CONFIG.viewport_width, SHOPEE_CONFIG.viewport_height),
    ) as browser:
        yield browser


async def new_page(browser: Union[Browser, BrowserContext]) -> Page:
    """Create a new page from the browser or context."""
    page = await browser.new_page()
    return page


async def human_delay(
    min_ms: int | None = None,
    max_ms: int | None = None,
) -> None:
    """Random delay to simulate human timing."""
    low = min_ms if min_ms is not None else SHOPEE_CONFIG.min_action_delay_ms
    high = max_ms if max_ms is not None else SHOPEE_CONFIG.max_action_delay_ms
    delay_s = (low + secrets.randbelow(high - low + 1)) / 1000.0
    await asyncio.sleep(delay_s)
