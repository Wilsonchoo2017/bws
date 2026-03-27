"""Popup detection, language selection, and dismissal for Shopee."""


from playwright.async_api import Page

from services.shopee.browser import human_delay
from services.shopee.humanize import random_click_element

async def select_english(page: Page) -> bool:
    """Select English from the language picker dialog if it appears.

    This only handles the blocking language selection modal that Shopee
    shows on first-ever visit. It does NOT touch the navbar language dropdown.

    Looks for a centered modal/dialog containing language options and
    clicks the "English" button/link inside it.

    Returns:
        True if language was selected, False if no language dialog found.
    """
    found = await page.evaluate("""() => {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const centerX = vw / 2;
        const centerY = vh / 2;

        // Find a centered modal (not in the navbar -- must be vertically centered)
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const r = el.getBoundingClientRect();
            // Must be a mid-screen modal, not the navbar
            if (r.width < 200 || r.height < 100 || r.y < 50) continue;
            if (r.width > vw * 0.8) continue;

            const elCenterX = r.x + r.width / 2;
            const elCenterY = r.y + r.height / 2;
            if (Math.abs(elCenterX - centerX) > 200) continue;
            if (Math.abs(elCenterY - centerY) > 200) continue;

            // This looks like a centered modal -- find "English" inside it
            const links = el.querySelectorAll('a, button, div, span');
            for (const link of links) {
                const text = link.textContent.trim();
                if (text === 'English') {
                    const lr = link.getBoundingClientRect();
                    if (lr.width > 10 && lr.width < 300 && lr.height > 10 && lr.height < 80) {
                        link.setAttribute('data-bws-lang', 'true');
                        return true;
                    }
                }
            }
        }
        return false;
    }""")

    if found:
        el = await page.query_selector('[data-bws-lang="true"]')
        if el:
            await page.evaluate("el => el.removeAttribute('data-bws-lang')", el)
            try:
                await el.click(timeout=3_000)
                await human_delay(min_ms=500, max_ms=1_000)
                return True
            except Exception:
                return False
    return False


async def _find_modal_close_button(page: Page):
    """Find the X close button for the Shopee promo modal.

    The modal is a large centered IMG element. The close button is a small
    DIV (outside the modal) containing an SVG with two crossing paths (X shape).
    We find it by looking for a small clickable element near the top-right
    area of any large centered element (the modal).

    Returns:
        ElementHandle of the close button, or None.
    """
    result = await page.evaluate("""() => {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const centerX = vw / 2;

        // Find the modal -- a large centered element
        const all = document.querySelectorAll('*');
        let modal = null;
        for (const el of all) {
            const r = el.getBoundingClientRect();
            if (r.width > 300 && r.width < vw * 0.8 && r.height > 300 && r.height < vh * 0.9) {
                const elCenterX = r.x + r.width / 2;
                if (Math.abs(elCenterX - centerX) < 100) {
                    modal = el;
                }
            }
        }
        if (!modal) return null;

        const mr = modal.getBoundingClientRect();

        // Find a small element near the top-right of the modal that has
        // cursor:pointer and contains an SVG (the X icon)
        for (const el of all) {
            const r = el.getBoundingClientRect();
            const isSmall = r.width >= 15 && r.width <= 50 && r.height >= 15 && r.height <= 50;
            const nearTopRight = (
                r.x >= mr.x + mr.width - 100 &&
                r.x <= mr.x + mr.width + 50 &&
                r.y >= mr.y - 50 &&
                r.y <= mr.y + 50
            );
            const isClickable = window.getComputedStyle(el).cursor === 'pointer';
            const hasSvg = el.querySelector('svg') !== null || el.tagName === 'SVG';

            if (isSmall && nearTopRight && isClickable && hasSvg) {
                // Return a selector we can use to click it
                // Add a temporary data attribute
                el.setAttribute('data-bws-close', 'true');
                return true;
            }
        }
        return null;
    }""")

    if result:
        el = await page.query_selector('[data-bws-close="true"]')
        if el:
            # Clean up the temp attribute
            await page.evaluate(
                "el => el.removeAttribute('data-bws-close')",
                el,
            )
            return el
    return None


async def dismiss_popups(page: Page) -> int:
    """Attempt to close all visible popups.

    Strategy:
    1. Find the promo modal's X close button by DOM inspection
    2. Fall back to Escape key
    3. Try known CSS selectors as last resort

    Returns:
        Number of popups dismissed.
    """
    dismissed = 0

    # Strategy 1: Find and click the modal's X close button precisely
    close_btn = await _find_modal_close_button(page)
    if close_btn:
        try:
            await random_click_element(close_btn)
            dismissed += 1
            await page.wait_for_timeout(500)
        except Exception:
            pass

    # Strategy 2: Escape key
    if dismissed == 0:
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
        except Exception:
            pass

    # Strategy 3: Known close button selectors
    fallback_selectors = (
        '.shopee-popup__close-btn',
        '[aria-label="Close"]',
        '[aria-label="close"]',
        '.shopee-authen--close',
    )
    for selector in fallback_selectors:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                if await el.is_visible():
                    box = await el.bounding_box()
                    if box and box["width"] < 60 and box["height"] < 60:
                        await random_click_element(el)
                        dismissed += 1
                        await page.wait_for_timeout(500)
        except Exception:
            continue

    return dismissed


def setup_dialog_handler(page: Page) -> None:
    """Auto-dismiss JavaScript alert/confirm/prompt dialogs."""
    page.on("dialog", lambda dialog: dialog.dismiss())


async def dismiss_popups_loop(
    page: Page,
    interval_ms: int = 3_000,
    max_rounds: int = 5,
) -> int:
    """Run popup dismissal multiple rounds with delays.

    Returns:
        Total number of popups dismissed.
    """
    total = 0
    for _ in range(max_rounds):
        count = await dismiss_popups(page)
        total += count
        if count == 0:
            break
        await page.wait_for_timeout(interval_ms)
    return total
