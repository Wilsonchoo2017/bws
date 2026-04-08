"""Carousell sell page -- automated product listing.

Fills the /sell form: photos, category, condition, title, item details,
description, price, buy button, and deal methods.
Captures DOM snapshots at EVERY step for R&D / selector discovery.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from services.browser.helpers import human_delay
from services.listing.snapshots import capture_listing_snapshot

logger = logging.getLogger("bws.listing.carousell_product")

SELL_URL = "https://www.carousell.com.my/sell"


# ---------------------------------------------------------------------------
# Snapshot helper -- captures at every interaction
# ---------------------------------------------------------------------------


async def _snap(page: Page, step: str, **extra: Any) -> None:
    """Convenience wrapper -- snapshot at every interaction."""
    await capture_listing_snapshot(
        page, f"carousell_{step}", extra=extra or None,
    )


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------


async def _upload_photos(page: Page, image_paths: list[Path]) -> None:
    """Upload product photos via the hidden file input (up to 10)."""
    if not image_paths:
        logger.warning("No images to upload")
        return

    await _snap(page, "before_photo_upload")

    try:
        file_input = page.locator('input[type="file"]').first
        str_paths = [str(p) for p in image_paths[:10]]
        await file_input.set_input_files(str_paths)
        await human_delay(3_000, 6_000)
        logger.info("Uploaded %d photos", len(str_paths))
    except Exception as exc:
        logger.warning("Photo upload failed: %s", exc)

    await _snap(
        page, "photos_uploaded",
        image_count=len(image_paths),
        paths=[str(p) for p in image_paths[:10]],
    )


async def _click_category_item(page: Page, text: str) -> bool:
    """Click a category item inside the category panel by its span text.

    The navbar also has "Hobbies & Toys" as an <a> link. Category panel
    items are <span> elements inside divs with category icon images.
    We use JS to find the correct element and click it.
    """
    try:
        clicked = await page.evaluate(
            """(text) => {
                // Find all spans matching the text
                const spans = [...document.querySelectorAll('span')].filter(
                    s => s.textContent.trim() === text
                );
                // Pick the one NOT inside a navbar <a> link
                for (const span of spans) {
                    if (span.closest('a[href*="top_navigation_bar"]')) continue;
                    if (span.closest('nav')) continue;
                    // Must be visible
                    const r = span.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        span.click();
                        return true;
                    }
                }
                return false;
            }""",
            text,
        )
        if clicked:
            return True
        logger.warning("Category item '%s': no matching span found via JS", text)
    except Exception as exc:
        logger.warning("Category item '%s' click failed: %s", text, exc)
    return False


async def _select_category(page: Page) -> None:
    """Select category: Hobbies & Toys > Toys & Games.

    The category picker is a panel on the right side of the sell form.
    We must avoid clicking the top navbar which also has "Hobbies & Toys".
    """
    await _snap(page, "before_category")

    # Ensure the category panel is open/visible
    try:
        cat_header = page.locator('text="Select a category"')
        if await cat_header.count() > 0:
            await cat_header.first.click(timeout=10_000)
            await human_delay(1_000, 2_000)
    except Exception as exc:
        logger.warning("Category header click failed: %s", exc)

    await _snap(page, "category_picker_opened")

    # Level 1: Click "Hobbies & Toys" in the category panel
    clicked = await _click_category_item(page, "Hobbies & Toys")
    if not clicked:
        logger.warning("'Hobbies & Toys' not found in category panel")
        await _snap(page, "category_hobbies_not_found")
        return
    await human_delay(800, 1_500)
    logger.info("Selected: Hobbies & Toys")
    await _snap(page, "category_hobbies_selected")

    # Level 2: Click "Toys & Games" in the subcategory list
    clicked = await _click_category_item(page, "Toys & Games")
    if not clicked:
        logger.warning("'Toys & Games' not found in category panel")
        await _snap(page, "category_toys_not_found")
        return
    await human_delay(800, 1_500)
    logger.info("Selected: Toys & Games")
    await _snap(page, "category_set")


async def _set_condition(page: Page) -> None:
    """Select 'Brand new' condition chip."""
    await _snap(page, "before_condition")

    try:
        brand_new = page.get_by_text("Brand new", exact=True).first
        await brand_new.click(timeout=10_000)
        await human_delay(500, 1_000)
        logger.info("Condition set to: Brand new")
    except Exception as exc:
        logger.warning("'Brand new' chip not found: %s", exc)

    await _snap(page, "condition_set")


async def _fill_title(page: Page, title: str) -> None:
    """Fill the listing title input."""
    await _snap(page, "before_title")

    try:
        title_input = page.locator(
            'input#title'
        ).or_(
            page.locator('input[name="field_title"]')
        ).or_(
            page.locator('input[placeholder*="Name your listing" i]')
        )
        await title_input.first.click(timeout=10_000)
        await human_delay(200, 400)
        await page.keyboard.type(title, delay=40)
        await human_delay(500, 1_000)
        logger.info("Title filled: %s", title[:60])
    except Exception as exc:
        logger.warning("Title input failed: %s", exc)

    await _snap(page, "title_filled", title=title[:80])


async def _fill_item_details(page: Page) -> None:
    """Fill Type dropdown and Age Range selection."""
    await _snap(page, "before_item_details")

    # Type dropdown -- custom dropdown with role="listbox" trigger button
    # Container: id="FieldSetField-Container-field_type_enum"
    try:
        type_btn = page.locator(
            '#FieldSetField-Container-field_type_enum button[role="listbox"]'
        ).or_(
            page.locator('button[role="listbox"]:has(span:text-is("Type"))')
        )
        if await type_btn.count() > 0:
            await type_btn.first.click(timeout=10_000)
            await human_delay(800, 1_500)
            logger.info("Type dropdown opened")
            await _snap(page, "type_dropdown_opened")

            # Select "Bricks & Building Blocks" from the list
            option = page.get_by_text("Bricks & Building Blocks", exact=True)
            if await option.count() > 0:
                await option.first.click(timeout=5_000)
                await human_delay(500, 1_000)
                logger.info("Type set to: Bricks & Building Blocks")
            else:
                logger.warning("'Bricks & Building Blocks' option not found")
        else:
            logger.warning("Type dropdown button not found")
    except Exception as exc:
        logger.warning("Type dropdown interaction failed: %s", exc)

    await _snap(page, "type_dropdown")

    # Age Range -- select "Adults" or "older than 12"
    try:
        adults = page.get_by_text("Adults", exact=True)
        if await adults.count() > 0:
            await adults.first.click(timeout=5_000)
            await human_delay(500, 1_000)
            logger.info("Age Range set to: Adults")
        else:
            older = page.get_by_text("older than 12", exact=True)
            if await older.count() > 0:
                await older.first.click(timeout=5_000)
                await human_delay(500, 1_000)
                logger.info("Age Range set to: older than 12")
    except Exception as exc:
        logger.warning("Age Range selection failed: %s", exc)

    await _snap(page, "item_details_filled")


async def _fill_description(page: Page, description: str) -> None:
    """Fill the description textarea."""
    await _snap(page, "before_description")

    try:
        desc_input = page.locator(
            'textarea[name="field_description"]'
        ).or_(
            page.locator('textarea[placeholder*="Include any other" i]')
        ).or_(
            page.locator('textarea')
        )
        await desc_input.first.click(timeout=10_000)
        await human_delay(200, 500)
        await page.keyboard.type(description, delay=15)
        await human_delay(500, 1_000)
        logger.info("Description filled (%d chars)", len(description))
    except Exception as exc:
        logger.warning("Description fill failed: %s", exc)

    await _snap(page, "description_filled")


async def _set_price(page: Page, price_cents: int) -> None:
    """Fill the price field in RM."""
    await _snap(page, "before_price")

    price_rm = price_cents / 100
    # Use decimals if not a whole number
    price_str = f"{price_rm:.2f}" if price_rm % 1 else f"{price_rm:.0f}"

    try:
        price_input = page.locator(
            'input#price'
        ).or_(
            page.locator('input[name="field_price"]')
        ).or_(
            page.locator('input[placeholder*="Price of your listing" i]')
        )
        await price_input.first.scroll_into_view_if_needed()
        await human_delay(500, 1_000)
        await price_input.first.click(timeout=10_000)
        await human_delay(200, 400)
        await page.keyboard.type(price_str, delay=60)
        await human_delay(500, 1_000)
        logger.info("Price set to RM %s", price_str)
    except Exception as exc:
        logger.warning("Price input failed: %s", exc)

    await _snap(page, "price_set", price_rm=price_str)


async def _disable_buy_button(page: Page) -> None:
    """Select 'Disable Buy button' radio and confirm the dialog."""
    await _snap(page, "before_buy_button")

    # The Buy button section has two radio inputs:
    #   value="true" (Enable) and value="false" (Disable)
    # Click the "Disable 'Buy' button" radio via JS to avoid visibility issues
    try:
        clicked = await page.evaluate("""() => {
            // Find the radio with value="false" (Disable)
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const radio of radios) {
                if (radio.value === 'false') {
                    radio.click();
                    return true;
                }
            }
            // Fallback: find by text
            const labels = [...document.querySelectorAll('span, p, label')];
            for (const el of labels) {
                if (el.textContent.includes("Disable") && el.textContent.includes("Buy")) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")

        if clicked:
            logger.info("Clicked Disable Buy button radio")
            await human_delay(1_000, 2_000)
        else:
            logger.warning("Disable Buy button radio not found")
    except Exception as exc:
        logger.warning("Disable Buy button click failed: %s", exc)

    await _snap(page, "buy_button_clicked")

    # Handle the confirmation dialog: "Disable the 'Buy' button and remove
    # delivery options?" with "Disable anyway" button
    try:
        clicked = await page.evaluate("""() => {
            const buttons = [...document.querySelectorAll('button')];
            for (const btn of buttons) {
                const text = btn.textContent.trim().toLowerCase();
                if (text.includes('disable anyway')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        if clicked:
            await human_delay(1_000, 2_000)
            logger.info("Confirmed: Disable anyway")
        else:
            logger.info("No 'Disable anyway' dialog appeared")
    except Exception as exc:
        logger.warning("Disable anyway dialog handling failed: %s", exc)

    await _snap(page, "buy_button_disabled")


async def _set_deal_methods(page: Page) -> None:
    """Enable both Meet-up and Delivery toggles.

    Carousell uses hidden checkbox inputs for these toggles. The visible
    toggle wrapper is a clickable div next to the label text. We use JS
    to find and click the correct toggle for each deal method.
    """
    await _snap(page, "before_deal_methods")

    # Enable Meet-up toggle
    try:
        clicked = await page.evaluate("""() => {
            const elems = [...document.querySelectorAll('p, span, label')];
            for (const el of elems) {
                if (el.textContent.trim() !== 'Meet-up') continue;
                const row = el.closest('div[class]');
                if (!row) continue;
                const toggle = row.querySelector(
                    '[class*="toggle"], [class*="switch"], [role="switch"]'
                );
                if (toggle) { toggle.click(); return 'toggle'; }
                const checkbox = row.querySelector('input[type="checkbox"]');
                if (checkbox && !checkbox.checked) {
                    (checkbox.closest('label') || row).click();
                    return 'checkbox';
                }
                row.click();
                return 'row';
            }
            return null;
        }""")
        if clicked:
            await human_delay(1_000, 2_000)
            logger.info("Meet-up toggled via %s", clicked)
        else:
            logger.warning("Meet-up toggle not found")
    except Exception as exc:
        logger.warning("Meet-up toggle failed: %s", exc)

    await _snap(page, "deal_meet_up_toggled")

    # Fill Meet-up location: search for MRT Surian and select first result
    try:
        location_input = page.locator(
            'input[placeholder*="Add location" i]'
        ).or_(
            page.locator('input[aria-label*="location" i]')
        ).or_(
            page.get_by_placeholder("Add location")
        )
        await location_input.first.scroll_into_view_if_needed()
        await human_delay(500, 1_000)
        await location_input.first.click(timeout=10_000)
        await human_delay(300, 600)
        from config.settings import CAROUSELL_CONFIG
        await page.keyboard.type(
            CAROUSELL_CONFIG.meetup_location_query, delay=60,
        )
        await human_delay(2_000, 3_000)

        await _snap(page, "meetup_location_searched")

        # Select the first search result
        result = page.get_by_text(
            CAROUSELL_CONFIG.meetup_location_label, exact=False,
        ).or_(
            page.locator('[class*="search"] [class*="result"]').first
        ).or_(
            page.locator('text="Search result" + div >> nth=0')
        )
        if await result.count() > 0:
            await result.first.click(timeout=5_000)
            await human_delay(1_000, 2_000)
            logger.info("Meet-up location selected: MRT Surian KG07")
        else:
            # Fallback: click first item after "Search result" text via JS
            await page.evaluate("""() => {
                const items = document.querySelectorAll('[class*="result"] p, [class*="Result"] p');
                if (items.length > 0) items[0].closest('div[class]').click();
            }""")
            await human_delay(1_000, 2_000)
            logger.info("Meet-up location selected (fallback)")
    except Exception as exc:
        logger.warning("Meet-up location failed: %s", exc)

    await _snap(page, "deal_methods_set")


async def _click_list_now(page: Page, *, submit: bool) -> None:
    """Find the 'List now' button. Click it only if submit is True."""
    await _snap(page, "before_list_button_scan")

    try:
        list_btn = page.locator(
            'button:has-text("List now")'
        ).or_(
            page.locator('a:has-text("List now")')
        ).or_(
            page.locator('button[type="submit"]')
        )

        if await list_btn.count() > 0:
            btn = list_btn.first
            await btn.scroll_into_view_if_needed()
            await human_delay(500, 1_000)

            box = await btn.bounding_box()
            text = await btn.text_content()
            logger.info(
                "List button found: text='%s', position=%s",
                text, box,
            )

            if submit:
                await btn.click(timeout=10_000)
                await human_delay(3_000, 5_000)
                logger.info("Clicked 'List now'")

                # Dismiss any post-submit informational dialogs (e.g. "Okay")
                try:
                    await page.evaluate("""() => {
                        const buttons = [...document.querySelectorAll('button')];
                        for (const b of buttons) {
                            const t = b.textContent.trim().toLowerCase();
                            if (t === 'okay' || t === 'ok' || t === 'got it') {
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    await human_delay(2_000, 3_000)
                except Exception:
                    pass
            else:
                logger.info("List button located but NOT clicked (submit=False)")
        else:
            logger.warning("List button not found on page")
    except Exception as exc:
        logger.warning("List button failed: %s", exc)

    await _snap(page, "list_button_done")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def create_product(
    page: Page,
    image_paths: list[Path],
    title: str,
    description: str,
    listing_price_cents: int,
    *,
    submit: bool = False,
) -> bool:
    """Fill the Carousell sell form.

    Walks through the form top-to-bottom, filling each field and
    capturing snapshots at every step.

    Args:
        page: Playwright page (already on /sell and logged in).
        image_paths: Absolute paths to image files (up to 10).
        title: Generated listing title.
        description: Generated listing description.
        listing_price_cents: Price in cents (MYR).
        submit: If True, click 'List now' to publish. Default False.

    Returns:
        True if form was filled successfully.
    """
    logger.info("Filling Carousell sell form: %s", title[:60])

    # Always navigate fresh to /sell to avoid stale form state
    await page.goto(SELL_URL, wait_until="domcontentloaded")
    await human_delay(2_000, 4_000)

    await _snap(page, "sell_page_loaded")

    # Step 1: Upload photos
    await _upload_photos(page, image_paths)

    # Step 2: Select category
    await _select_category(page)

    # Step 3: Set condition
    await _set_condition(page)

    # Step 4: Fill title
    await _fill_title(page, title)

    # Step 5: Fill item details (Type, Age Range)
    await _fill_item_details(page)

    # Step 6: Fill description
    await _fill_description(page, description)

    # Step 7: Set price
    await _set_price(page, listing_price_cents)

    # Step 8: Disable Buy button (confirms "Disable anyway" dialog)
    await _disable_buy_button(page)

    # Step 9: Set deal methods (AFTER disabling Buy button, which resets them)
    await _set_deal_methods(page)

    # Step 10: List now button
    await _click_list_now(page, submit=submit)

    # Final comprehensive snapshot
    await page.evaluate("window.scrollTo(0, 0)")
    await human_delay(500, 1_000)
    await _snap(
        page, "form_complete",
        title=title[:80],
        price_cents=listing_price_cents,
        image_count=len(image_paths),
    )

    logger.info("Carousell form filled -- ready for review (NOT submitted)")
    return True
