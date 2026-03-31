"""Keepa login flow with captcha/bot detection notification."""

import logging
import secrets

from playwright.async_api import Page

from config.keepa_env import KeepaCredentials, get_keepa_credentials
from services.browser import human_delay
from services.notifications.ntfy import NtfyMessage, send_notification

logger = logging.getLogger("bws.keepa.auth")

# Selectors for detecting logged-in state
LOGGED_IN_SELECTORS: tuple[str, ...] = (
    "#panelUsername",
    "#panelUserMenu",
    "#UMElogout",
    "#panelLogout",
)

# Login form selectors
SEL_LOGIN_TRIGGER = "#panelUserRegisterLogin"
SEL_USERNAME_INPUT = "#username"
SEL_PASSWORD_INPUT = "#password"
SEL_SUBMIT_BUTTON = "#submitLogin"


async def is_logged_in(page: Page) -> bool:
    """Check if the current Keepa session is authenticated."""
    for selector in LOGGED_IN_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return True
        except Exception:
            continue
    return False


def _notify_login_captcha() -> None:
    """Send ntfy notification for login captcha."""
    send_notification(
        NtfyMessage(
            title="Keepa: Login requires intervention",
            message=(
                "Keepa login hit a CAPTCHA or verification challenge. "
                "Please open the browser window and solve it."
            ),
            priority=5,
            tags=("warning", "robot"),
        )
    )


async def login(
    page: Page,
    credentials: KeepaCredentials | None = None,
) -> bool:
    """Log into keepa.com.

    Auto-fills credentials, then waits up to 5 minutes for login
    to complete (user may need to solve CAPTCHA manually).

    Returns True if login succeeded, False on timeout.
    """
    if await is_logged_in(page):
        logger.info("Already logged into Keepa")
        return True

    creds = credentials or get_keepa_credentials()

    # Click the "Log In / Register" span to open the login modal
    try:
        login_trigger = await page.wait_for_selector(
            SEL_LOGIN_TRIGGER, timeout=10_000
        )
        if login_trigger:
            await login_trigger.click()
            await human_delay(1_500, 3_000)
    except Exception:
        logger.warning("Could not find login trigger, trying hash navigation")
        await page.goto("https://keepa.com/#!login", wait_until="domcontentloaded")
        await human_delay(2_000, 4_000)

    # Wait for username input to become visible, then fill it
    try:
        username_input = await page.wait_for_selector(
            SEL_USERNAME_INPUT, state="visible", timeout=10_000
        )
        if username_input:
            await username_input.click()
            await human_delay(300, 600)
            for char in creds.username:
                delay_ms = secrets.randbelow(70) + 50
                await page.keyboard.type(char, delay=delay_ms)
            await human_delay(500, 1_000)
    except Exception:
        logger.error("Could not find username input")
        return False

    # Fill password
    try:
        password_input = await page.wait_for_selector(
            SEL_PASSWORD_INPUT, state="visible", timeout=5_000
        )
        if password_input:
            await password_input.click()
            await human_delay(300, 600)
            for char in creds.password:
                delay_ms = secrets.randbelow(70) + 50
                await page.keyboard.type(char, delay=delay_ms)
            await human_delay(500, 1_000)
    except Exception:
        logger.error("Could not find password input")
        return False

    # Click submit
    try:
        submit_btn = await page.wait_for_selector(
            SEL_SUBMIT_BUTTON, state="visible", timeout=5_000
        )
        if submit_btn:
            await submit_btn.click()
            await human_delay(2_000, 4_000)
    except Exception:
        logger.warning("Could not find submit button, pressing Enter")
        await page.keyboard.press("Enter")
        await human_delay(2_000, 4_000)

    # Poll for login success (up to 5 minutes)
    notified = False
    max_polls = 300  # 5 minutes at 1s intervals
    for i in range(max_polls):
        if await is_logged_in(page):
            logger.info("Keepa login successful after %ds", i)
            return True

        # Send ntfy after 15 seconds if still not logged in
        if i == 15 and not notified:
            _notify_login_captcha()
            notified = True
            logger.info(
                "Waiting for login (CAPTCHA/2FA) -- ntfy notification sent"
            )

        await human_delay(900, 1_100)

    logger.error("Keepa login timed out after 5 minutes")
    return False
