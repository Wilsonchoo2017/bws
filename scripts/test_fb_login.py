"""Facebook Marketplace login + navigation test.

Standalone script to validate:
1. Camoufox launches with a persistent "facebook-seller" profile
2. Facebook login with auto-filled credentials
3. User completes 2FA manually
4. Navigation to Marketplace create-item page
5. Snapshots captured at every step for selector discovery

Usage:
    python scripts/test_fb_login.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from playwright.async_api import Page

from services.browser.helpers import human_delay, stealth_browser
from services.listing.snapshots import capture_listing_snapshot
from services.notifications.ntfy import (
    NTFY_TOPIC_ALERTS,
    NtfyMessage,
    send_notification,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s  %(message)s",
)
logger = logging.getLogger("bws.test_fb_login")

FB_URL = "https://www.facebook.com"
MARKETPLACE_CREATE_URL = "https://www.facebook.com/marketplace/create/item"
LOGIN_TIMEOUT_SECONDS = 300

# Credentials from env
FB_EMAIL = os.environ.get("FACEBOOK_EMAIL", "")
FB_PASSWORD = os.environ.get("FACEBOOK_PASSWORD", "")


async def _snap(page: Page, step: str) -> None:
    """Convenience wrapper for snapshot capture."""
    path = await capture_listing_snapshot(page, step)
    if path:
        logger.info("Snapshot saved: %s", path)


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
        except Exception as exc:
            logger.debug("Cookie banner selector %s failed: %s", selector, exc)
            continue


async def _is_logged_in(page: Page) -> bool:
    """Check if we are logged in to Facebook.

    Not logged in if: login form visible, URL indicates login/2FA/checkpoint,
    or the page is still on a loading spinner.
    """
    url = page.url

    # URL-based checks for login / 2FA / checkpoint pages
    not_logged_in_paths = (
        "/login",
        "/checkpoint/",
        "/two_step_verification/",
        "/two_factor/",
        "/recover/",
    )
    if any(path in url for path in not_logged_in_paths):
        logger.debug("Not logged in: URL contains login/2FA path")
        return False

    # The Facebook loading spinner shows the logo on a blank page.
    try:
        body_len = await page.evaluate(
            "() => (document.body.innerText || '').trim().length"
        )
        if body_len < 50:
            logger.debug("Page still loading (body_len=%d)", body_len)
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
                logger.debug("Login form detected via %s", selector)
                return False
        except Exception as exc:
            logger.debug("Login check selector %s failed: %s", selector, exc)

    return True


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


async def _fill_credentials(page: Page) -> None:
    """Auto-fill Facebook email and password.

    Handles both the full login page and the modal overlay that appears
    when visiting Marketplace while logged out.
    """
    if not FB_PASSWORD:
        logger.warning("FACEBOOK_PASSWORD not set -- skipping auto-fill")
        return

    logger.info("Auto-filling credentials for %s", FB_EMAIL)

    # Use JS to focus + clear + type to avoid overlay interception issues.
    # Facebook's modal has a div that intercepts pointer events, so
    # Playwright's .click() fails.  JS .focus() bypasses that.

    # Email -- try multiple selectors (modal uses name="email" with dynamic id)
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
            await page.keyboard.type(FB_EMAIL, delay=50)
            await human_delay(min_ms=500, max_ms=1_000)
            logger.info("Filled email field")
        except Exception as exc:
            logger.warning("Could not fill email: %s", exc)
    else:
        logger.warning("No visible email input found")

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
            await page.keyboard.type(FB_PASSWORD, delay=50)
            await human_delay(min_ms=500, max_ms=1_000)
            logger.info("Filled password field")
        except Exception as exc:
            logger.warning("Could not fill password: %s", exc)
    else:
        logger.warning("No visible password input found")

    await _snap(page, "fb_credentials_filled")

    # Click login button -- use JS click to bypass overlay interception
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


async def _wait_for_login(page: Page) -> bool:
    """Poll for up to 300s until login succeeds."""
    logger.info(
        "Waiting for login / 2FA completion. You have %d seconds.",
        LOGIN_TIMEOUT_SECONDS,
    )

    for i in range(LOGIN_TIMEOUT_SECONDS):
        await page.wait_for_timeout(1_000)

        if await _is_logged_in(page):
            logger.info("Facebook login successful!")
            await _snap(page, "fb_login_success")
            return True

        if i > 0 and i % 30 == 0:
            logger.info("Still waiting for login... %ds elapsed", i)
            await _snap(page, f"fb_login_waiting_{i}s")

    logger.warning("Login timed out after %d seconds", LOGIN_TIMEOUT_SECONDS)
    await _snap(page, "fb_login_timeout")
    return False


async def run() -> None:
    """Main test flow."""
    logger.info("Launching Camoufox with facebook-seller profile...")

    async with stealth_browser(
        headless=False,
        locale="en-MY",
        profile_name="facebook-seller",
    ) as browser:
        pages = browser.pages
        page = pages[0] if pages else await browser.new_page()

        # Step 1: Navigate directly to Facebook login page
        logger.info("Navigating to %s", FB_URL)
        await page.goto(FB_URL, wait_until="domcontentloaded")
        await human_delay(min_ms=2_000, max_ms=4_000)
        await _snap(page, "fb_initial_page")

        # Step 2: Dismiss cookie banner
        await _dismiss_cookie_banner(page)

        # Step 3: Login loop -- Facebook may redirect between pages,
        # so keep checking and re-filling until actually logged in.
        notified = False
        for attempt in range(3):
            if await _is_logged_in(page):
                logger.info("Logged in to Facebook")
                await _snap(page, "fb_logged_in")
                break

            logger.info("Not logged in (attempt %d) -- filling credentials", attempt + 1)
            await _fill_credentials(page)
            await _snap(page, f"fb_login_attempt_{attempt + 1}")

            if not notified:
                await _notify_2fa()
                notified = True

            # Wait for login to complete or for a redirect to settle
            logged_in = await _wait_for_login(page)
            if logged_in:
                break

            # If we timed out, take a snapshot and let the next loop
            # iteration re-check the state
            await _snap(page, f"fb_post_wait_attempt_{attempt + 1}")
            await human_delay(min_ms=2_000, max_ms=3_000)
        else:
            logger.error("Login failed after all attempts -- aborting")
            await asyncio.to_thread(input, "Press Enter to close browser...")
            return

        # Step 4: Navigate to Marketplace create page
        logger.info("Navigating to Marketplace create page...")
        await page.goto(MARKETPLACE_CREATE_URL, wait_until="domcontentloaded")
        await human_delay(min_ms=4_000, max_ms=6_000)
        await _snap(page, "fb_marketplace_create_page")

        # Check if marketplace also demands login (modal)
        if not await _is_logged_in(page):
            logger.warning("Marketplace showing login again -- filling credentials")
            await _fill_credentials(page)
            await _wait_for_login(page)
            # Re-navigate after login
            await page.goto(MARKETPLACE_CREATE_URL, wait_until="domcontentloaded")
            await human_delay(min_ms=4_000, max_ms=6_000)

        # Step 5: Extra wait for SPA hydration, then capture form discovery
        await page.wait_for_timeout(3_000)
        await _snap(page, "fb_form_discovery")

        logger.info("Done! Browser is open for manual inspection.")
        logger.info("Snapshots saved to ~/.bws/listing-debug/")
        logger.info("Check diagnostics.json for form selectors.")

        await asyncio.to_thread(input, "Press Enter to close browser...")


if __name__ == "__main__":
    asyncio.run(run())
