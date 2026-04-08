"""Carousell -- browser wiring and sync entry points."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from db.connection import get_connection
from services.bricklink.repository import get_set_minifigures
from services.browser.config import BrowserConfig
from services.browser.pool import get_persistent_browser
from services.items.repository import get_item_detail
from services.listing.carousell_auth import login
from services.listing.templates import (
    collect_image_paths,
    generate_listing_description,
    generate_listing_title,
)

logger = logging.getLogger("bws.listing.carousell")

_CONFIG = BrowserConfig(
    profile_name="carousell-seller",
    headless=False,
    locale="en-MY",
    window=(1366, 768),
)


async def _create_listing(page: Page, set_number: str) -> bool:
    """Full listing flow: Google OAuth login, gather data, fill form."""
    from services.listing.carousell_product import create_product

    # Step 1: Login via Google OAuth (with NTFY + 2FA wait)
    logged_in = await login(page)
    if not logged_in:
        logger.error("Carousell login failed, cannot create listing")
        return False

    # Step 2: Gather item data from DB
    conn = get_connection()
    item = get_item_detail(conn, set_number)
    if not item:
        logger.error("Item %s not found in database", set_number)
        return False

    minifigures = get_set_minifigures(conn, set_number)
    image_paths = collect_image_paths(conn, set_number, max_photos=10)

    # Step 3: Generate title and description (Carousell-specific)
    title = generate_listing_title(item)
    description = generate_listing_description(
        item, minifigures, platform="carousell",
    )

    listing_price = item.get("listing_price_cents")
    if not listing_price:
        logger.error(
            "No listing price set for %s -- set it in the item detail page first",
            set_number,
        )
        return False

    logger.info(
        "Listing %s on Carousell: price=RM%.2f, images=%d",
        set_number,
        listing_price / 100,
        len(image_paths),
    )

    # Step 4: Fill the sell form and submit
    success = await create_product(
        page,
        image_paths=image_paths,
        title=title,
        description=description,
        listing_price_cents=listing_price,
        submit=True,
    )

    # Step 5: Record listing in database
    if success:
        from services.listing.repository import record_listing
        record_listing(conn, set_number, "carousell", listing_price)

    return success


def create_listing(set_number: str) -> bool:
    """Create a Carousell product listing for a LEGO set (blocking).

    Opens Carousell, logs in via Google OAuth, navigates to /sell,
    fills the form, and clicks 'List now' to publish.
    """
    browser = get_persistent_browser(_CONFIG)
    return browser.run(_create_listing, set_number, timeout=600)
