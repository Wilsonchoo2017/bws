"""Async bridge -- run async coroutines from synchronous code.

Manages a dedicated asyncio event loop in a daemon thread so that
Playwright pages can persist across multiple synchronous calls.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Awaitable, Callable

logger = logging.getLogger("bws.browser.bridge")


class AsyncBridge:
    """Run async functions on a dedicated event loop thread.

    The loop stays alive between calls so that state (browser pages,
    connections) persists.  Call :meth:`stop` to shut down.
    """

    def __init__(self, name: str = "browser") -> None:
        self._name = name
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Return the running event loop, creating it if needed."""
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever,
                    daemon=True,
                    name=f"async-bridge-{self._name}",
                )
                self._thread.start()
            return self._loop

    def run(
        self,
        coro_fn: Callable[..., Awaitable[Any]],
        *args: Any,
        timeout: float = 280,
    ) -> Any:
        """Schedule *coro_fn(*args)* on the loop and block until done."""
        loop = self.ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro_fn(*args), loop)
        try:
            return future.result(timeout=timeout)
        except Exception:
            future.cancel()
            raise

    def stop(self) -> None:
        """Stop the event loop and join the thread."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._loop = None
        self._thread = None
