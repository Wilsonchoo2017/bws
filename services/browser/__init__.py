"""Browser subsystem -- anti-detection browsing with Camoufox.

Decomposed into focused components:

- :mod:`~services.browser.config` -- ``BrowserConfig`` dataclass
- :mod:`~services.browser.session` -- ``BrowserSession`` (one page lifecycle)
- :mod:`~services.browser.bridge` -- ``AsyncBridge`` (thread + event loop)
- :mod:`~services.browser.process_guard` -- ``ProcessGuard`` (OS cleanup)
- :mod:`~services.browser.pool` -- ``BrowserPool`` (manages N instances)

Public API re-exported here for backward compatibility.
"""

from services.browser.config import BrowserConfig
from services.browser.pool import PersistentBrowser, close_all_browsers, get_persistent_browser
from services.browser.process_guard import clear_stale_profile_lock as _clear_stale_profile_lock
from services.browser.session import BrowserSession
from services.browser.helpers import human_delay, new_page, stealth_browser

__all__ = [
    "BrowserConfig",
    "BrowserSession",
    "PersistentBrowser",
    "_clear_stale_profile_lock",
    "close_all_browsers",
    "get_persistent_browser",
    "human_delay",
    "new_page",
    "stealth_browser",
]
