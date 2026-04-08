"""Shopee Seller Center login flow."""

import logging

from playwright.async_api import Page

from config.shopee_env import ShopeeCredentials, get_shopee_credentials
from services.shopee.browser import human_delay
from services.shopee.humanize import random_click_element, random_type
from services.shopee.popups import dismiss_popups

logger = logging.getLogger(__name__)

SELLER_URL = "https://seller.shopee.com.my"

# Selectors for the seller login form
SEL_USERNAME_INPUT = 'input[name="loginKey"]'
SEL_PASSWORD_INPUT = 'input[name="password"]'
SEL_LOGIN_BUTTON = 'button[type="submit"], button:has-text("Log In"), button:has-text("log in")'

# URL fragments that indicate we are NOT logged in
_LOGIN_PATHS: tuple[str, ...] = ("/account/signin", "/account/login", "/buyer/login")

# DOM indicators that we are on the seller dashboard (logged in)
_DASHBOARD_SELECTORS: tuple[str, ...] = (
    '[class*="sidebar"]',
    '[class*="dashboard"]',
    '[class*="shop-name"]',
    'a[href*="/portal/product"]',
)


async def is_logged_in(page: Page) -> bool:
    """Check if the current session is authenticated on Seller Center."""
    url = page.url
    if any(path in url for path in _LOGIN_PATHS):
        return False

    for selector in _DASHBOARD_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return True
        except Exception:
            continue
    return False


async def login(
    page: Page,
    credentials: ShopeeCredentials | None = None,
    auto_fill: bool = True,
) -> bool:
    """Log in to Shopee Seller Center.

    Auto-fills credentials, then waits up to 5 minutes for manual
    CAPTCHA / 2FA completion.

    Returns True if login succeeded, False on timeout.
    """
    if await is_logged_in(page):
        return True

    # Navigate to seller portal -- Shopee redirects to login if needed
    current = page.url
    if not current.startswith(SELLER_URL):
        await page.goto(SELLER_URL, wait_until="domcontentloaded")
        await human_delay(min_ms=1_500, max_ms=3_000)
        await dismiss_popups(page)

    if await is_logged_in(page):
        return True

    if auto_fill:
        try:
            creds = credentials or get_shopee_credentials()

            # Remove HTML5 pattern attributes that cause "did not match the
            # expected pattern" errors during character-by-character typing
            await page.evaluate("""() => {
                for (const input of document.querySelectorAll('input[pattern]')) {
                    input.removeAttribute('pattern');
                }
            }""")

            await random_type(page, SEL_USERNAME_INPUT, creds.username)
            await human_delay()

            await random_type(page, SEL_PASSWORD_INPUT, creds.password)
            await human_delay()

            login_btn = await page.query_selector(SEL_LOGIN_BUTTON)
            if login_btn and await login_btn.is_visible():
                await random_click_element(login_btn)

        except Exception:
            logger.warning("Auto-fill failed, falling back to manual login", exc_info=True)

    logger.info("Waiting for Seller Center login (solve CAPTCHA / 2FA in the browser)...")
    logger.info("You have 5 minutes.")

    try:
        for _ in range(300):
            await page.wait_for_timeout(1_000)

            url = page.url
            if not any(path in url for path in _LOGIN_PATHS):
                await human_delay(min_ms=1_000, max_ms=2_000)
                if await is_logged_in(page):
                    logger.info("Seller Center login successful!")
                    return True

        logger.warning("Seller Center login timed out after 5 minutes.")
        return False

    except Exception:
        logger.warning("Login wait interrupted", exc_info=True)
        return False
