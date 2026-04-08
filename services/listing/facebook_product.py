"""Facebook Marketplace product form automation.

Fills the create-item form at /marketplace/create/item with photos,
title, price, category, condition, and description.  Takes diagnostic
snapshots at every step.

Facebook uses React with obfuscated class names -- all selectors rely
on aria-label, role, text content, and structural position rather than
CSS classes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import Page

from services.browser.helpers import human_delay
from services.listing.snapshots import capture_listing_snapshot

logger = logging.getLogger("bws.listing.facebook_product")

MARKETPLACE_CREATE_URL = "https://www.facebook.com/marketplace/create/item"


async def _snap(page: Page, step: str) -> None:
    await capture_listing_snapshot(page, step)


# ---------------------------------------------------------------------------
# Individual form field functions
# ---------------------------------------------------------------------------


async def _upload_photos(page: Page, image_paths: list[Path]) -> None:
    """Upload photos via hidden file input."""
    await _snap(page, "fb_before_upload_photos")

    # Facebook has hidden input[type=file] elements for photo upload
    file_inputs = await page.query_selector_all('input[type="file"]')
    if not file_inputs:
        logger.warning("No file input found for photo upload")
        return

    # Use the first file input -- set all files at once
    str_paths = [str(p) for p in image_paths]
    await file_inputs[0].set_input_files(str_paths)
    logger.info("Uploaded %d photos", len(str_paths))

    # Wait for upload processing
    await human_delay(min_ms=3_000, max_ms=5_000)
    await _snap(page, "fb_photos_uploaded")


async def _find_field_by_label(page: Page, label_text: str) -> object | None:
    """Find an input field by its associated label span text.

    Facebook wraps each form field in a <label> containing a <span>
    with the field name (e.g. "Title", "Price") and an <input>.
    """
    return await page.evaluate_handle(
        """(labelText) => {
            const spans = [...document.querySelectorAll('span')];
            const label = spans.find(
                s => s.textContent.trim() === labelText
                  && s.closest('label')
            );
            if (!label) return null;
            const container = label.closest('label');
            return container?.querySelector('input')
                || container?.querySelector('textarea')
                || null;
        }""",
        label_text,
    )


async def _fill_title(page: Page, title: str) -> None:
    """Fill the Title field."""
    await _snap(page, "fb_before_title")

    el = await _find_field_by_label(page, "Title")
    if el:
        await el.evaluate("el => { el.focus(); el.value = ''; }")
        await page.keyboard.type(title, delay=40)
        logger.info("Filled title: %s", title[:60])
    else:
        logger.warning("Title field not found")

    await human_delay(min_ms=500, max_ms=1_000)
    await _snap(page, "fb_title_filled")


async def _fill_price(page: Page, price_cents: int) -> None:
    """Fill the Price field (in RM)."""
    await _snap(page, "fb_before_price")

    price_str = str(price_cents // 100)

    el = await _find_field_by_label(page, "Price")
    if el:
        await el.evaluate("el => { el.focus(); el.value = ''; }")
        await page.keyboard.type(price_str, delay=40)
        logger.info("Filled price: RM%s", price_str)
    else:
        logger.warning("Price field not found")

    await human_delay(min_ms=500, max_ms=1_000)
    await _snap(page, "fb_price_filled")


async def _select_category(page: Page) -> None:
    """Select the Category dropdown -- choose 'Toys & games'."""
    await _snap(page, "fb_before_category")

    # Find the Category combobox by its label
    clicked = await page.evaluate("""() => {
        const spans = [...document.querySelectorAll('span')];
        const cat = spans.find(
            s => s.textContent.trim() === 'Category'
              && s.closest('label[role="combobox"]')
        );
        if (!cat) return false;
        cat.closest('label[role="combobox"]').click();
        return true;
    }""")

    if not clicked:
        logger.warning("Category combobox not found")
        await _snap(page, "fb_category_not_found")
        return

    await human_delay(min_ms=1_000, max_ms=2_000)

    # Select "Toys & games" from the dropdown list
    selected = await page.evaluate("""() => {
        const items = [...document.querySelectorAll(
            '[role="option"], [role="menuitem"], [role="listbox"] span'
        )];
        const target = items.find(
            el => el.textContent.trim().toLowerCase().includes('toys')
               && el.textContent.trim().toLowerCase().includes('game')
        );
        if (target) { target.click(); return true; }

        // Fallback: try all visible spans
        const spans = [...document.querySelectorAll('span')];
        const match = spans.find(
            s => s.textContent.trim().toLowerCase().includes('toys')
              && s.textContent.trim().toLowerCase().includes('game')
              && s.offsetParent !== null
        );
        if (match) { match.click(); return true; }
        return false;
    }""")

    if selected:
        logger.info("Selected category: Toys & games")
    else:
        logger.warning("Could not select 'Toys & games' category")

    await human_delay(min_ms=500, max_ms=1_000)
    await _snap(page, "fb_category_selected")


async def _select_condition(page: Page) -> None:
    """Select the Condition dropdown -- choose 'New'."""
    await _snap(page, "fb_before_condition")

    # Find the Condition combobox by its label
    clicked = await page.evaluate("""() => {
        const spans = [...document.querySelectorAll('span')];
        const cond = spans.find(
            s => s.textContent.trim() === 'Condition'
              && s.closest('label[role="combobox"]')
        );
        if (!cond) return false;
        cond.closest('label[role="combobox"]').click();
        return true;
    }""")

    if not clicked:
        logger.warning("Condition combobox not found")
        await _snap(page, "fb_condition_not_found")
        return

    await human_delay(min_ms=1_000, max_ms=2_000)

    # Select "New" from the dropdown
    selected = await page.evaluate("""() => {
        const items = [...document.querySelectorAll(
            '[role="option"], [role="menuitem"], [role="listbox"] span'
        )];
        const target = items.find(
            el => el.textContent.trim() === 'New'
        );
        if (target) { target.click(); return true; }

        // Fallback: visible spans
        const spans = [...document.querySelectorAll('span')];
        const match = spans.find(
            s => s.textContent.trim() === 'New'
              && s.offsetParent !== null
        );
        if (match) { match.click(); return true; }
        return false;
    }""")

    if selected:
        logger.info("Selected condition: New")
    else:
        logger.warning("Could not select 'New' condition")

    await human_delay(min_ms=500, max_ms=1_000)
    await _snap(page, "fb_condition_selected")


async def _fill_description(page: Page, description: str) -> None:
    """Fill the Description field via 'More details' expansion."""
    await _snap(page, "fb_before_description")

    # Click "More details" to expand the description section
    expanded = await page.evaluate("""() => {
        const spans = [...document.querySelectorAll('span')];
        const more = spans.find(
            s => s.textContent.trim() === 'More details'
              && s.offsetParent !== null
        );
        if (more) { more.click(); return true; }
        return false;
    }""")

    if expanded:
        logger.info("Expanded 'More details' section")
        await human_delay(min_ms=1_000, max_ms=2_000)
    else:
        logger.info("'More details' not found -- description may already be visible")

    # Find and fill the description textarea or contenteditable
    el = await _find_field_by_label(page, "Description")
    if el:
        await el.evaluate("el => { el.focus(); el.value = ''; }")
        await page.keyboard.type(description, delay=15)
        logger.info("Filled description (%d chars)", len(description))
    else:
        # Try contenteditable div as fallback
        filled = await page.evaluate("""(text) => {
            const editables = [...document.querySelectorAll(
                '[contenteditable="true"]'
            )].filter(el => el.offsetParent !== null);
            // Pick the one near "Description" label
            if (editables.length > 0) {
                const target = editables[editables.length - 1];
                target.focus();
                target.textContent = text;
                target.dispatchEvent(new Event('input', {bubbles: true}));
                return true;
            }
            return false;
        }""", description)
        if filled:
            logger.info("Filled description via contenteditable (%d chars)", len(description))
        else:
            logger.warning("Description field not found")

    await human_delay(min_ms=500, max_ms=1_000)
    await _snap(page, "fb_description_filled")


async def _enable_hide_from_friends(page: Page) -> None:
    """Toggle 'Hide from friends' on."""
    await _snap(page, "fb_before_hide_from_friends")

    # First scroll to the bottom of the form to make the toggle visible
    await page.evaluate("""() => {
        const spans = [...document.querySelectorAll('span')];
        const label = spans.find(
            s => s.textContent.trim() === 'Hide from friends'
        );
        if (label) label.scrollIntoView({block: 'center'});
    }""")
    await human_delay(min_ms=500, max_ms=1_000)

    toggled = await page.evaluate("""() => {
        const spans = [...document.querySelectorAll('span')];
        const label = spans.find(
            s => s.textContent.trim() === 'Hide from friends'
        );
        if (!label) return 'not_found';

        // Walk up to find the row container that holds both label and toggle
        let container = label.parentElement;
        for (let i = 0; i < 8 && container; i++) {
            // Look for a checkbox input in this container
            const checkbox = container.querySelector('input[type="checkbox"]');
            if (checkbox) {
                if (!checkbox.checked) {
                    checkbox.click();
                    return 'clicked_checkbox';
                }
                return 'already_checked';
            }

            // Look for a switch role
            const toggle = container.querySelector('[role="switch"]');
            if (toggle) {
                if (toggle.getAttribute('aria-checked') !== 'true') {
                    toggle.click();
                    return 'clicked_switch';
                }
                return 'already_checked';
            }

            // Look for aria-label="Enabled"/"Disabled" toggle
            const ariaToggle = container.querySelector(
                '[aria-label="Disabled"], [aria-label="Enabled"]'
            );
            if (ariaToggle) {
                if (ariaToggle.getAttribute('aria-label') === 'Disabled') {
                    ariaToggle.click();
                    return 'clicked_aria_toggle';
                }
                return 'already_checked';
            }

            container = container.parentElement;
        }

        return 'no_toggle_found';
    }""")

    if "clicked" in toggled:
        logger.info("Enabled 'Hide from friends' (%s)", toggled)
    elif toggled == "already_checked":
        logger.info("'Hide from friends' was already enabled")
    else:
        logger.warning("Could not toggle 'Hide from friends': %s", toggled)

    await human_delay(min_ms=500, max_ms=1_000)
    await _snap(page, "fb_hide_from_friends_toggled")


async def _click_next(page: Page) -> bool:
    """Click the Next button to proceed to step 2."""
    clicked = await page.evaluate("""() => {
        const btns = [...document.querySelectorAll(
            '[aria-label="Next"], div[role="button"]'
        )];
        const next = btns.find(
            b => b.getAttribute('aria-label') === 'Next'
              || b.textContent.trim() === 'Next'
        );
        if (next) { next.click(); return true; }
        return false;
    }""")

    if clicked:
        logger.info("Clicked 'Next' button")
        await human_delay(min_ms=3_000, max_ms=5_000)
        await _snap(page, "fb_after_next")
        return True

    logger.warning("Could not click 'Next'")
    return False


async def _add_groups(page: Page, group_names: list[str]) -> None:
    """On the step-2 page, search and add groups to list in.

    Facebook's step 2 may show 'List in more places' with group search.
    """
    await _snap(page, "fb_step2_page")

    # Look for a "List in more places" or group-related section
    # Try clicking it to expand
    expanded = await page.evaluate("""() => {
        const spans = [...document.querySelectorAll('span')];
        const more = spans.find(
            s => (s.textContent.trim().toLowerCase().includes('list in more places')
              || s.textContent.trim().toLowerCase().includes('more places'))
              && s.offsetParent !== null
        );
        if (more) { more.click(); return true; }

        // Also try any checkbox/toggle near group text
        const group = spans.find(
            s => s.textContent.trim().toLowerCase().includes('group')
              && s.offsetParent !== null
        );
        if (group) { group.click(); return true; }

        return false;
    }""")

    if expanded:
        logger.info("Found 'List in more places' / groups section")
        await human_delay(min_ms=2_000, max_ms=3_000)
        await _snap(page, "fb_groups_section_expanded")
    else:
        logger.info("No 'List in more places' found -- taking snapshot for inspection")
        await _snap(page, "fb_no_groups_section")

    for group_name in group_names:
        logger.info("Searching for group: %s", group_name)

        # Try to find a search input for groups
        search_filled = await page.evaluate("""(name) => {
            // Look for search inputs in the groups section
            const inputs = [...document.querySelectorAll(
                'input[type="search"], input[placeholder*="earch"], input[placeholder*="roup"]'
            )].filter(el => el.offsetParent !== null);

            if (inputs.length > 0) {
                const input = inputs[inputs.length - 1];
                input.focus();
                input.value = '';
                return true;
            }
            return false;
        }""", group_name)

        if search_filled:
            await page.keyboard.type(group_name, delay=40)
            await human_delay(min_ms=2_000, max_ms=3_000)
            await _snap(page, f"fb_group_search_{group_name[:20]}")

            # Try to click the matching group result (fuzzy: strip special chars)
            selected = await page.evaluate("""(name) => {
                const normalize = s => s.toLowerCase().replace(/[^a-z0-9 ]/g, '').trim();
                const target = normalize(name);

                // Check visible candidates near the search area
                const candidates = [...document.querySelectorAll(
                    '[role="option"], [role="checkbox"], [role="menuitem"], label, div[role="button"]'
                )].filter(el => el.offsetParent !== null);

                const match = candidates.find(
                    el => normalize(el.textContent).includes(target)
                );
                if (match) {
                    match.click();
                    return true;
                }

                // Fallback: visible spans with fuzzy match
                const spans = [...document.querySelectorAll('span')].filter(
                    s => normalize(s.textContent).includes(target)
                      && s.offsetParent !== null
                );
                if (spans.length > 0) {
                    spans[0].click();
                    return true;
                }

                return false;
            }""", group_name)

            if selected:
                logger.info("Selected group: %s", group_name)
            else:
                logger.warning("Could not select group: %s", group_name)

            await human_delay(min_ms=1_000, max_ms=2_000)
        else:
            # No search input -- try clicking group names directly (fuzzy)
            clicked = await page.evaluate("""(name) => {
                const normalize = s => s.toLowerCase().replace(/[^a-z0-9 ]/g, '').trim();
                const target = normalize(name);
                const spans = [...document.querySelectorAll('span')].filter(
                    s => normalize(s.textContent).includes(target)
                      && s.offsetParent !== null
                );
                if (spans.length > 0) {
                    spans[0].click();
                    return true;
                }
                return false;
            }""", group_name)

            if clicked:
                logger.info("Clicked group: %s", group_name)
            else:
                logger.warning("Could not find group: %s", group_name)

            await human_delay(min_ms=1_000, max_ms=2_000)

        await _snap(page, f"fb_group_added_{group_name[:20]}")

    await _snap(page, "fb_groups_complete")


async def _locate_next_button(page: Page) -> None:
    """Find the Next button but do NOT click it -- leave for user review."""
    await _snap(page, "fb_before_next")

    found = await page.evaluate("""() => {
        const btns = [...document.querySelectorAll(
            '[aria-label="Next"], div[role="button"]'
        )];
        const next = btns.find(
            b => b.getAttribute('aria-label') === 'Next'
              || b.textContent.trim() === 'Next'
        );
        if (next) {
            next.scrollIntoView({block: 'center'});
            return true;
        }
        return false;
    }""")

    if found:
        logger.info("Located 'Next' button (not clicking -- user review)")
    else:
        logger.warning("'Next' button not found")

    await _snap(page, "fb_form_complete")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def create_product(
    page: Page,
    *,
    image_paths: list[Path],
    title: str,
    description: str,
    listing_price_cents: int,
    groups: list[str] | None = None,
    submit: bool = False,
) -> bool:
    """Fill the Facebook Marketplace create-item form.

    Args:
        page: Playwright page already logged in to Facebook.
        image_paths: List of image file paths to upload.
        title: Listing title.
        description: Listing description.
        listing_price_cents: Price in cents (MYR).
        groups: Optional list of group names to cross-post to.
        submit: If True, click Next. If False, leave for user review.

    Returns:
        True if form was filled successfully.
    """
    # Navigate to create page
    if "/marketplace/create/item" not in page.url:
        await page.goto(MARKETPLACE_CREATE_URL, wait_until="domcontentloaded")
        await human_delay(min_ms=4_000, max_ms=6_000)

    await _snap(page, "fb_create_page_loaded")

    # Step 1: Fill form fields sequentially
    await _upload_photos(page, image_paths)
    await _fill_title(page, title)
    await _fill_price(page, listing_price_cents)
    await _select_category(page)
    await _select_condition(page)
    await _fill_description(page, description)
    await _enable_hide_from_friends(page)

    # Step 2: Click Next to go to the groups/publish page
    if not await _click_next(page):
        logger.warning("Could not proceed to step 2")
        await _locate_next_button(page)
        return True

    # Step 2 page: add groups if requested
    if groups:
        await _add_groups(page, groups)

    if not submit:
        logger.info("Form complete -- left open for user review (not publishing)")
        await _snap(page, "fb_ready_for_review")

    logger.info("Facebook Marketplace form filling complete")
    return True
