"""One-shot BrickLink login helper.

Launches a headed Camoufox session against the ``bricklink-listings``
persistent profile so the user can log in manually.  Cookies are
persisted to ``~/.bws/bricklink-listings-profile/`` and will be picked
up automatically by the listings scraper on the next run.

Usage:
    python -m scripts.bricklink_login

After the browser opens:
    1. Navigate to any BrickLink page and log in (top-right "Sign in").
    2. Optionally open priceGuideSettings.asp and enable the
       "Show Seller Country" option so your account returns the
       enriched catalog rows.
    3. Visit https://www.bricklink.com/v2/catalog/catalogitem.page?S=10857-1#T=P
       to confirm you can see store rows with country flags.
    4. Press Ctrl+C in this terminal (or close the browser window)
       to persist the session.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.bricklink.listings_browser import PROFILE_NAME, PROFILE_DIR
from services.browser.helpers import stealth_browser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s  %(message)s",
)
logger = logging.getLogger("bws.bricklink_login")

BL_HOME = "https://www.bricklink.com/v2/main.page"


async def run() -> None:
    logger.info("Launching Camoufox with profile %s", PROFILE_NAME)
    logger.info("Profile dir: %s", PROFILE_DIR)

    async with stealth_browser(
        headless=False,
        locale="en-US",
        profile_name=PROFILE_NAME,
    ) as browser:
        pages = browser.pages
        page = pages[0] if pages else await browser.new_page()

        logger.info("Navigating to %s", BL_HOME)
        await page.goto(BL_HOME, wait_until="domcontentloaded")

        print()
        print("=" * 72)
        print("BrickLink login window is open.")
        print()
        print("  1. Click 'Sign in' (top right) and log in with your account.")
        print("  2. (Optional) Visit priceGuideSettings.asp and toggle any")
        print("     options you want persisted (e.g. show seller country).")
        print("  3. Verify you can see store rows at:")
        print("     https://www.bricklink.com/v2/catalog/catalogitem.page?S=10857-1#T=P")
        print("  4. Press Ctrl+C here (or close the window) to persist cookies.")
        print("=" * 72)
        print()

        try:
            while True:
                await asyncio.sleep(2)
                if page.is_closed():
                    logger.info("Page closed by user -- exiting.")
                    break
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Received interrupt -- closing browser and persisting profile.")

    logger.info("Profile saved at %s", PROFILE_DIR)
    logger.info("Run `python -m scripts.bricklink_listings_cli 10857-1` to test.")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
