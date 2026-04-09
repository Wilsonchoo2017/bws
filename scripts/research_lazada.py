"""Research script: launch CamoFox and explore Lazada Seller Center.

Opens a persistent browser, navigates to Lazada Seller Center login page,
and waits for manual login + 2FA. Then keeps the browser open for exploration.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import Page

from services.browser.config import BrowserConfig
from services.browser.pool import get_persistent_browser
from services.listing.snapshots import capture_listing_snapshot

SELLER_URL = "https://sellercenter.lazada.com.my/"

_CONFIG = BrowserConfig(
    profile_name="lazada-seller",
    headless=False,
    locale="en-MY",
    window=(1366, 768),
)


# URLs that mean we are NOT logged in yet
_NOT_LOGGED_IN = ("/login", "/register", "/account/login", "/apps/account/login")

# URLs that positively confirm we ARE in the seller dashboard
_DASHBOARD_INDICATORS = ("/apps/seller/", "/apps/product/", "/apps/order/", "/apps/home")


def _is_logged_in(url: str) -> bool:
    """Check if current URL indicates a logged-in seller dashboard state."""
    lower = url.lower()
    # Negative: still on login/registration pages
    if any(p in lower for p in _NOT_LOGGED_IN):
        return False
    # Positive: on a known dashboard path
    if any(p in lower for p in _DASHBOARD_INDICATORS):
        return True
    # Fallback: if on sellercenter domain without login/register, likely logged in
    return "sellercenter.lazada" in lower and "/apps/" in lower


async def _research(page: Page) -> str:
    """Navigate to Lazada Seller Center, wait for login, then snapshot."""
    print(f"\n>>> Navigating to {SELLER_URL}")
    await page.goto(SELLER_URL, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(3)
    await capture_listing_snapshot(page, "lazada_01_landing")
    print(f"Landing URL: {page.url}")

    # Click "Log In" link if we're on the registration page
    try:
        login_link = await page.query_selector('a:has-text("Log in")')
        if not login_link:
            login_link = await page.query_selector('a:has-text("Log In")')
        if login_link:
            print(">>> Found 'Log In' link, clicking...")
            await login_link.click()
            await asyncio.sleep(3)
            await capture_listing_snapshot(page, "lazada_02_login_page")
            print(f"Login page URL: {page.url}")
        else:
            print("No 'Log In' link found, checking page state...")
    except Exception as e:
        print(f"Could not click login link: {e}")

    # Poll for login (user logs in manually in the browser)
    print("\n=== Please log in manually in the browser window ===")
    print("Waiting for dashboard (polling every 5s, up to 5 min)...")

    for i in range(60):
        await asyncio.sleep(5)
        url = page.url
        if _is_logged_in(url):
            print(f"\nLogged in! URL: {url}")
            break
        if i % 6 == 0 and i > 0:
            print(f"  Still waiting... ({i * 5}s elapsed, URL: {url})")
    else:
        # Take a snapshot anyway to see where we ended up
        await capture_listing_snapshot(page, "lazada_timeout")
        print(f"Timed out. Final URL: {page.url}")
        return "Login timed out"

    await asyncio.sleep(3)
    await capture_listing_snapshot(page, "lazada_03_dashboard")
    print(f"Dashboard URL: {page.url}")

    # Navigate to Add Product
    add_url = SELLER_URL + "apps/product/publish"
    print(f"\n>>> Navigating to Add Product: {add_url}")
    await page.goto(add_url, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(5)
    await capture_listing_snapshot(page, "lazada_04_add_product")
    print(f"Add Product URL: {page.url}")

    # Scroll down to capture the full form
    for i in range(5):
        await page.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(2)
        await capture_listing_snapshot(page, f"lazada_05_form_scroll_{i}")
        print(f"Captured form scroll {i}")

    # Scroll back to top
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(1)

    # Keep browser open for 10 minutes
    print("\n=== Snapshots saved to ~/.bws/listing-debug/ ===")
    print("Browser staying open for 10 min for manual exploration.")
    await asyncio.sleep(600)

    return "Research session complete"


def main() -> None:
    browser = get_persistent_browser(_CONFIG)
    try:
        result = browser.run(_research, timeout=3600)  # 1 hour timeout
        print(f"\n{result}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
