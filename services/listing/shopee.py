"""Shopee Seller Center -- browser wiring and sync entry points."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from db.connection import get_connection
from services.bricklink.repository import get_set_minifigures
from services.browser.config import BrowserConfig
from services.browser.pool import get_persistent_browser
from services.items.repository import get_item_detail
from services.listing.auth import login
from services.listing.snapshots import capture_listing_snapshot
from services.listing.templates import (
    collect_image_paths,
    generate_listing_description,
    generate_listing_title,
    shipping_dimensions_cm,
    shipping_weight_kg,
)

logger = logging.getLogger("bws.listing.shopee")

_CONFIG = BrowserConfig(
    profile_name="shopee-seller",
    headless=False,
    locale="en-MY",
    window=(1366, 768),
)


async def _navigate_and_login(page: Page) -> bool:
    """Async implementation: navigate to Seller Center and log in."""
    return await login(page)


async def _create_listing(page: Page, set_number: str) -> bool:
    """Full listing flow: login, gather data, fill product form."""
    from services.listing.shopee_product import create_product

    # Step 1: Login -- then go straight to add product page
    logged_in = await login(page)
    if not logged_in:
        logger.error("Shopee login failed, cannot create listing")
        return False

    # Step 2: Gather item data from DB
    conn = get_connection()
    item = get_item_detail(conn, set_number)
    if not item:
        logger.error("Item %s not found in database", set_number)
        return False

    minifigures = get_set_minifigures(conn, set_number)
    image_paths = collect_image_paths(conn, set_number, max_photos=9)

    # Step 3: Generate title and description
    title = generate_listing_title(item)
    description = generate_listing_description(item, minifigures)

    # Step 4: Compute shipping values
    weight = shipping_weight_kg(item.get("weight"))
    dims = shipping_dimensions_cm(item.get("dimensions"))

    base_price = item.get("listing_price_cents")
    if not base_price:
        logger.error(
            "No listing price set for %s -- set it in the item detail page first",
            set_number,
        )
        return False

    # Shopee price is 5% above the base listing price
    listing_price = round(base_price * 1.05)

    if weight is None:
        logger.warning("No weight data for %s, using 1.0 kg", set_number)
        weight = 1.0

    if dims is None:
        logger.warning("No dimensions for %s, using 30x20x15 cm", set_number)
        dims = (20, 30, 15)

    logger.info(
        "Listing %s: price=RM%.2f, weight=%.2fkg, dims=%s, images=%d",
        set_number,
        listing_price / 100,
        weight,
        dims,
        len(image_paths),
    )

    # Step 5: Fill the product form
    success = await create_product(
        page,
        item=item,
        minifigures=minifigures,
        image_paths=image_paths,
        title=title,
        description=description,
        listing_price_cents=listing_price,
        weight_kg=weight,
        dims=dims,
    )

    # Step 6: Record listing in database
    if success:
        from services.listing.repository import record_listing
        record_listing(conn, set_number, "shopee", listing_price)

    return success


def navigate_and_login() -> bool:
    """Open Shopee Seller Center and log in (blocking)."""
    browser = get_persistent_browser(_CONFIG)
    return browser.run(_navigate_and_login)


def create_listing(set_number: str) -> bool:
    """Create a Shopee product listing for a LEGO set (blocking).

    Opens Seller Center, logs in, navigates to Add Product,
    and fills the form. Does NOT click Save -- user must review first.
    """
    browser = get_persistent_browser(_CONFIG)
    return browser.run(_create_listing, set_number, timeout=300)
