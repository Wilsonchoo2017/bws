"""Shopee Seller Center -- automated product creation.

Fills the "Add a New Product" form: images, title, category,
description, brand, price, stock, shipping, and delivery options.
Captures DOM snapshots at every step for R&D.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from services.listing.snapshots import capture_listing_snapshot
from services.shopee.browser import human_delay
from services.shopee.humanize import random_click, random_type
from services.shopee.popups import dismiss_popups

logger = logging.getLogger("bws.listing.shopee_product")

SELLER_BASE = "https://seller.shopee.com.my"

# ---------------------------------------------------------------------------
# Tab navigation helpers
# ---------------------------------------------------------------------------


async def _click_tab(page: Page, tab_name: str) -> None:
    """Click a tab on the Add Product page by its visible text."""
    # Scope to the tab bar area (eds-tabs) to avoid matching text elsewhere
    try:
        tab_bar = page.locator('[class*="eds-tabs__nav"], [class*="tab-bar"], [role="tablist"]').first
        tab = tab_bar.get_by_text(tab_name, exact=True)
        await tab.first.click(timeout=10_000)
    except Exception:
        # Fallback: try direct role-based click
        try:
            await page.get_by_role("tab", name=tab_name).first.click(timeout=10_000)
        except Exception as exc:
            logger.warning("Tab click failed for '%s': %s", tab_name, exc)
            await capture_listing_snapshot(page, f"tab_click_failed_{tab_name}")
    await human_delay(1_000, 2_000)


async def _clear_and_type(
    page: Page, selector: str, value: str,
) -> None:
    """Click an input, clear via JS native setter (React-safe), then type."""
    el = await page.wait_for_selector(selector, timeout=10_000)
    if el:
        await el.click()
        await human_delay(200, 400)
        await _clear_focused_and_type(page, value, delay=60)


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------


async def _navigate_to_add_product(page: Page) -> bool:
    """Navigate directly to the 'Add a New Product' page."""
    try:
        await page.goto(
            f"{SELLER_BASE}/portal/product/new",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        await human_delay(2_000, 4_000)
        await dismiss_popups(page)
        await capture_listing_snapshot(page, "add_product_page")
        return True
    except Exception as exc:
        logger.error("Failed to navigate to Add Product: %s", exc)
        await capture_listing_snapshot(page, "add_product_failed")
        return False


async def _upload_images(page: Page, image_paths: list[Path]) -> None:
    """Upload product images via the file input."""
    if not image_paths:
        logger.warning("No images to upload")
        return

    # Find the file input (hidden, used by the upload button)
    file_input = page.locator('input[type="file"]').first
    str_paths = [str(p) for p in image_paths]
    await file_input.set_input_files(str_paths)

    # Wait for thumbnails to appear (upload processing)
    await human_delay(3_000, 6_000)
    await capture_listing_snapshot(
        page, "images_uploaded",
        extra={"image_count": len(image_paths), "paths": str_paths},
    )


async def _clear_focused_and_type(
    page: Page, text: str, *, delay: int = 40,
) -> None:
    """Clear the currently focused field via JS native setter, then type."""
    await page.evaluate("""() => {
        const el = document.activeElement;
        if (el && ('value' in el)) {
            const desc = Object.getOwnPropertyDescriptor(
                el.tagName === 'TEXTAREA'
                    ? HTMLTextAreaElement.prototype
                    : HTMLInputElement.prototype,
                'value'
            );
            if (desc && desc.set) {
                desc.set.call(el, '');
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    }""")
    await human_delay(300, 500)
    await page.keyboard.type(text, delay=delay)


async def _fill_product_name(page: Page, title: str) -> None:
    """Fill the Product Name field on Basic Information tab."""
    try:
        name_input = page.locator(
            '[data-product-edit-field-unique-id="name"] input'
        ).or_(
            page.locator('input[placeholder*="Brand Name"]')
        ).or_(
            page.locator('input[placeholder*="name" i]')
        ).first

        await name_input.click(timeout=10_000)
        await human_delay(200, 400)
        await _clear_focused_and_type(page, title, delay=40)
        await human_delay(500, 1_000)
        await capture_listing_snapshot(page, "title_filled")
    except Exception as exc:
        logger.warning("Product name input failed: %s", exc)
        await capture_listing_snapshot(page, "title_input_not_found")


async def _set_category(page: Page) -> None:
    """Set category: Hobbies & Collections > Toys & Games > Others.

    Uses the search bar in the category modal to find the right path,
    then clicks through the filtered results.
    """
    # Scroll back to top for category
    await page.evaluate("window.scrollTo(0, 0)")
    await human_delay(500, 1_000)

    # Check if category is already set (shows path like "Hobbies...> Toys & Games")
    already_set = await page.evaluate("""() => {
        const el = document.querySelector(
            '[data-product-edit-field-unique-id="category"]'
        );
        if (!el) return false;
        const text = el.textContent || '';
        return text.includes('Toys & Games') || text.includes('Toys &amp; Games');
    }""")
    if already_set:
        logger.info("Category already set to Toys & Games, skipping")
        await capture_listing_snapshot(page, "category_already_set")
        return

    # Click the category edit/select button
    try:
        cat_btn = page.locator(
            '[data-product-edit-field-unique-id="category"]'
        ).or_(
            page.locator('text="Edit Category"')
        ).or_(
            page.locator('text="Please set category"')
        )
        await cat_btn.first.click(timeout=10_000)
        await human_delay(1_000, 2_000)
    except Exception:
        logger.warning("Could not find category button")
        await capture_listing_snapshot(page, "category_button_not_found")
        return

    # Type "toys" in the search bar inside the modal
    try:
        search = page.locator('.eds-modal input[type="text"]').or_(
            page.locator('.eds-modal input[placeholder*="search" i]')
        ).or_(
            page.locator('.eds-modal input').first
        )
        await search.first.click(timeout=5_000)
        await human_delay(300, 600)
        await page.keyboard.type("toys", delay=80)
        await human_delay(1_000, 2_000)
    except Exception as exc:
        logger.warning("Category search input not found: %s", exc)
        await capture_listing_snapshot(page, "category_search_not_found")
        return

    # Now click through the filtered tree:
    # Column 1: Hobbies & Collections
    # Column 2: Toys & Games
    # Column 3: Others
    levels = [
        "Hobbies & Collections",
        "Toys & Games",
        "Others",
    ]

    for level_text in levels:
        try:
            await human_delay(500, 1_000)
            option = page.locator(f'.eds-modal li:has-text("{level_text}")').or_(
                page.locator(f'.eds-modal :text-is("{level_text}")')
            )
            await option.last.click(force=True, timeout=10_000)
            await human_delay(800, 1_500)
            logger.info("Category '%s' selected", level_text)
        except Exception as exc:
            logger.warning("Category '%s' not found: %s", level_text, exc)
            await capture_listing_snapshot(
                page, "category_level_not_found",
                extra={"level": level_text},
            )
            return

    # Click Confirm
    try:
        confirm = page.locator(
            '.eds-modal__footer button:has-text("Confirm")'
        ).or_(
            page.locator('button:has-text("Confirm")')
        )
        await confirm.first.click(timeout=10_000)
        await human_delay(1_000, 2_000)
    except Exception as exc:
        logger.warning("Category Confirm button not found: %s", exc)

    await capture_listing_snapshot(page, "category_set")


async def _set_brand(page: Page) -> None:
    """Set Brand to LEGO on the Specification tab."""
    await _click_tab(page, "Specification")
    await human_delay(500, 1_000)

    # Check if brand is already set to LEGO
    brand_text = await page.evaluate("""() => {
        const el = document.querySelector('.product-brand-item .eds-selector');
        return el ? el.textContent.trim() : '';
    }""")
    if "LEGO" in brand_text:
        logger.info("Brand already set to LEGO, skipping")
        await capture_listing_snapshot(page, "brand_already_set")
        return

    # Step 1: Click the Brand dropdown trigger to open it
    try:
        brand_trigger = page.locator('.product-brand-item .eds-selector').first
        await brand_trigger.click(timeout=10_000)
        await human_delay(800, 1_500)
        await capture_listing_snapshot(page, "brand_dropdown_opened")
    except Exception as exc:
        logger.warning("Brand dropdown click failed: %s", exc)
        await capture_listing_snapshot(page, "brand_dropdown_failed")
        return

    # Step 2: Find the search input inside the opened popover and type "LEGO"
    # The popover renders as an eds-popper element at the end of the body
    try:
        # The popover search input could be in various containers
        search = page.locator(
            '.eds-popper input[type="text"], '
            '.eds-popper input[placeholder], '
            '.eds-dropdown__popover input, '
            '[class*="select-popover"] input'
        )
        count = await search.count()
        if count > 0:
            await search.first.click(timeout=5_000)
            await human_delay(300, 600)
            await page.keyboard.type("LEGO", delay=80)
            await human_delay(1_500, 2_500)
        else:
            # No search input -- try typing directly (dropdown may filter on keypress)
            await page.keyboard.type("LEGO", delay=80)
            await human_delay(1_500, 2_500)
    except Exception as exc:
        logger.warning("Brand search input failed: %s", exc)

    # Step 3: Click the exact "LEGO" option (not "LEGO Batman" etc.)
    try:
        # Use exact text match to avoid clicking sub-brands like "LEGO Batman"
        lego_option = page.locator(
            '.eds-popper [class*="option"] :text-is("LEGO"), '
            '[class*="select-popover"] [class*="option"] :text-is("LEGO")'
        ).or_(
            page.get_by_text("LEGO", exact=True)
        )
        count = await lego_option.count()
        if count > 0:
            # Click the first exact "LEGO" match
            await lego_option.first.click(timeout=10_000)
            await human_delay(500, 1_000)
            logger.info("Brand LEGO selected")
        else:
            logger.warning("LEGO option not found in brand dropdown")
    except Exception as exc:
        logger.warning("Brand option click failed: %s", exc)

    await capture_listing_snapshot(page, "brand_set")


async def _fill_description(page: Page, description: str) -> None:
    """Fill the Description field."""
    await _click_tab(page, "Description")
    await human_delay(500, 1_000)

    # Shopee's description editor could be a textarea, contenteditable div,
    # or a rich text editor. Try multiple approaches.
    try:
        # Try textarea first
        textarea = page.locator('textarea[placeholder*="description" i]').or_(
            page.locator('textarea')
        ).or_(
            page.locator('[contenteditable="true"]')
        )

        if await textarea.count() > 0:
            await textarea.first.click()
            await human_delay(200, 500)
            await _clear_focused_and_type(page, description, delay=15)
            await human_delay(500, 1_000)
    except Exception as exc:
        logger.warning("Description fill failed: %s", exc)

    await capture_listing_snapshot(page, "description_filled")


async def _set_price_and_stock(
    page: Page, price_cents: int,
) -> None:
    """Fill Price and Stock on the Sales Information tab."""
    await _click_tab(page, "Sales Information")
    await human_delay(500, 1_000)

    price_str = f"{price_cents / 100:.2f}"

    # Price input -- use Shopee's unique field ID
    try:
        price_input = page.locator(
            '[data-product-edit-field-unique-id="price"] input'
        ).first
        await price_input.click(timeout=10_000)
        await human_delay(200, 400)
        await _clear_focused_and_type(page, price_str, delay=60)
        await human_delay(300, 600)
    except Exception as exc:
        logger.warning("Price input failed: %s", exc)

    # Stock input
    try:
        stock_input = page.locator(
            '[data-product-edit-field-unique-id="stock"] input'
        ).or_(
            page.locator('[data-auto-correct-key="stock"] input')
        ).first
        await stock_input.click(timeout=10_000)
        await human_delay(200, 400)
        await _clear_focused_and_type(page, "1", delay=60)
        await human_delay(300, 600)
    except Exception as exc:
        logger.warning("Stock input failed: %s", exc)

    await capture_listing_snapshot(page, "price_set", extra={"price": price_str})


async def _set_shipping(
    page: Page,
    weight_kg: float,
    dims: tuple[int, int, int],
) -> None:
    """Fill Weight and Parcel Size, enable delivery options on Shipping tab."""
    await _click_tab(page, "Shipping")
    await human_delay(500, 1_000)

    w, l, h = dims

    # Weight input -- use Shopee's unique field ID
    try:
        weight_input = page.locator(
            '[data-product-edit-field-unique-id="weight"] input'
        ).or_(
            page.locator('[data-auto-correct-key="weight"] input')
        ).first
        await weight_input.click(timeout=10_000)
        await human_delay(200, 400)
        await _clear_focused_and_type(page, str(weight_kg), delay=60)
        await human_delay(500, 1_000)
    except Exception as exc:
        logger.warning("Weight input failed: %s", exc)

    # Parcel Size: W x L x H (three separate inputs)
    try:
        dim_inputs = page.locator(
            'input[placeholder*="Integer" i], input[placeholder="W (Integer)"]'
        )
        count = await dim_inputs.count()
        if count >= 3:
            for i, val in enumerate([w, l, h]):
                await dim_inputs.nth(i).click()
                await human_delay(200, 400)
                await _clear_focused_and_type(page, str(val), delay=60)
                await human_delay(200, 400)
        else:
            # Fallback: find by placeholder patterns
            for placeholder, val in [("W", w), ("L", l), ("H", h)]:
                inp = page.locator(f'input[placeholder*="{placeholder}"]').first
                await inp.click(timeout=5_000)
                await human_delay(200, 400)
                await _clear_focused_and_type(page, str(val), delay=60)
                await human_delay(200, 400)
    except Exception as exc:
        logger.warning("Parcel size input failed: %s", exc)

    # Wait for Shopee to process weight and enable delivery toggles
    await human_delay(1_000, 2_000)

    # Scroll down to reveal Dangerous Goods and delivery toggles
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await human_delay(1_000, 2_000)

    # Dangerous Goods -- select "No" radio button (skip if already selected)
    try:
        dg_already_no = await page.evaluate("""() => {
            const spans = [...document.querySelectorAll('span, label')];
            const dg = spans.find(s => s.textContent.trim() === 'Dangerous Goods');
            if (!dg) return false;
            const section = dg.closest('div[class]');
            if (!section) return false;
            const radios = section.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                const label = r.closest('label');
                if (label && label.textContent.trim() === 'No' && r.checked) return true;
            }
            return false;
        }""")
        if dg_already_no:
            logger.info("Dangerous Goods already set to No, skipping")
            return

        # The radio is inside a section with "Dangerous Goods" text
        dg_section = page.locator('div:has(> :text("Dangerous Goods"))').or_(
            page.locator('[class*="dangerous"]')
        )
        no_label = dg_section.locator('label:has-text("No"), span:text-is("No")').first

        if await no_label.count() > 0:
            await no_label.click(force=True)
            await human_delay(500, 1_000)
            logger.info("Dangerous Goods set to No")
        else:
            # Fallback: find any "No" radio on the page in the shipping context
            radios = page.locator('input[type="radio"]')
            count = await radios.count()
            for idx in range(count):
                radio = radios.nth(idx)
                parent_text = await radio.evaluate("el => el.closest('label')?.textContent || ''")
                if parent_text.strip() == "No":
                    await radio.check(force=True)
                    await human_delay(500, 1_000)
                    logger.info("Dangerous Goods set to No (fallback)")
                    break
    except Exception as exc:
        logger.warning("Dangerous Goods radio failed: %s", exc)

    await capture_listing_snapshot(
        page, "shipping_filled",
        extra={"weight_kg": weight_kg, "dims_wlh": [w, l, h]},
    )


async def _toggle_delivery(
    page: Page, label: str, *, enable: bool,
) -> None:
    """Enable or disable a single delivery toggle by section label."""
    try:
        section = page.locator(f'div:has(> div:has-text("{label}"))').or_(
            page.locator(f'div:has(> :text("{label}"))')
        )
        toggle = section.locator('.eds-switch').first

        if await toggle.count() == 0:
            logger.warning("%s toggle not found", label)
            return

        cls = await toggle.get_attribute("class") or ""

        if "disabled" in cls:
            logger.info("%s toggle is disabled", label)
            return

        is_on = "eds-switch--open" in cls

        if enable and is_on:
            logger.info("%s already enabled, skipping", label)
        elif not enable and not is_on:
            logger.info("%s already disabled, skipping", label)
        else:
            await toggle.click(force=True)
            await human_delay(800, 1_500)
            action = "Enabled" if enable else "Disabled"
            logger.info("%s %s", action, label)
    except Exception as exc:
        logger.warning("Failed to toggle %s: %s", label, exc)


async def _enable_delivery_options(page: Page) -> None:
    """Enable Doorstep Delivery and Self Collection, disable Bulky."""
    # Scroll to bottom to reveal all delivery options
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await human_delay(1_000, 1_500)

    await _toggle_delivery(page, "Doorstep Delivery", enable=True)
    await _toggle_delivery(page, "Self Collection Point", enable=True)
    await _toggle_delivery(page, "Bulky Delivery", enable=False)

    await capture_listing_snapshot(page, "delivery_enabled")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def _validate_form(page: Page) -> list[str]:
    """Validate required fields before save. Returns list of failed field IDs.

    Field IDs: "title", "price", "stock", "category", "weight".
    Empty list means all checks passed.
    """
    errors: list[str] = []

    # 1. Title
    try:
        title_val = await page.locator(
            '[data-product-edit-field-unique-id="name"] input'
        ).first.input_value()
        if not title_val.strip():
            errors.append("title")
    except Exception:
        errors.append("title")

    # 2. Category (should not show "Please set category")
    try:
        no_cat = await page.evaluate("""() => {
            const el = document.querySelector(
                '[data-product-edit-field-unique-id="category"]'
            );
            if (!el) return true;
            const text = el.textContent || '';
            return text.includes('Please set category') || text.includes('Edit Category');
        }""")
        if no_cat:
            errors.append("category")
    except Exception:
        errors.append("category")

    # 3. Price
    try:
        await _click_tab(page, "Sales Information")
        await human_delay(500, 1_000)
        price_val = await page.locator(
            '[data-product-edit-field-unique-id="price"] input'
        ).first.input_value()
        if not price_val.strip():
            errors.append("price")
    except Exception:
        errors.append("price")

    # 4. Stock
    try:
        stock_val = await page.locator(
            '[data-product-edit-field-unique-id="stock"] input'
        ).or_(
            page.locator('[data-auto-correct-key="stock"] input')
        ).first.input_value()
        if not stock_val.strip() or stock_val.strip() == "0":
            errors.append("stock")
    except Exception:
        errors.append("stock")

    # 5. Weight
    try:
        await _click_tab(page, "Shipping")
        await human_delay(500, 1_000)
        weight_val = await page.locator(
            '[data-product-edit-field-unique-id="weight"] input'
        ).or_(
            page.locator('[data-auto-correct-key="weight"] input')
        ).first.input_value()
        if not weight_val.strip():
            errors.append("weight")
    except Exception:
        errors.append("weight")

    return errors


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def create_product(
    page: Page,
    item: dict[str, Any],
    minifigures: list[dict[str, Any]],
    image_paths: list[Path],
    title: str,
    description: str,
    listing_price_cents: int,
    weight_kg: float,
    dims: tuple[int, int, int],
) -> bool:
    """Fill the Shopee 'Add a New Product' form.

    Navigates through all tabs and fills fields. Does NOT click
    'Save and Publish' -- leaves the form ready for user review.

    Args:
        page: Playwright page (already logged in to Seller Center).
        item: Item dict from get_item_detail().
        minifigures: List of minifig dicts.
        image_paths: Absolute paths to image files.
        title: Generated listing title.
        description: Generated listing description.
        listing_price_cents: Price in cents (MYR).
        weight_kg: Shipping weight in kg (already +20%).
        dims: Shipping dimensions (W, L, H) in cm integers (already +5cm).

    Returns:
        True if form was filled successfully.
    """
    set_number = item["set_number"]
    logger.info("Creating Shopee listing for %s", set_number)

    # Step 1: Navigate to Add New Product
    if not await _navigate_to_add_product(page):
        return False
    await dismiss_popups(page)

    # Wait for the page to fully render
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    await human_delay(1_000, 2_000)

    # Step 2: Upload images
    await _upload_images(page, image_paths)

    # Step 3: Fill product name
    await _fill_product_name(page, title)

    # Step 4: Set category
    await _set_category(page)

    # Step 5: Set brand (Specification tab)
    await _set_brand(page)

    # Step 6: Fill description
    await _fill_description(page, description)

    # Step 7: Set price and stock
    await _set_price_and_stock(page, listing_price_cents)

    # Step 8: Set shipping weight and dimensions
    await _set_shipping(page, weight_kg, dims)

    # Step 9: Enable delivery options
    await _enable_delivery_options(page)

    # Step 10: Validate form before save
    validation_errors = await _validate_form(page)
    if validation_errors:
        for field in validation_errors:
            logger.warning("Validation failed: %s -- retrying", field)
        await capture_listing_snapshot(
            page, "validation_failed_retry",
            extra={"errors": validation_errors},
        )

        # Retry each failed field (dedupe price/stock since they share a step)
        retried: set[str] = set()
        for field in validation_errors:
            if field in retried:
                continue
            if field == "title":
                await _click_tab(page, "Basic Information")
                await human_delay(500, 1_000)
                await _fill_product_name(page, title)
            elif field == "category":
                await _click_tab(page, "Basic Information")
                await human_delay(500, 1_000)
                await _set_category(page)
            elif field in ("price", "stock"):
                await _set_price_and_stock(page, listing_price_cents)
                retried.add("price")
                retried.add("stock")
            elif field == "weight":
                await _set_shipping(page, weight_kg, dims)
            retried.add(field)

        # Re-validate
        validation_errors = await _validate_form(page)
        if validation_errors:
            for field in validation_errors:
                logger.error("Validation still failed after retry: %s", field)
            await capture_listing_snapshot(
                page, "validation_failed_final",
                extra={"errors": validation_errors},
            )
            logger.error(
                "Form validation failed with %d error(s) after retry -- aborting",
                len(validation_errors),
            )
            return False

        logger.info("Validation passed after retry")

    # Step 11: Click "Save and Delist"
    try:
        # Dismiss any leftover modals first
        await page.keyboard.press("Escape")
        await human_delay(500, 1_000)

        save_btn = page.locator('button:has-text("Save and Delist")').first
        await save_btn.scroll_into_view_if_needed()
        await human_delay(500, 1_000)
        await save_btn.click(force=True, timeout=10_000)
        await human_delay(1_500, 2_500)

        # Shopee shows a confirmation dialog titled "Save and Delist ?"
        # with two buttons: "Optimize Now" and "Save and Delist"
        # Scope to the specific modal containing this title
        await human_delay(1_000, 1_500)
        delist_modal = page.locator(
            '.eds-modal:has(.eds-modal__header:has-text("Save and Delist"))'
        )
        dialog_btn = delist_modal.locator(
            'button.eds-button--primary'
        )
        await dialog_btn.first.click(force=True, timeout=10_000)
        await human_delay(3_000, 5_000)
        logger.info("Confirmed Save and Delist for %s", set_number)
    except Exception as exc:
        logger.warning("Save and Delist failed: %s", exc)

    await capture_listing_snapshot(
        page, "after_save",
        extra={
            "set_number": set_number,
            "title": title,
            "price_cents": listing_price_cents,
            "weight_kg": weight_kg,
            "dims": list(dims),
            "image_count": len(image_paths),
        },
    )

    logger.info("Shopee listing saved (delisted) for %s", set_number)
    return True
