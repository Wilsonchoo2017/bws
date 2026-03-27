"""Human-like interaction helpers for anti-detection.

All click and type actions should go through these functions to randomize
cursor position within elements, vary timing, and avoid bot-like patterns.
"""


import secrets

from playwright.async_api import ElementHandle, Page

from services.shopee.browser import human_delay


async def random_click(
    page: Page,
    selector: str,
    *,
    timeout: int = 30_000,
) -> None:
    """Click an element at a random position within its bounding box.

    Instead of clicking dead-center (bot-like), picks a random point
    within the element's visible area with some padding from edges.

    Args:
        page: Playwright page
        selector: CSS selector of the element to click
        timeout: Max time to wait for element
    """
    el = await page.wait_for_selector(selector, timeout=timeout)
    if not el:
        raise ValueError(f"Element not found: {selector}")
    await random_click_element(el)


async def random_click_element(el: ElementHandle) -> None:
    """Click an ElementHandle at a random position within its bounds."""
    box = await el.bounding_box()
    if not box:
        await el.click()
        return

    # Pick a random point with 20% padding from edges
    pad_x = box["width"] * 0.2
    pad_y = box["height"] * 0.2

    # Ensure padding doesn't exceed half the dimension
    pad_x = min(pad_x, box["width"] * 0.4)
    pad_y = min(pad_y, box["height"] * 0.4)

    offset_x = pad_x + _rand_float() * (box["width"] - 2 * pad_x)
    offset_y = pad_y + _rand_float() * (box["height"] - 2 * pad_y)

    await el.click(position={"x": offset_x, "y": offset_y})


async def random_type(
    page: Page,
    selector: str,
    text: str,
    *,
    min_delay_ms: int = 50,
    max_delay_ms: int = 120,
) -> None:
    """Type text into an element with randomized per-keystroke delay.

    Each keystroke has a slightly different delay to mimic human typing.

    Args:
        page: Playwright page
        selector: CSS selector of the input element
        text: Text to type
        min_delay_ms: Minimum delay between keystrokes in ms
        max_delay_ms: Maximum delay between keystrokes in ms
    """
    el = await page.wait_for_selector(selector, timeout=10_000)
    if not el:
        raise ValueError(f"Element not found: {selector}")

    # Click the element at a random position first
    await random_click_element(el)
    await human_delay(min_ms=200, max_ms=500)

    # Type each character with varying delay
    for char in text:
        delay_ms = min_delay_ms + secrets.randbelow(max_delay_ms - min_delay_ms + 1)
        await page.keyboard.type(char, delay=delay_ms)


def _rand_float() -> float:
    """Return a random float between 0.0 and 1.0."""
    return secrets.randbelow(10_000) / 10_000.0
