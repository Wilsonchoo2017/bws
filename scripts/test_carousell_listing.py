"""Manual test: fill Carousell sell form WITHOUT submitting.

Usage:
    python -m scripts.test_carousell_listing [set_number]

Default set_number: 71841
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

SET_NUMBER = sys.argv[1] if len(sys.argv) > 1 else "71841"


def main() -> None:
    from db.connection import get_connection
    from services.bricklink.repository import get_set_minifigures
    from services.browser.config import BrowserConfig
    from services.browser.pool import get_persistent_browser
    from services.items.repository import get_item_detail
    from services.listing.carousell_auth import login
    from services.listing.carousell_product import create_product
    from services.listing.templates import (
        collect_image_paths,
        generate_listing_description,
        generate_listing_title,
    )

    config = BrowserConfig(
        profile_name="carousell-seller",
        headless=False,
        locale="en-MY",
        window=(1366, 768),
    )

    conn = get_connection()
    item = get_item_detail(conn, SET_NUMBER)
    if not item:
        print(f"Item {SET_NUMBER} not found in database")
        return

    minifigures = get_set_minifigures(conn, SET_NUMBER)
    image_paths = collect_image_paths(conn, SET_NUMBER, max_photos=10)
    title = generate_listing_title(item)
    description = generate_listing_description(
        item, minifigures, platform="carousell",
    )
    listing_price = item.get("listing_price_cents")
    if not listing_price:
        print(f"No listing price for {SET_NUMBER}")
        return

    print(f"Set: {SET_NUMBER}")
    print(f"Title: {title}")
    print(f"Price: RM{listing_price / 100:.2f}")
    print(f"Images: {len(image_paths)}")
    print(f"submit=False -- will NOT click List")
    print()

    async def _run(page):
        logged_in = await login(page)
        if not logged_in:
            print("Login failed")
            return False
        return await create_product(
            page,
            image_paths=image_paths,
            title=title,
            description=description,
            listing_price_cents=listing_price,
            submit=False,
        )

    browser = get_persistent_browser(config)
    result = browser.run(_run, timeout=600)
    print(f"\nResult: {'SUCCESS' if result else 'FAILED'}")


if __name__ == "__main__":
    main()
