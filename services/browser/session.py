"""Browser session -- single page lifecycle management.

Handles launching a Camoufox browser, creating a page, and
recovering from crashes.  Does NOT manage threads or event loops
(that is :class:`AsyncBridge`'s job).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from camoufox.async_api import AsyncCamoufox
from playwright._impl._errors import TargetClosedError
from playwright.async_api import Page

from services.browser.config import BrowserConfig
from services.browser.process_guard import clear_stale_profile_lock, kill_browser_processes

logger = logging.getLogger("bws.browser.session")


class BrowserSession:
    """Manages a single persistent Camoufox page.

    All methods are async and expected to run on the :class:`AsyncBridge`
    event loop.
    """

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._camoufox: AsyncCamoufox | None = None
        self._browser: Any | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page | None:
        return self._page

    @property
    def is_alive(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    async def ensure_page(self) -> Page:
        """Return the persistent page, launching the browser if needed."""
        if self._page and not self._page.is_closed():
            return self._page

        # Browser died or first launch -- shutdown + re-create.
        try:
            await self.shutdown()
        except (TargetClosedError, Exception):
            self._camoufox = None
            self._browser = None
            self._page = None

        cfg = self._config
        user_data_path = Path.home() / ".bws" / f"{cfg.profile_name}-profile"
        user_data_path.mkdir(parents=True, exist_ok=True)
        clear_stale_profile_lock(user_data_path)

        for _attempt in range(2):
            self._camoufox = AsyncCamoufox(
                headless=cfg.headless,
                geoip=True,
                locale=cfg.locale,
                os="macos",
                humanize=0.5,
                persistent_context=True,
                user_data_dir=str(user_data_path),
                window=cfg.window,
            )
            try:
                self._browser = await self._camoufox.__aenter__()
                self._page = await self._browser.new_page()
                break
            except TargetClosedError:
                logger.warning(
                    "Browser context died immediately for %s, retrying",
                    cfg.profile_name,
                )
                await self._safe_close_camoufox()
                kill_browser_processes(cfg.profile_name)
                await asyncio.sleep(1)
                continue
        else:
            raise RuntimeError(
                f"Failed to launch browser '{cfg.profile_name}' after retries"
            )

        logger.info(
            "Launched browser session: %s (headless=%s)",
            cfg.profile_name, cfg.headless,
        )
        return self._page

    async def shutdown(self) -> None:
        """Close the browser if it's open."""
        if self._camoufox is not None:
            try:
                await self._camoufox.__aexit__(None, None, None)
            except Exception:
                logger.debug("Browser close error", exc_info=True)
            self._camoufox = None
            self._browser = None
            self._page = None

    async def _safe_close_camoufox(self) -> None:
        try:
            if self._camoufox:
                await self._camoufox.__aexit__(None, None, None)
        except Exception:
            pass
        self._camoufox = None
        self._browser = None
        self._page = None
