"""Keepa price history scraper with Cloudflare and login handling.

Uses Playwright + Camoufox to load Keepa, bypass Cloudflare,
log in, search for a LEGO set, and intercept price history data
from internal API responses. Sends ntfy notification when a
Cloudflare challenge or login CAPTCHA requires human intervention.
"""

import asyncio
import logging
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page

from config.settings import KEEPA_CONFIG, KEEPA_RATE_LIMITER
from services.browser import human_delay
from services.keepa.auth import is_logged_in, login
from services.keepa.parser import click_all_date_range, extract_product_data
from services.keepa.types import KeepaDataPoint, KeepaProductData, KeepaScrapeResult
from services.notifications.ntfy import NtfyMessage, send_notification

logger = logging.getLogger("bws.keepa.scraper")

KEEPA_BASE = "https://keepa.com"

# Cloudflare challenge indicators
CF_CHALLENGE_TITLES: tuple[str, ...] = (
    "just a moment",
    "attention required",
    "checking your browser",
)


def _keepa_browser() -> AsyncCamoufox:
    """Create a Camoufox browser context for Keepa."""
    user_data_path = Path(KEEPA_CONFIG.user_data_dir).expanduser()
    user_data_path.mkdir(parents=True, exist_ok=True)

    return AsyncCamoufox(
        headless=KEEPA_CONFIG.headless,
        geoip=True,
        locale=KEEPA_CONFIG.locale,
        os="macos",
        humanize=True,
        persistent_context=True,
        user_data_dir=str(user_data_path),
        window=(KEEPA_CONFIG.viewport_width, KEEPA_CONFIG.viewport_height),
    )


def _notify_captcha(query: str) -> None:
    """Send ntfy notification asking user to solve a Cloudflare challenge."""
    send_notification(
        NtfyMessage(
            title="Keepa: Cloudflare challenge",
            message=(
                f"Keepa search for '{query}' hit a Cloudflare challenge. "
                "Please open the browser window and solve the captcha."
            ),
            priority=5,
            tags=("warning", "robot"),
        )
    )


async def _detect_cloudflare(page: Page) -> bool:
    """Check if the current page is a Cloudflare challenge."""
    try:
        title = await page.title()
        return any(cf in title.lower() for cf in CF_CHALLENGE_TITLES)
    except Exception:
        return False


async def _wait_for_cloudflare(
    page: Page,
    query: str,
    timeout_s: int | None = None,
) -> bool:
    """Wait for a Cloudflare challenge to be solved.

    Sends an ntfy notification, then polls until the challenge page
    is gone or the timeout is reached.

    Returns True if challenge was solved, False on timeout.
    """
    timeout = timeout_s or KEEPA_CONFIG.captcha_timeout_s
    logger.warning("Cloudflare challenge detected for query: %s", query)
    _notify_captcha(query)

    elapsed = 0
    poll_interval = 3
    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        if not await _detect_cloudflare(page):
            logger.info("Cloudflare challenge solved after %ds", elapsed)
            return True

    logger.error(
        "Cloudflare challenge timeout after %ds for query: %s",
        timeout, query,
    )
    return False


async def scrape_keepa(
    set_number: str,
    *,
    headless: bool | None = None,
) -> KeepaScrapeResult:
    """Scrape Keepa price history for a LEGO set.

    Flow:
    1. Launch browser with persistent keepa profile
    2. Navigate to keepa.com
    3. Handle Cloudflare challenge if present
    4. Log in if needed
    5. Search for the set number
    6. Click first matching result
    7. Set date range to 'All'
    8. Intercept API responses for chart data
    9. Fall back to DOM extraction if API interception fails

    Args:
        set_number: LEGO set number (e.g. "60305")
        headless: Override headless setting

    Returns:
        KeepaScrapeResult with parsed product data or error
    """
    await KEEPA_RATE_LIMITER.acquire()

    try:
        async with _keepa_browser() as browser:
            page = await browser.new_page()

            # Navigate to Keepa
            logger.info("Navigating to %s", KEEPA_BASE)
            await page.goto(KEEPA_BASE, wait_until="domcontentloaded")
            await human_delay(3_000, 5_000)

            # Handle Cloudflare challenge
            if await _detect_cloudflare(page):
                solved = await _wait_for_cloudflare(page, set_number)
                if not solved:
                    return KeepaScrapeResult(
                        success=False,
                        set_number=set_number,
                        error="Cloudflare challenge not solved within timeout",
                    )
                await page.goto(KEEPA_BASE, wait_until="domcontentloaded")
                await human_delay(3_000, 5_000)

            # Check login state, log in if needed
            if not await is_logged_in(page):
                logged_in = await login(page)
                if not logged_in:
                    return KeepaScrapeResult(
                        success=False,
                        set_number=set_number,
                        error="Keepa login failed",
                    )
                await human_delay(2_000, 3_000)

            # Search for the LEGO set
            search_query = f"{set_number} lego"
            logger.info("Searching Keepa for: %s", search_query)

            search_input = await _find_search_box(page)
            if not search_input:
                return KeepaScrapeResult(
                    success=False,
                    set_number=set_number,
                    error="Could not find Keepa search box",
                )

            # Use JS click to avoid Playwright timeout on Keepa's SPA
            await search_input.evaluate("el => el.click()")
            await human_delay(300, 600)

            # Focus and select all existing text
            await search_input.evaluate("el => { el.focus(); el.select(); }")
            await human_delay(100, 200)

            # Type search query with human-like delays
            for char in search_query:
                delay_ms = secrets.randbelow(70) + 50
                await page.keyboard.type(char, delay=delay_ms)
            await human_delay(800, 1_500)

            # Press Enter to search
            await page.keyboard.press("Enter")
            await human_delay(3_000, 5_000)

            # Cloudflare often triggers after search submission
            if await _detect_cloudflare(page):
                solved = await _wait_for_cloudflare(page, set_number)
                if not solved:
                    return KeepaScrapeResult(
                        success=False,
                        set_number=set_number,
                        error="Cloudflare challenge not solved within timeout",
                    )
                # After solving, the search results should load
                await human_delay(3_000, 5_000)

            # Wait for search results (ag-grid takes time to render)
            try:
                await page.wait_for_selector(
                    ".ag-row, .ag-row-first", timeout=15_000
                )
            except Exception:
                logger.debug("ag-grid rows not found, waiting longer")
                await human_delay(3_000, 5_000)

            await page.wait_for_load_state("networkidle")
            await human_delay(1_000, 2_000)

            # Check Cloudflare again (can trigger on result page too)
            if await _detect_cloudflare(page):
                solved = await _wait_for_cloudflare(page, set_number)
                if not solved:
                    return KeepaScrapeResult(
                        success=False,
                        set_number=set_number,
                        error="Cloudflare challenge not solved within timeout",
                    )
                await human_delay(3_000, 5_000)
                # Re-wait for results after Cloudflare
                try:
                    await page.wait_for_selector(
                        ".ag-row, .ag-row-first", timeout=15_000
                    )
                except Exception:
                    pass

            # Click first matching result
            clicked = await _click_first_result(page, set_number)
            if not clicked:
                return KeepaScrapeResult(
                    success=False,
                    set_number=set_number,
                    error=f"No search results found for {set_number}",
                )

            await human_delay(3_000, 5_000)
            await page.wait_for_load_state("networkidle")
            await human_delay(1_000, 2_000)

            # Click "All" date range (Year first, then All appears)
            await click_all_date_range(page)
            await human_delay(3_000, 5_000)

            # Extract product data from the DOM statistics tables
            product_data = await extract_product_data(page, set_number)

            # Sweep the chart canvas to extract historical data via tooltips
            chart_points = await _sweep_chart_tooltips(page)
            if chart_points:
                logger.info(
                    "Chart sweep collected %d tooltip readings", len(chart_points)
                )
                product_data = _merge_chart_points(product_data, chart_points)

            logger.info(
                "Keepa scrape for %s: amazon=%d pts, new=%d pts, "
                "buy_box=%d pts, sales_rank=%d pts",
                set_number,
                len(product_data.amazon_price),
                len(product_data.new_price),
                len(product_data.buy_box),
                len(product_data.sales_rank),
            )

            return KeepaScrapeResult(
                success=True,
                set_number=set_number,
                product_data=product_data,
            )

    except Exception as exc:
        logger.exception("Keepa scrape failed for set: %s", set_number)
        return KeepaScrapeResult(
            success=False,
            set_number=set_number,
            error=str(exc),
        )


async def _find_search_box(page: Page) -> Any | None:
    """Find the Keepa search input element.

    The search bar is hidden behind a 'Search' menu item in the top nav.
    Click #showSearchBar to reveal #searchInput, or try the search
    icon (#menuSearch). Falls back to direct hash navigation.
    """
    # Wait for the top nav to load, then click the search trigger
    try:
        btn = await page.wait_for_selector(
            "#showSearchBar", state="visible", timeout=10_000
        )
        if btn:
            await btn.click()
            await human_delay(800, 1_500)
    except Exception:
        logger.debug("showSearchBar not found, trying alternatives")
        for selector in ("#menuSearch", 'a:has-text("Search")'):
            try:
                alt = await page.query_selector(selector)
                if alt and await alt.is_visible():
                    await alt.click()
                    await human_delay(800, 1_500)
                    break
            except Exception:
                continue

    # Wait for search input to become visible
    try:
        el = await page.wait_for_selector(
            "#searchInput", state="visible", timeout=5_000
        )
        if el:
            return el
    except Exception:
        pass

    # Fallback: navigate to search page via hash
    logger.info("Search box not found, navigating to search page")
    await page.goto("https://keepa.com/#!search", wait_until="domcontentloaded")
    await human_delay(2_000, 3_000)

    try:
        el = await page.wait_for_selector(
            "#searchInput", state="visible", timeout=5_000
        )
        if el:
            return el
    except Exception:
        pass

    return None


async def _click_first_result(page: Page, set_number: str) -> bool:
    """Click the first search result matching the set number.

    Keepa uses ag-grid for search results. The clickable product title
    is an <a> tag inside a grid cell within an ag-row.
    """
    # Primary: click the <a> link inside the first ag-row containing the set number
    selectors = (
        f'.ag-row a:has-text("{set_number}")',
        f'div[role="row"] a:has-text("{set_number}")',
        ".ag-row-first a",
        'div[role="row"]:first-child a',
        f'a:has-text("{set_number}")',
    )

    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=5_000)
            if el and await el.is_visible():
                await el.click()
                logger.info("Clicked search result: %s", sel)
                return True
        except Exception:
            continue

    # Fallback: click the first visible ag-row itself
    try:
        row = await page.query_selector(".ag-row-first, .ag-row[row-index='0']")
        if row and await row.is_visible():
            await row.click()
            logger.info("Clicked first ag-row directly")
            return True
    except Exception:
        pass

    return False


async def _sweep_chart_tooltips(page: Page) -> list[dict[str, Any]]:
    """Sweep the mouse across the chart canvas to collect tooltip data.

    Keepa shows date and price tooltips when hovering over the canvas.
    We move the mouse across the chart width in steps to collect
    historical data points.

    Returns a list of dicts with 'date', 'label', 'price' keys.
    """
    try:
        # Find the chart canvas
        canvases = await page.query_selector_all("canvas")
        chart_box = None
        for canvas in canvases:
            box = await canvas.bounding_box()
            if box and box["width"] > 400 and box["height"] > 200:
                chart_box = box
                break

        if not chart_box:
            logger.warning("Could not find chart canvas for tooltip sweep")
            return []

        logger.info(
            "Sweeping chart canvas: x=%.0f y=%.0f w=%.0f h=%.0f",
            chart_box["x"], chart_box["y"],
            chart_box["width"], chart_box["height"],
        )

        # Sweep using Playwright mouse.move (triggers jQuery/Flot events)
        # then batch-read tooltips periodically
        chart_x = chart_box["x"]
        chart_y_mid = chart_box["y"] + chart_box["height"] * 0.4
        chart_width = chart_box["width"]
        num_steps = 50

        raw_tooltips: list[dict[str, Any]] = []

        for i in range(num_steps):
            x = chart_x + (chart_width * i / num_steps)
            await page.mouse.move(x, chart_y_mid)
            await asyncio.sleep(0.1)

            tooltip = await page.evaluate("""() => {
                // Read flotTip divs
                const tips = document.querySelectorAll('.flotTip, [id^="flotTip"]');
                const parts = [];
                for (const t of tips) {
                    if (t.offsetParent !== null && t.textContent.trim()) {
                        parts.push(t.textContent.trim());
                    }
                }
                if (parts.length > 0) return parts.join(' | ');

                // Read combined info line near chart top
                const els = document.querySelectorAll('div, span');
                for (const el of els) {
                    if (!el.offsetParent) continue;
                    const text = (el.textContent || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text.includes('$') && text.length > 30 &&
                        text.length < 300 && rect.width > 200 &&
                        /Mon|Tue|Wed|Thu|Fri|Sat|Sun/.test(text)) {
                        return text;
                    }
                }
                return null;
            }""")

            if tooltip:
                raw_tooltips.append({"step": i, "x": int(x), "text": tooltip})

        points: list[dict[str, Any]] = []
        seen_dates: set[str] = set()

        for item in (raw_tooltips or []):
            tooltip = item.get("text", "")
            if not tooltip:
                continue

            date_match = re.search(
                r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+"
                r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
                r"\d{1,2}\s+\d{1,2}:\d{2})",
                tooltip,
            )

            date_str = date_match.group(1).strip() if date_match else f"step_{item['step']}"
            if date_str in seen_dates:
                continue
            seen_dates.add(date_str)

            search_text = tooltip[date_match.end():] if date_match else tooltip
            price_matches = re.findall(
                r"(Amazon|New, 3rd Party FBA|New, 3rd Party FBM|"
                r"New|Buy Box|Used, like new|Used|"
                r"Warehouse Deals|Collectible|List Price)"
                r"\$\s*([\d,.]+)",
                search_text,
            )

            for label, price in price_matches:
                points.append({
                    "date": date_str,
                    "label": label.strip(),
                    "price": price.strip(),
                })

        # Move mouse away from chart
        await page.mouse.move(0, 0)

        return points
    except Exception:
        logger.exception("Chart tooltip sweep failed")
        return []


def _merge_chart_points(
    product_data: KeepaProductData,
    chart_points: list[dict[str, Any]],
) -> KeepaProductData:
    """Merge tooltip-extracted chart points into the product data.

    Maps tooltip labels to the appropriate price series fields.
    """
    label_map = {
        "New": "new_price",
        "Amazon": "amazon_price",
        "Buy Box": "buy_box",
        "New, 3rd Party FBA": "new_3p_fba",
        "New, 3rd Party FBM": "new_3p_fbm",
        "Used": "used_price",
        "Used, like new": "used_like_new",
        "Warehouse Deals": "warehouse_deals",
        "Collectible": "collectible",
        "List Price": "list_price",
    }

    series: dict[str, list[KeepaDataPoint]] = {
        field: list(getattr(product_data, field))
        for field in label_map.values()
    }

    # Deduplicate by (field, date, value)
    seen: set[tuple[str, str, int]] = set()

    for point in chart_points:
        label = point["label"]
        field = label_map.get(label)
        if not field:
            for key, val in label_map.items():
                if key in label:
                    field = val
                    break
        if not field:
            continue

        try:
            cents = int(float(point["price"].replace(",", "")) * 100)
        except (ValueError, TypeError):
            continue

        key = (field, point["date"], cents)
        if key in seen:
            continue
        seen.add(key)

        series[field].append(
            KeepaDataPoint(date=point["date"], value=cents)
        )

    return KeepaProductData(
        set_number=product_data.set_number,
        asin=product_data.asin,
        title=product_data.title,
        keepa_url=product_data.keepa_url,
        scraped_at=product_data.scraped_at,
        amazon_price=tuple(series["amazon_price"]),
        new_price=tuple(series["new_price"]),
        new_3p_fba=tuple(series["new_3p_fba"]),
        new_3p_fbm=tuple(series["new_3p_fbm"]),
        used_price=tuple(series["used_price"]),
        used_like_new=tuple(series["used_like_new"]),
        buy_box=tuple(series["buy_box"]),
        list_price=tuple(series["list_price"]),
        warehouse_deals=tuple(series["warehouse_deals"]),
        collectible=tuple(series["collectible"]),
        sales_rank=product_data.sales_rank,
        current_buy_box_cents=product_data.current_buy_box_cents,
        current_amazon_cents=product_data.current_amazon_cents,
        current_new_cents=product_data.current_new_cents,
        lowest_ever_cents=product_data.lowest_ever_cents,
        highest_ever_cents=product_data.highest_ever_cents,
    )


def scrape_keepa_sync(
    set_number: str,
    *,
    headless: bool | None = None,
) -> KeepaScrapeResult:
    """Synchronous wrapper for scrape_keepa."""
    return asyncio.run(scrape_keepa(set_number, headless=headless))
