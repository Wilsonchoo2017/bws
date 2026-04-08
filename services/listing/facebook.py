"""Facebook Marketplace -- browser wiring and sync entry points."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from db.connection import get_connection
from services.bricklink.repository import get_set_minifigures
from services.browser.config import BrowserConfig
from services.browser.pool import get_persistent_browser
from services.items.repository import get_item_detail
from services.listing.facebook_auth import login
from services.listing.snapshots import capture_listing_snapshot
from services.listing.templates import (
    collect_image_paths,
    generate_listing_description,
    generate_listing_title,
)

logger = logging.getLogger("bws.listing.facebook")

_CONFIG = BrowserConfig(
    profile_name="facebook-seller",
    headless=False,
    locale="en-MY",
    window=(1366, 768),
)


async def _create_listing(page: Page, set_number: str) -> bool:
    """Full listing flow: Facebook login, gather data, fill form."""
    from services.listing.facebook_product import create_product

    # Step 1: Login (with 2FA device approval wait)
    logged_in = await login(page)
    if not logged_in:
        logger.error("Facebook login failed, cannot create listing")
        return False

    # Step 2: Gather item data from DB
    conn = get_connection()
    item = get_item_detail(conn, set_number)
    if not item:
        logger.error("Item %s not found in database", set_number)
        return False

    minifigures = get_set_minifigures(conn, set_number)
    image_paths = collect_image_paths(conn, set_number, max_photos=10, brand_border=False)

    # Step 3: Generate title and description (Facebook-specific)
    title = generate_listing_title(item)
    description = generate_listing_description(
        item, minifigures, platform="facebook",
    )

    listing_price = item.get("listing_price_cents")
    if not listing_price:
        logger.error(
            "No listing price set for %s -- set it in the item detail page first",
            set_number,
        )
        return False

    logger.info(
        "Listing %s on Facebook Marketplace: price=RM%.2f, images=%d",
        set_number,
        listing_price / 100,
        len(image_paths),
    )

    # Step 4: Fill the create-item form (does NOT publish by default)
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
        "fb_listing_complete",
        extra={
            "set_number": set_number,
            "title": title,
            "price_rm": listing_price / 100,
            "image_count": len(image_paths),
        },
    )

    return result


def create_listing(set_number: str) -> bool:
    """Create a Facebook Marketplace listing for a LEGO set (blocking).

    Opens Facebook, logs in, navigates to Marketplace create-item,
    fills the form, and leaves it for user review before publishing.
    """
    browser = get_persistent_browser(_CONFIG)
    return browser.run(_create_listing, set_number, timeout=600)
