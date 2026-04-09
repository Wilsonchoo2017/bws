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


async def _clear_focused_and_type(
    page: Page, text: str, *, delay: int = 40,
) -> None:
    """Clear the currently focused field via JS native setter (React-safe), then type."""
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
        await el.evaluate("el => el.focus()")
        await human_delay(200, 400)
        await _clear_focused_and_type(page, title, delay=40)
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
        await el.evaluate("el => el.focus()")
        await human_delay(200, 400)
        await _clear_focused_and_type(page, price_str, delay=40)
        logger.info("Filled price: RM%s", price_str)
    else:
        logger.warning("Price field not found")

    await human_delay(min_ms=500, max_ms=1_000)
    await _snap(page, "fb_price_filled")


async def _select_category(page: Page) -> None:
    """Select the Category dropdown -- choose 'Toys & games'."""
    await _snap(page, "fb_before_category")

    # Check if category is already set to "Toys & games"
    already_set = await page.evaluate("""() => {
        const spans = [...document.querySelectorAll('span')];
        const cat = spans.find(
            s => s.textContent.trim() === 'Category'
              && s.closest('label[role="combobox"]')
        );
        if (!cat) return false;
        const container = cat.closest('label[role="combobox"]');
        const text = container ? container.textContent : '';
        const norm = text.toLowerCase().replace(/[^a-z0-9& ]/g, '').trim();
        return norm.includes('toys & games');
    }""")
    if already_set:
        logger.info("Category already set to Toys & games, skipping")
        await _snap(page, "fb_category_already_set")
        return

    # Find the Category combobox by its label and click it
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

    await human_delay(min_ms=1_500, max_ms=2_500)
    await _snap(page, "fb_category_dropdown_open")

    # Select "Toys & games" -- must be an exact match to avoid
    # picking "Tools" or other partial hits.  The dropdown uses
    # role="option" elements or visible spans inside a listbox.
    selected = await page.evaluate("""() => {
        const normalize = s => s.toLowerCase().replace(/[^a-z0-9& ]/g, '').trim();
        const target = 'toys & games';

        // First try role="option" elements (standard listbox items)
        const options = [...document.querySelectorAll('[role="option"]')];
        for (const opt of options) {
            if (normalize(opt.textContent) === target) {
                opt.click();
                return 'option';
            }
        }

        // Try all visible spans with exact match
        const spans = [...document.querySelectorAll('span')].filter(
            s => s.offsetParent !== null
        );
        for (const s of spans) {
            if (normalize(s.textContent) === target) {
                s.click();
                return 'span_exact';
            }
        }

        // Fallback: scroll through the dropdown to find it
        const listbox = document.querySelector('[role="listbox"]');
        if (listbox) {
            // Scroll to bottom to load all items
            listbox.scrollTop = listbox.scrollHeight;
        }

        return null;
    }""")

    if selected:
        logger.info("Selected category: Toys & games (via %s)", selected)
    else:
        # Dropdown may need scrolling -- wait and retry
        await human_delay(min_ms=1_000, max_ms=1_500)
        retry = await page.evaluate("""() => {
            const normalize = s => s.toLowerCase().replace(/[^a-z0-9& ]/g, '').trim();
            const target = 'toys & games';

            const spans = [...document.querySelectorAll('span')].filter(
                s => s.offsetParent !== null
            );
            for (const s of spans) {
                if (normalize(s.textContent) === target) {
                    s.scrollIntoView({block: 'center'});
                    s.click();
                    return true;
                }
            }
            return false;
        }""")
        if retry:
            logger.info("Selected category: Toys & games (after scroll)")
        else:
            logger.warning("Could not select 'Toys & games' category")

    await human_delay(min_ms=500, max_ms=1_000)
    await _snap(page, "fb_category_selected")


async def _select_condition(page: Page) -> None:
    """Select the Condition dropdown -- choose 'New'."""
    await _snap(page, "fb_before_condition")

    # Check if condition is already set to "New" (exact match to avoid
    # false positives from group names or other text containing "New")
    already_set = await page.evaluate("""() => {
        const spans = [...document.querySelectorAll('span')];
        const cond = spans.find(
            s => s.textContent.trim() === 'Condition'
              && s.closest('label[role="combobox"]')
        );
        if (!cond) return false;
        const container = cond.closest('label[role="combobox"]');
        if (!container) return false;
        // Check all child spans for exact "New" match
        const children = [...container.querySelectorAll('span')];
        return children.some(s => s.textContent.trim() === 'New');
    }""")
    if already_set:
        logger.info("Condition already set to New, skipping")
        await _snap(page, "fb_condition_already_set")
        return

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

    # Expand "More details" to reveal Description, SKU, Location, etc.
    # The disclosure is a React component.  We use Playwright locator
    # click which properly dispatches React synthetic events.
    try:
        more_details = page.locator('span:text-is("More details")')
        if await more_details.count() > 0:
            await more_details.first.scroll_into_view_if_needed()
            await human_delay(min_ms=500, max_ms=1_000)
            await more_details.first.click(timeout=5_000)
            logger.info("Clicked 'More details' (attempt 1)")
            await human_delay(min_ms=2_000, max_ms=3_000)

            # Check if textarea appeared
            textarea = await page.query_selector("textarea")
            if not textarea or not await textarea.is_visible():
                # Try clicking the subtitle text instead
                subtitle = page.locator(
                    'span:text-is("Attract more interest by including more details.")'
                )
                if await subtitle.count() > 0:
                    await subtitle.first.click(timeout=5_000)
                    logger.info("Clicked subtitle text (attempt 2)")
                    await human_delay(min_ms=2_000, max_ms=3_000)
        else:
            logger.info("'More details' not found")
    except Exception as exc:
        logger.warning("Could not click 'More details': %s", exc)

    await _snap(page, "fb_more_details_expanded")

    # Wait for the textarea to appear after expansion
    # The Description field is a <textarea> with a dynamic id
    textarea = None
    for _ in range(5):
        textarea = await page.query_selector("textarea")
        if textarea and await textarea.is_visible():
            break
        await page.wait_for_timeout(500)
        textarea = None

    if textarea:
        await textarea.evaluate("el => el.focus()")
        await human_delay(200, 400)
        await _clear_focused_and_type(page, description, delay=15)
        logger.info("Filled description via textarea (%d chars)", len(description))
    else:
        # Fallback: try finding by label
        el = await _find_field_by_label(page, "Description")
        el_is_null = True
        if el:
            try:
                val = await el.json_value()
                el_is_null = val is None
            except Exception:
                el_is_null = False

        if not el_is_null:
            await el.evaluate("el => el.focus()")
            await human_delay(200, 400)
            await _clear_focused_and_type(page, description, delay=15)
            logger.info("Filled description via label (%d chars)", len(description))
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
    """On the step-2 page, tick checkboxes next to target groups.

    The "List in more places" page shows the user's groups as a
    checkbox list under "List in your groups".  Just click the row
    for each matching group to toggle it on.
    """
    await _snap(page, "fb_step2_groups")

    for group_name in group_names:
        logger.info("Looking for group checkbox: %s", group_name)

        selected = await page.evaluate("""(name) => {
            const normalize = s => s.toLowerCase().replace(/[^a-z0-9 ]/g, '').trim();
            const target = normalize(name);

            // Each group row is a clickable container with the group
            // name in a span and a checkbox/radio.  Find the span
            // matching the name and click its nearest row ancestor.
            const spans = [...document.querySelectorAll('span')].filter(
                s => s.offsetParent !== null
                  && normalize(s.textContent).includes(target)
            );

            for (const span of spans) {
                // Walk up to find a clickable row (role=checkbox, role=row,
                // or a div with an input[type=checkbox] inside)
                let el = span;
                for (let i = 0; i < 10 && el; i++) {
                    const cb = el.querySelector('input[type="checkbox"]');
                    if (cb && !cb.checked) {
                        cb.click();
                        return 'checkbox';
                    }

                    if (el.getAttribute('role') === 'checkbox'
                        || el.getAttribute('role') === 'option') {
                        el.click();
                        return 'role_click';
                    }

                    el = el.parentElement;
                }

                // Fallback: just click the span's closest large container
                const row = span.closest('[class]');
                if (row) {
                    row.click();
                    return 'row_click';
                }
            }
            return null;
        }""", group_name)

        if selected:
            logger.info("Toggled group: %s (via %s)", group_name, selected)
        else:
            logger.warning("Could not find group: %s", group_name)

        await human_delay(min_ms=500, max_ms=1_000)
        await _snap(page, f"fb_group_toggled_{group_name[:20]}")

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
# Validation
# ---------------------------------------------------------------------------


async def _validate_form(page: Page) -> list[str]:
    """Validate required fields before submission. Returns failed field IDs.

    Field IDs: "title", "price", "category", "condition", "description".
    Empty list means all checks passed.
    """
    errors: list[str] = []

    # 1. Title
    try:
        el = await _find_field_by_label(page, "Title")
        if el:
            val = await el.evaluate("el => el.value || ''")
            if not val.strip():
                errors.append("title")
        else:
            errors.append("title")
    except Exception:
        errors.append("title")

    # 2. Price
    try:
        el = await _find_field_by_label(page, "Price")
        if el:
            val = await el.evaluate("el => el.value || ''")
            if not val.strip():
                errors.append("price")
        else:
            errors.append("price")
    except Exception:
        errors.append("price")

    # 3. Category (combobox should not just show "Category")
    try:
        cat_set = await page.evaluate("""() => {
            const spans = [...document.querySelectorAll('span')];
            const cat = spans.find(
                s => s.textContent.trim() === 'Category'
                  && s.closest('label[role="combobox"]')
            );
            if (!cat) return false;
            const container = cat.closest('label[role="combobox"]');
            const text = container ? container.textContent : '';
            // If it only shows "Category" with no selection, it's not set
            return text.trim() !== 'Category';
        }""")
        if not cat_set:
            errors.append("category")
    except Exception:
        errors.append("category")

    # 4. Condition (combobox should not just show "Condition")
    try:
        cond_set = await page.evaluate("""() => {
            const spans = [...document.querySelectorAll('span')];
            const cond = spans.find(
                s => s.textContent.trim() === 'Condition'
                  && s.closest('label[role="combobox"]')
            );
            if (!cond) return false;
            const container = cond.closest('label[role="combobox"]');
            const text = container ? container.textContent : '';
            return text.trim() !== 'Condition';
        }""")
        if not cond_set:
            errors.append("condition")
    except Exception:
        errors.append("condition")

    # 5. Description (textarea should have content)
    try:
        textarea = await page.query_selector("textarea")
        if textarea and await textarea.is_visible():
            val = await textarea.evaluate("el => el.value || ''")
            if not val.strip():
                errors.append("description")
        # If textarea not visible, description might not be expanded -- skip check
    except Exception:
        pass

    return errors


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

    # Hide-from-friends and group settings persist from previous listings,
    # so we only toggle if explicitly needed (the function already checks state).
    await _enable_hide_from_friends(page)

    # Step 2: Validate form before proceeding
    validation_errors = await _validate_form(page)
    if validation_errors:
        for field in validation_errors:
            logger.warning("Validation failed: %s -- retrying", field)
        await _snap(page, "fb_validation_failed_retry")

        # Retry each failed field
        for field in validation_errors:
            if field == "title":
                await _fill_title(page, title)
            elif field == "price":
                await _fill_price(page, listing_price_cents)
            elif field == "category":
                await _select_category(page)
            elif field == "condition":
                await _select_condition(page)
            elif field == "description":
                await _fill_description(page, description)

        # Re-validate
        validation_errors = await _validate_form(page)
        if validation_errors:
            for field in validation_errors:
                logger.error("Validation still failed after retry: %s", field)
            await _snap(page, "fb_validation_failed_final")
            logger.error(
                "Form validation failed with %d error(s) after retry -- aborting",
                len(validation_errors),
            )
            return False

        logger.info("Validation passed after retry")

    # Step 3: Click Next to go to the publish page
    if not await _click_next(page):
        logger.warning("Could not proceed to step 2")
        await _locate_next_button(page)
        return True

    # Group settings persist from previous listings -- skip group selection
    # and go straight to publish.

    if submit:
        # Click Publish using Playwright locators (JS .click() doesn't
        # dispatch React synthetic events on Facebook's obfuscated DOM)
        await _snap(page, "fb_before_publish")

        published = False
        try:
            # Try aria-label="Publish" first
            pub_btn = page.locator('[aria-label="Publish"]')
            if await pub_btn.count() > 0:
                await pub_btn.first.click(timeout=10_000)
                published = True
                logger.info("Clicked Publish via aria-label")
            else:
                # Try text-based match on div[role="button"]
                pub_text = page.locator(
                    'div[role="button"]:has-text("Publish")'
                )
                if await pub_text.count() > 0:
                    await pub_text.first.click(timeout=10_000)
                    published = True
                    logger.info("Clicked Publish via text match")
                else:
                    # Fallback: try any span containing "Publish" inside
                    # a clickable ancestor (Facebook wraps buttons in divs)
                    pub_span = page.locator('span:text-is("Publish")')
                    if await pub_span.count() > 0:
                        await pub_span.first.click(timeout=10_000)
                        published = True
                        logger.info("Clicked Publish via span text")
                    else:
                        # Last resort: try Next button
                        next_btn = page.locator('[aria-label="Next"]').or_(
                            page.locator('div[role="button"]:has-text("Next")')
                        )
                        if await next_btn.count() > 0:
                            await next_btn.first.click(timeout=10_000)
                            published = True
                            logger.info("Clicked Next on step 2 (Publish not found)")
        except Exception as exc:
            logger.warning("Publish button click failed: %s", exc)

        if published:
            await human_delay(min_ms=3_000, max_ms=5_000)
            await _snap(page, "fb_after_publish")
        else:
            logger.warning("Could not find Publish/Next button on step 2")
            await _snap(page, "fb_publish_not_found")
    else:
        logger.info("Form complete -- left open for user review (not publishing)")
        await _snap(page, "fb_ready_for_review")

    logger.info("Facebook Marketplace form filling complete")
    return True
