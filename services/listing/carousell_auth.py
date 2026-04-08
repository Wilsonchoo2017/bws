"""Carousell login flow via Google OAuth.

Navigates to the sell page, clicks "Continue with Google", sends an NTFY
notification, and waits for the user to complete Google login + 2FA manually.
"""

import logging

from playwright.async_api import Page

from services.browser.helpers import human_delay
from services.listing.snapshots import capture_listing_snapshot
from services.notifications.ntfy import (
    NTFY_TOPIC_ALERTS,
    NtfyMessage,
    send_notification,
)

logger = logging.getLogger("bws.listing.carousell_auth")

SELL_URL = "https://www.carousell.com.my/sell"

# Indicators that the user is NOT logged in (visible on the sell page)
_NOT_LOGGED_IN_SELECTORS: tuple[str, ...] = (
    'text="Login"',
    'text="Register"',
    'text="Log in or sign up"',
    'a[href*="/login"]',
)

# Max wait for Google OAuth + 2FA completion
_LOGIN_TIMEOUT_SECONDS = 300


async def _is_logged_in(page: Page) -> bool:
    """Check if the user is logged in by looking for login/register links.

    Carousell shows the sell form even when not logged in, so we check
    for the absence of login/register UI elements in the header.
    """
    for selector in _NOT_LOGGED_IN_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return False
        except Exception:
            continue
    # No login/register links visible -- assume logged in
    return True


async def _click_google_login(page: Page) -> bool:
    """Find and click the 'Continue with Google' button.

    Returns True if the button was found and clicked.
    """
    google_selectors = (
        'button:has-text("Continue with Google")',
        'button:has-text("Google")',
        '[data-testid*="google"]',
        'a:has-text("Google")',
    )
    for selector in google_selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await el.click()
                return True
        except Exception:
            continue
    return False


def _notify_2fa() -> None:
    """Send NTFY notification asking user to complete login."""
    send_notification(
        NtfyMessage(
            title="Carousell: Google login required",
            message=(
                "Complete Google login + 2FA in the browser window. "
                "You have 5 minutes."
            ),
            priority=5,
            tags=("warning", "key"),
            topic=NTFY_TOPIC_ALERTS,
        )
    )


async def login(page: Page) -> bool:
    """Log in to Carousell via Google OAuth.

    1. Navigate to /sell
    2. If not logged in, click "Continue with Google"
    3. Send NTFY notification
    4. Wait up to 5 minutes for manual login + 2FA completion

    Returns True if login succeeded, False on timeout.
    """
    # Navigate to sell page
    current = page.url
    if not current.startswith("https://www.carousell.com.my"):
        await page.goto(SELL_URL, wait_until="domcontentloaded")
        await human_delay(min_ms=2_000, max_ms=4_000)

    await capture_listing_snapshot(page, "carousell_initial_page")

    # Already logged in?
    if await _is_logged_in(page):
        logger.info("Already logged in to Carousell")
        await capture_listing_snapshot(page, "carousell_already_logged_in")
        return True

    # Click "Login" link in the header to get to the login page
    try:
        login_link = page.locator('text="Login"').or_(
            page.locator('a[href*="/login"]')
        )
        if await login_link.count() > 0:
            await login_link.first.click(timeout=10_000)
            await human_delay(min_ms=2_000, max_ms=3_000)
            logger.info("Clicked Login link")
            await capture_listing_snapshot(page, "carousell_login_page")
    except Exception as exc:
        logger.warning("Could not click Login link: %s", exc)

    # Try clicking "Continue with Google" on the login page
    clicked = await _click_google_login(page)
    if clicked:
        logger.info("Clicked 'Continue with Google'")
        await human_delay(min_ms=1_000, max_ms=2_000)
    else:
        logger.warning(
            "Could not find Google login button -- "
            "page may already be on Google login or different state"
        )

    await capture_listing_snapshot(page, "carousell_google_login")

    # Notify user to complete login manually
    _notify_2fa()
    logger.info(
        "Waiting for Google login + 2FA (solve in browser). "
        "You have %d seconds.",
        _LOGIN_TIMEOUT_SECONDS,
    )

    # Poll until logged in or timeout
    try:
        for i in range(_LOGIN_TIMEOUT_SECONDS):
            await page.wait_for_timeout(1_000)

            # Check if logged in (no login/register links visible)
            if await _is_logged_in(page):
                logger.info("Carousell login successful!")
                # Navigate back to /sell if we're not there
                if "/sell" not in page.url:
                    await page.goto(SELL_URL, wait_until="domcontentloaded")
                    await human_delay(min_ms=2_000, max_ms=3_000)
                await capture_listing_snapshot(
                    page, "carousell_login_success"
                )
                return True

            # Log progress every 30 seconds
            if i > 0 and i % 30 == 0:
                logger.info("Still waiting for login... %ds elapsed", i)

        logger.warning("Carousell login timed out after %d seconds", _LOGIN_TIMEOUT_SECONDS)
        await capture_listing_snapshot(page, "carousell_login_timeout")
        return False

    except Exception:
        logger.warning("Login wait interrupted", exc_info=True)
        await capture_listing_snapshot(page, "carousell_login_error")
        return False
