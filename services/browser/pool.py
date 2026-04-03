"""Browser pool -- manages persistent browser instances.

The only public API that executors interact with.  Maps profile names
to :class:`PersistentBrowser` instances (which combine an
:class:`AsyncBridge` with a :class:`BrowserSession`).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Awaitable, Callable

from services.browser.bridge import AsyncBridge
from services.browser.config import BrowserConfig
from services.browser.process_guard import kill_browser_processes
from services.browser.session import BrowserSession

logger = logging.getLogger("bws.browser.pool")


class PersistentBrowser:
    """Long-lived Camoufox browser that stays open across scraping tasks.

    Composes :class:`AsyncBridge` (thread management) with
    :class:`BrowserSession` (page lifecycle).  This is the object
    returned by :func:`get_persistent_browser`.
    """

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._bridge = AsyncBridge(name=config.profile_name)
        self._session = BrowserSession(config)
        self._closed = False

    def run(
        self,
        coro_fn: Callable[..., Awaitable[Any]],
        *args: Any,
        timeout: float = 280,
    ) -> Any:
        """Run an async function with the persistent page."""
        if self._closed:
            raise RuntimeError(f"Browser '{self._config.profile_name}' is closed")

        async def _run() -> Any:
            page = await self._session.ensure_page()
            return await coro_fn(page, *args)

        return self._bridge.run(_run, timeout=timeout)

    def close(self) -> None:
        """Shut down the browser and event loop."""
        self._closed = True
        try:
            self._bridge.run(self._session.shutdown, timeout=5)
        except Exception:
            logger.debug("Browser shutdown error", exc_info=True)
        self._bridge.stop()
        kill_browser_processes(self._config.profile_name)

    def restart(self) -> None:
        """Force-close the page so the next run() gets a fresh browser."""
        if self._closed:
            return
        try:
            self._bridge.run(self._session.shutdown, timeout=10)
        except Exception:
            logger.debug("Browser restart shutdown error", exc_info=True)
        logger.info("Restarting persistent browser: %s", self._config.profile_name)

    @property
    def is_alive(self) -> bool:
        return not self._closed and self._session.is_alive


# ---------------------------------------------------------------------------
# Global pool -- one PersistentBrowser per profile
# ---------------------------------------------------------------------------

_browsers: dict[str, PersistentBrowser] = {}
_browsers_lock = threading.Lock()


def get_persistent_browser(config: BrowserConfig) -> PersistentBrowser:
    """Get or create a persistent browser for the given profile.

    Thread-safe.  Returns the same instance for the same profile_name.
    """
    with _browsers_lock:
        existing = _browsers.get(config.profile_name)
        if existing and not existing._closed:
            return existing
        browser = PersistentBrowser(config)
        _browsers[config.profile_name] = browser
        return browser


def close_all_browsers() -> None:
    """Shut down all persistent browsers.  Call on application exit."""
    with _browsers_lock:
        for name, browser in _browsers.items():
            logger.info("Closing persistent browser: %s", name)
            browser.close()
        _browsers.clear()
