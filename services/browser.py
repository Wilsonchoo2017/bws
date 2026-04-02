"""Shared Camoufox browser utility for anti-detection scraping.

Extracted from shopee/browser.py for reuse across Brickset, BrickEconomy,
and other browser-based scrapers.

Includes ``PersistentBrowser`` -- a long-lived browser session that keeps
a Camoufox instance alive across multiple scraping tasks, avoiding the
cost of cold-starting Firefox every time.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Awaitable, Callable, Union

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext, Page

if TYPE_CHECKING:
    pass

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


# ---------------------------------------------------------------------------
# Persistent browser session
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrowserConfig:
    """Configuration for a persistent browser session."""

    profile_name: str
    headless: bool = True
    locale: str = "en-US"
    window: tuple[int, int] = (1366, 768)


class PersistentBrowser:
    """Long-lived Camoufox browser that stays open across scraping tasks.

    Runs its own asyncio event loop in a daemon thread so that the
    browser and Playwright page survive between synchronous executor
    calls (which would normally destroy everything via asyncio.run).

    Usage from synchronous code (e.g. scrape-queue executors)::

        browser = PersistentBrowser(BrowserConfig(profile_name="keepa"))
        result = browser.run(my_async_scrape_fn, set_number)
        # browser stays alive for the next task
        browser.close()  # only on shutdown

    The ``run`` method accepts an async callable that receives a ``Page``
    as its first argument, plus any extra positional args.
    """

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._browser: Any | None = None  # AsyncCamoufox context
        self._camoufox: AsyncCamoufox | None = None
        self._page: Page | None = None
        self._closed = False

    # -- public API --------------------------------------------------------

    def run(
        self,
        coro_fn: Callable[..., Awaitable[Any]],
        *args: Any,
        timeout: float = 280,
    ) -> Any:
        """Run an async function with a persistent page.

        Args:
            coro_fn: Async callable. Receives (page, *args).
            *args: Extra arguments forwarded to coro_fn.
            timeout: Max seconds before raising TimeoutError.

        Returns:
            Whatever coro_fn returns.
        """
        loop = self._ensure_loop()

        async def _run() -> Any:
            page = await self._ensure_page()
            return await coro_fn(page, *args)

        future = asyncio.run_coroutine_threadsafe(_run(), loop)
        try:
            return future.result(timeout=timeout)
        except Exception:
            # If the coroutine is still running, cancel it
            future.cancel()
            raise

    def close(self) -> None:
        """Shut down the browser and event loop."""
        self._closed = True
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._shutdown(), self._loop,
            )
            try:
                future.result(timeout=15)
            except Exception:
                logger.debug("Browser shutdown error", exc_info=True)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None
        self._browser = None
        self._page = None

    def restart(self) -> None:
        """Force-close the current page so the next run() gets a fresh browser.

        Use after a scrape failure that may indicate stale browser state
        (e.g. elements not found, page didn't load). The next call to
        run() will automatically launch a new browser via _ensure_page().
        """
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._shutdown(), self._loop,
            )
            try:
                future.result(timeout=10)
            except Exception:
                logger.debug("Browser restart shutdown error", exc_info=True)
        logger.info("Restarting persistent browser: %s", self._config.profile_name)

    @property
    def is_alive(self) -> bool:
        """True if the browser is running and usable."""
        return (
            not self._closed
            and self._browser is not None
            and self._page is not None
            and not self._page.is_closed()
        )

    # -- internals ---------------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever,
                    daemon=True,
                    name=f"browser-{self._config.profile_name}",
                )
                self._thread.start()
            return self._loop

    async def _ensure_page(self) -> Page:
        """Return the persistent page, launching the browser if needed."""
        if self._page and not self._page.is_closed():
            return self._page

        # Browser died or first launch -- (re)create everything
        await self._shutdown()

        cfg = self._config
        user_data_path = Path.home() / ".bws" / f"{cfg.profile_name}-profile"
        user_data_path.mkdir(parents=True, exist_ok=True)
        _clear_stale_profile_lock(user_data_path)

        self._camoufox = AsyncCamoufox(
            headless=cfg.headless,
            geoip=True,
            locale=cfg.locale,
            os="macos",
            humanize=True,
            persistent_context=True,
            user_data_dir=str(user_data_path),
            window=cfg.window,
        )
        self._browser = await self._camoufox.__aenter__()
        self._page = await self._browser.new_page()

        logger.info(
            "Launched persistent browser: %s (headless=%s)",
            cfg.profile_name, cfg.headless,
        )
        return self._page

    async def _shutdown(self) -> None:
        """Close the browser if it's open."""
        if self._camoufox is not None:
            try:
                await self._camoufox.__aexit__(None, None, None)
            except Exception:
                logger.debug("Browser close error", exc_info=True)
            self._camoufox = None
            self._browser = None
            self._page = None


# Global persistent browser instances (one per scraper type).
# Lazily initialized by get_persistent_browser().
_browsers: dict[str, PersistentBrowser] = {}
_browsers_lock = threading.Lock()


def get_persistent_browser(config: BrowserConfig) -> PersistentBrowser:
    """Get or create a persistent browser for the given profile.

    Thread-safe. Returns the same instance for the same profile_name.
    """
    with _browsers_lock:
        existing = _browsers.get(config.profile_name)
        if existing and not existing._closed:
            return existing
        browser = PersistentBrowser(config)
        _browsers[config.profile_name] = browser
        return browser


def close_all_browsers() -> None:
    """Shut down all persistent browsers. Call on application exit."""
    with _browsers_lock:
        for name, browser in _browsers.items():
            logger.info("Closing persistent browser: %s", name)
            browser.close()
        _browsers.clear()
