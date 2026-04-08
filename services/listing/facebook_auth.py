"""Facebook login flow with 2FA device approval.

Navigates to Facebook, auto-fills credentials, sends an NTFY notification,
and waits for the user to approve the login on their mobile device.
"""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Page

from config.facebook_env import get_facebook_credentials
from services.browser.helpers import human_delay
from services.listing.snapshots import capture_listing_snapshot
from services.notifications.ntfy import (
    NTFY_TOPIC_ALERTS,
    NtfyMessage,
    send_notification,
)

logger = logging.getLogger("bws.listing.facebook_auth")

FB_URL = "https://www.facebook.com"

# URL fragments that indicate we are NOT logged in
_NOT_LOGGED_IN_PATHS: tuple[str, ...] = (
    "/login",
    "/checkpoint/",
    "/two_step_verification/",
    "/two_factor/",
    "/recover/",
)

# Max wait for 2FA completion
_LOGIN_TIMEOUT_SECONDS = 300


async def _find_visible(page: Page, selectors: tuple[str, ...]) -> object | None:
    """Return the first visible element matching any of the selectors."""
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return el
        except Exception:
            continue
    return None


async def _is_logged_in(page: Page) -> bool:
    """Check if we are logged in to Facebook.

    Not logged in if: login form visible, URL indicates login/2FA/checkpoint,
    or the page is still on a loading spinner.
    """
    url = page.url
    if any(path in url for path in _NOT_LOGGED_IN_PATHS):
        return False

    # Facebook loading spinner: blank page with minimal text
    try:
        body_len = await page.evaluate(
            "() => (document.body.innerText || '').trim().length"
        )
        if body_len < 50:
            return False
    except Exception:
        pass

    # Check for any visible login form inputs (page or modal)
    login_input_selectors = (
        "input#email",
        'input[name="email"][type="text"]',
        'input[name="email"][type="email"]',
        'input[name="pass"]',
    )
    for selector in login_input_selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return False
        except Exception:
            continue

    return True


async def _dismiss_cookie_banner(page: Page) -> None:
    """Dismiss Facebook cookie consent banner if present."""
    cookie_selectors = (
        'button[data-cookiebanner="accept_button"]',
        'button[title="Allow all cookies"]',
        'button[title="Allow essential and optional cookies"]',
        'button:has-text("Allow all cookies")',
        'button:has-text("Accept All")',
    )
    for selector in cookie_selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await el.click()
                logger.info("Dismissed cookie banner via %s", selector)
                await human_delay(min_ms=1_000, max_ms=2_000)
                return
        except Exception:
            continue


async def _fill_credentials(page: Page) -> None:
    """Auto-fill Facebook email and password using JS focus to bypass overlays."""
    creds = get_facebook_credentials()

    logger.info("Auto-filling credentials for %s", creds.email)

    # Email
    email_selectors = (
        "input#email",
        'input[name="email"][type="text"]',
        'input[name="email"][type="email"]',
        'input[name="email"]',
    )
    email_el = await _find_visible(page, email_selectors)
    if email_el:
        try:
            await email_el.evaluate("el => { el.focus(); el.value = ''; }")
            await page.keyboard.type(creds.email, delay=50)
            await human_delay(min_ms=500, max_ms=1_000)
            logger.info("Filled email field")
        except Exception as exc:
            logger.warning("Could not fill email: %s", exc)

    # Password
    pass_selectors = (
        "input#pass",
        'input[name="pass"]',
        'input[type="password"]',
    )
    pass_el = await _find_visible(page, pass_selectors)
    if pass_el:
        try:
            await pass_el.evaluate("el => { el.focus(); el.value = ''; }")
            await page.keyboard.type(creds.password, delay=50)
            await human_delay(min_ms=500, max_ms=1_000)
            logger.info("Filled password field")
        except Exception as exc:
            logger.warning("Could not fill password: %s", exc)

    await capture_listing_snapshot(page, "fb_credentials_filled")

    # Click login button via JS to bypass overlay interception
    login_selectors = (
        'button[name="login"]',
        'button[data-testid="royal_login_button"]',
        'div[role="button"]:has-text("Log in")',
        'div[role="button"]:has-text("Log In")',
        'button:has-text("Log in")',
        'button:has-text("Log In")',
        'button[type="submit"]',
    )
    login_el = await _find_visible(page, login_selectors)
    if login_el:
        await login_el.evaluate("el => el.click()")
        logger.info("Clicked login button")
        await human_delay(min_ms=2_000, max_ms=4_000)
    else:
        logger.warning("Could not find login button")


async def _notify_2fa() -> None:
    """Send NTFY notification asking user to complete 2FA."""
    await asyncio.to_thread(
        send_notification,
        NtfyMessage(
            title="Facebook: Login 2FA required",
            message=(
                "Complete 2FA in the browser window. "
                "You have 5 minutes."
            ),
            priority=5,
            tags=("warning", "key"),
            topic=NTFY_TOPIC_ALERTS,
        ),
    )


async def login(page: Page) -> bool:
    """Log in to Facebook.

    1. Navigate to Facebook
    2. Dismiss cookie banner
    3. Auto-fill credentials if not logged in
    4. Send NTFY notification for 2FA
    5. Wait up to 5 minutes for login completion
    6. Retry up to 3 times (Facebook may redirect between pages)

    Returns True if login succeeded, False on timeout.
    """
    # Navigate to Facebook
    current = page.url
    if not current.startswith("https://www.facebook.com"):
        await page.goto(FB_URL, wait_until="domcontentloaded")
        await human_delay(min_ms=2_000, max_ms=4_000)

    await capture_listing_snapshot(page, "fb_initial_page")
    await _dismiss_cookie_banner(page)

    notified = False
    for attempt in range(3):
        if await _is_logged_in(page):
            logger.info("Logged in to Facebook")
            await capture_listing_snapshot(page, "fb_logged_in")
            return True

        logger.info("Not logged in (attempt %d) -- filling credentials", attempt + 1)
        await _fill_credentials(page)

        if not notified:
            await _notify_2fa()
            notified = True

        logger.info(
            "Waiting for login / 2FA completion. You have %d seconds.",
            _LOGIN_TIMEOUT_SECONDS,
        )

        for i in range(_LOGIN_TIMEOUT_SECONDS):
            await page.wait_for_timeout(1_000)

            if await _is_logged_in(page):
                logger.info("Facebook login successful!")
                await capture_listing_snapshot(page, "fb_login_success")
                return True

            if i > 0 and i % 30 == 0:
                logger.info("Still waiting for login... %ds elapsed", i)

        await capture_listing_snapshot(page, f"fb_login_timeout_attempt_{attempt + 1}")
        await human_delay(min_ms=2_000, max_ms=3_000)

    logger.warning("Facebook login failed after all attempts")
    await capture_listing_snapshot(page, "fb_login_failed")
    return False
