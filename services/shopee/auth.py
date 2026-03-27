"""Shopee login flow."""

from __future__ import annotations

from playwright.async_api import Page

from config.shopee_env import ShopeeCredentials, get_shopee_credentials
from services.shopee.browser import human_delay
from services.shopee.humanize import random_click, random_click_element, random_type
from services.shopee.popups import dismiss_popups

LOGIN_URL = "https://shopee.com.my/buyer/login"

# Selectors
SEL_USERNAME_INPUT = 'input[name="loginKey"]'
SEL_PASSWORD_INPUT = 'input[name="password"]'
SEL_LOGIN_BUTTON = 'button:has-text("Log In")'

# Indicators that we're logged in (any match = logged in)
LOGGED_IN_SELECTORS: tuple[str, ...] = (
    '[class*="navbar__username"]',
    '[class*="navbar__user"]',
    'a[href*="/user/account"]',
    '[class*="shopee-badge"]',
)


async def is_logged_in(page: Page) -> bool:
    """Check if the current session is already authenticated."""
    for selector in LOGGED_IN_SELECTORS:
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
    """Perform Shopee login.

    If auto_fill is True, fills in username and password from .env,
    then waits for you to complete 2FA/CAPTCHA manually.

    Either way, waits up to 5 minutes for login to complete.

    Args:
        page: Playwright page
        credentials: Optional credentials (loads from .env if not provided)
        auto_fill: Whether to auto-fill username/password fields

    Returns:
        True if login succeeded, False if timed out
    """
    if await is_logged_in(page):
        return True

    # Navigate to login page if not already there
    if "/buyer/login" not in page.url:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await human_delay(min_ms=1_000, max_ms=2_000)
        await dismiss_popups(page)

    if auto_fill:
        try:
            creds = credentials or get_shopee_credentials()

            # Type username with randomized click + keystroke timing
            await random_type(page, SEL_USERNAME_INPUT, creds.username)
            await human_delay()

            # Type password
            await random_type(page, SEL_PASSWORD_INPUT, creds.password)
            await human_delay()

            # Click login button at random position
            login_btn = await page.query_selector(SEL_LOGIN_BUTTON)
            if login_btn and await login_btn.is_visible():
                await random_click_element(login_btn)

        except Exception:
            pass

    # Wait up to 5 minutes for login to complete.
    # User may need to solve CAPTCHA or complete 2FA.
    print("Waiting for login to complete (solve CAPTCHA/2FA in the browser)...")
    print("You have 5 minutes to complete the login.")

    try:
        for _ in range(300):  # 300 seconds = 5 minutes
            await page.wait_for_timeout(1_000)

            current_url = page.url
            if "/buyer/login" not in current_url and "verify" not in current_url:
                await human_delay(min_ms=1_000, max_ms=2_000)
                if await is_logged_in(page):
                    print("Login successful!")
                    return True

        print("Login timed out after 5 minutes.")
        return False

    except Exception:
        return False
