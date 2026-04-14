"""Camoufox browser wrapper for the BrickLink listings scraper.

A single persistent profile (``bricklink-listings``) lives under
``~/.bws/bricklink-listings-profile/``.  The user logs in once via
``scripts/bricklink_login.py``; after that, every subsequent run picks
up the cookies from that profile automatically.

This module is intentionally thin: it only builds a ``BrowserConfig``
and hands off to ``services.browser.get_persistent_browser``.  All the
lifecycle / thread / recovery machinery already exists there.
"""

from __future__ import annotations

from pathlib import Path

from services.browser import BrowserConfig, PersistentBrowser, get_persistent_browser

PROFILE_NAME = "bricklink-listings"
PROFILE_DIR = Path.home() / ".bws" / f"{PROFILE_NAME}-profile"


def build_browser_config(*, headless: bool = False) -> BrowserConfig:
    """Build the Camoufox config for the BrickLink listings profile.

    Default headless=False so the first-run login flow is visible; the
    CLI can override this for subsequent automated runs.
    """
    return BrowserConfig(
        profile_name=PROFILE_NAME,
        headless=headless,
        locale="en-US",
        window=(1440, 900),
    )


def get_listings_browser(*, headless: bool = False) -> PersistentBrowser:
    """Get (or create) the persistent BrickLink listings browser."""
    return get_persistent_browser(build_browser_config(headless=headless))


def profile_exists() -> bool:
    """Return True if the profile dir has been created by a prior run."""
    return PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())
