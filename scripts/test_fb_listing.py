"""Facebook Marketplace end-to-end listing test.

Tests the full flow: login -> fill form for a given set number.
Uses the production modules (facebook_auth, facebook_product, templates).

Usage:
    python scripts/test_fb_listing.py <set_number>
    python scripts/test_fb_listing.py 71841
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from playwright.async_api import Page

from db.connection import get_connection
from services.bricklink.repository import get_set_minifigures
from services.browser.helpers import human_delay, stealth_browser
from services.items.repository import get_item_detail
from services.listing.facebook_auth import login
from services.listing.facebook_product import create_product
from services.listing.snapshots import capture_listing_snapshot
from services.listing.templates import (
    collect_image_paths,
    generate_listing_description,
    generate_listing_title,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s  %(message)s",
)
logger = logging.getLogger("bws.test_fb_listing")


async def run(set_number: str) -> None:
    """Full Facebook Marketplace listing test."""
    logger.info("Testing Facebook listing for set %s", set_number)

    async with stealth_browser(
        headless=False,
        locale="en-MY",
        profile_name="facebook-seller",
    ) as browser:
        pages = browser.pages
        page = pages[0] if pages else await browser.new_page()

        # Step 1: Login
        logged_in = await login(page)
        if not logged_in:
            logger.error("Login failed -- aborting")
            return

        # Step 2: Gather item data
        conn = get_connection()
        item = get_item_detail(conn, set_number)
        if not item:
            logger.error("Item %s not found in database", set_number)
            return

        minifigures = get_set_minifigures(conn, set_number)
        image_paths = collect_image_paths(conn, set_number, max_photos=10)

        title = generate_listing_title(item)
        description = generate_listing_description(
            item, minifigures, platform="facebook",
        )

        listing_price = item.get("listing_price_cents")
        if not listing_price:
            logger.error("No listing price set for %s", set_number)
            return

        logger.info("Title: %s", title)
        logger.info("Price: RM%.2f", listing_price / 100)
        logger.info("Images: %d", len(image_paths))
        logger.info("Description:\n%s", description)

        # Step 3: Fill the form (no submit)
        result = await create_product(
            page,
            image_paths=image_paths,
            title=title,
            description=description,
            listing_price_cents=listing_price,
            submit=False,
        )

        await capture_listing_snapshot(
            page,
            "fb_test_listing_complete",
            extra={
                "set_number": set_number,
                "title": title,
                "price_rm": listing_price / 100,
                "result": result,
            },
        )

        logger.info("Form filling %s. Browser open for review.", "succeeded" if result else "had issues")
        logger.info("Snapshots saved to ~/.bws/listing-debug/")

        await asyncio.to_thread(input, "Press Enter to close browser...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_fb_listing.py <set_number>")
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))
