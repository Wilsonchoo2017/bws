"""Keepa price history scraper with Cloudflare and login handling.

Uses Playwright + Camoufox to load Keepa, bypass Cloudflare,
log in, search for a LEGO set, and intercept price history data
from internal API responses. Sends ntfy notification when a
Cloudflare challenge or login CAPTCHA requires human intervention.
"""

import asyncio
import dataclasses
import logging
import re
import secrets
import time
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
from services.notifications.scraper_alerts import alert_cloudflare_blocked

logger = logging.getLogger("bws.keepa.scraper")

KEEPA_BASE = "https://keepa.com"

# Cloudflare challenge indicators
CF_CHALLENGE_TITLES: tuple[str, ...] = (
    "just a moment",
    "attention required",
    "checking your browser",
)

# In-page Cloudflare Turnstile widget selectors (iframe/div)
CF_WIDGET_SELECTORS: tuple[str, ...] = (
    'iframe[src*="challenges.cloudflare.com"]',
    'iframe[src*="cloudflare.com/cdn-cgi/challenge"]',
    "#cf-turnstile",
    ".cf-turnstile",
    "#turnstile-wrapper",
)

# Consecutive Cloudflare challenge tracking for preventive alerts
_cf_challenge_count: int = 0
_cf_last_challenge: float = 0.0
_CF_RESET_INTERVAL: float = 3600.0  # reset counter after 1 hour of no challenges
_CF_ALERT_THRESHOLD: int = 2  # alert after N consecutive challenges


def _record_cf_challenge(set_number: str) -> None:
    """Track a Cloudflare challenge occurrence and alert if pattern detected."""
    global _cf_challenge_count, _cf_last_challenge
    now = time.monotonic()
    if now - _cf_last_challenge > _CF_RESET_INTERVAL:
        _cf_challenge_count = 0
    _cf_challenge_count += 1
    _cf_last_challenge = now
    if _cf_challenge_count >= _CF_ALERT_THRESHOLD:
        alert_cloudflare_blocked("Keepa", _cf_challenge_count, set_number)


def _record_cf_clear() -> None:
    """Reset Cloudflare challenge counter after a successful scrape."""
    global _cf_challenge_count
    _cf_challenge_count = 0


def _keepa_browser() -> AsyncCamoufox:
    """Create a Camoufox browser context for Keepa."""
    user_data_path = Path(KEEPA_CONFIG.user_data_dir).expanduser()
    user_data_path.mkdir(parents=True, exist_ok=True)

    from services.browser import _clear_stale_profile_lock
    _clear_stale_profile_lock(user_data_path)

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
    """Check if the current page is a Cloudflare challenge.

    Detects full-page challenges (title-based), in-page Turnstile
    widgets (iframe/div checkbox dialogs), and Keepa's custom
    anti-bot modal dialog.
    """
    try:
        title = await page.title()
        if any(cf in title.lower() for cf in CF_CHALLENGE_TITLES):
            return True
    except Exception:
        pass

    # Check for in-page Turnstile widget (checkbox dialog)
    try:
        for selector in CF_WIDGET_SELECTORS:
            el = await page.query_selector(selector)
            if el:
                visible = await el.is_visible()
                if visible:
                    logger.info(
                        "Cloudflare Turnstile widget detected: %s", selector,
                    )
                    return True
    except Exception:
        pass

    # Check for Keepa's in-page anti-bot modal (contains Turnstile
    # widget inside a dialog that may not match standard CF selectors)
    try:
        body_text = await page.evaluate(
            "() => document.body.innerText.substring(0, 1000)"
        )
        if "anti-bot check" in body_text.lower():
            logger.info("Keepa anti-bot check dialog detected via page text")
            return True
    except Exception:
        pass

    return False


async def _try_click_turnstile(page: Page) -> bool:
    """Attempt to click the Cloudflare Turnstile checkbox.

    The Turnstile widget renders inside an iframe. Locate the iframe,
    then click the checkbox input inside it. Uses human-like mouse
    movement to the checkbox center.

    Returns True if a click was attempted, False if widget not found.
    """
    # Find the Turnstile iframe
    iframe_selectors = (
        'iframe[src*="challenges.cloudflare.com"]',
        'iframe[src*="cloudflare.com/cdn-cgi/challenge"]',
        'iframe[title*="Cloudflare"]',
        'iframe[title*="cloudflare"]',
        'iframe[src*="turnstile"]',
    )

    for selector in iframe_selectors:
        try:
            iframe_el = await page.query_selector(selector)
            if not iframe_el or not await iframe_el.is_visible():
                continue

            # Click the center of the iframe — the checkbox is typically
            # positioned near the left side of the widget
            box = await iframe_el.bounding_box()
            if not box:
                continue

            # Checkbox is roughly at (30, center_y) inside the widget
            click_x = box["x"] + min(30, box["width"] * 0.15)
            click_y = box["y"] + box["height"] / 2

            logger.info(
                "Clicking Turnstile checkbox at (%.0f, %.0f) via selector: %s",
                click_x, click_y, selector,
            )

            # Human-like: move then click with slight randomness
            await human_delay(300, 800)
            await page.mouse.move(click_x + secrets.randbelow(5), click_y + secrets.randbelow(3))
            await human_delay(100, 300)
            await page.mouse.click(click_x, click_y)
            return True
        except Exception as exc:
            logger.debug("Turnstile click failed for %s: %s", selector, exc)
            continue

    # Fallback: try clicking inside the anti-bot dialog directly
    # (some implementations render the checkbox outside an iframe)
    try:
        checkbox = await page.query_selector(
            'input[type="checkbox"], .cf-turnstile input, '
            '#turnstile-wrapper input'
        )
        if checkbox and await checkbox.is_visible():
            logger.info("Clicking Turnstile checkbox element directly")
            await human_delay(300, 800)
            await checkbox.click()
            return True
    except Exception:
        pass

    return False


async def _wait_for_cloudflare(
    page: Page,
    query: str,
    timeout_s: int | None = None,
) -> bool:
    """Wait for a Cloudflare challenge to be solved.

    First attempts to auto-click the Turnstile checkbox. If that
    doesn't resolve it, sends an ntfy notification and polls until
    the challenge is gone or the timeout is reached.

    Returns True if challenge was solved, False on timeout.
    """
    timeout = timeout_s or KEEPA_CONFIG.captcha_timeout_s
    logger.warning("Cloudflare challenge detected for query: %s", query)

    # Attempt auto-click before notifying for human help
    await human_delay(1_000, 2_000)
    clicked = await _try_click_turnstile(page)
    if clicked:
        # Wait a few seconds for Turnstile to validate the click
        await human_delay(3_000, 5_000)
        if not await _detect_cloudflare(page):
            logger.info("Cloudflare challenge auto-solved via checkbox click")
            return True
        logger.info("Auto-click did not resolve challenge, waiting for human")

    _notify_captcha(query)

    elapsed = 0
    poll_interval = 3
    click_retry_interval = 15
    last_click_attempt = 0
    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        if not await _detect_cloudflare(page):
            logger.info("Cloudflare challenge solved after %ds", elapsed)
            return True
        # Retry clicking periodically (widget may re-render)
        if elapsed - last_click_attempt >= click_retry_interval:
            last_click_attempt = elapsed
            await _try_click_turnstile(page)

    logger.error(
        "Cloudflare challenge timeout after %ds for query: %s",
        timeout, query,
    )
    return False


_SEARCH_RESULT_SELECTORS: tuple[str, ...] = (
    ".ag-row",
    ".ag-row-first",
    'div[role="row"]',
    'div[role="gridcell"]',
    "#searchResultTable",
)


async def _wait_for_search_results(page: Page) -> bool:
    """Wait for Keepa search results to appear on page."""
    for selector in _SEARCH_RESULT_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=5_000)
            logger.info("Search results found with selector: %s", selector)
            return True
        except Exception:
            continue
    return False


async def scrape_keepa(
    set_number: str,
    *,
    headless: bool | None = None,
    page: Page | None = None,
) -> KeepaScrapeResult:
    """Scrape Keepa price history for a LEGO set.

    Flow:
    1. Launch browser with persistent keepa profile (or reuse page)
    2. Navigate directly to Keepa search URL
    3. Handle Cloudflare challenge if present
    4. Log in if needed
    5. Click first matching result
    6. Enable all chart legend series
    7. Set date range to 'All'
    8. Sweep chart tooltips for historical data

    Args:
        set_number: LEGO set number (e.g. "60305")
        headless: Override headless setting
        page: Reuse an existing Playwright page (for persistent browser).

    Returns:
        KeepaScrapeResult with parsed product data or error
    """
    await KEEPA_RATE_LIMITER.acquire()

    if page is not None:
        return await scrape_with_page(page, set_number)

    try:
        async with _keepa_browser() as browser:
            page = await browser.new_page()
            return await scrape_with_page(page, set_number)

    except Exception as exc:
        logger.exception("Keepa scrape failed for set: %s", set_number)
        return KeepaScrapeResult(
            success=False,
            set_number=set_number,
            error=str(exc),
        )


async def scrape_with_page(
    page: Page,
    set_number: str,
) -> KeepaScrapeResult:
    """Core Keepa scraping logic operating on an existing page."""
    try:
        search_url = f"{KEEPA_BASE}/#!search/1-{set_number}%20lego"
        logger.info("Navigating to search: %s", search_url)
        await page.goto(search_url, wait_until="domcontentloaded")
        await human_delay(3_000, 5_000)

        # Handle Cloudflare challenge
        if await _detect_cloudflare(page):
            _record_cf_challenge(set_number)
            solved = await _wait_for_cloudflare(page, set_number)
            if not solved:
                return KeepaScrapeResult(
                    success=False,
                    set_number=set_number,
                    error="Cloudflare challenge not solved within timeout",
                )
            # Retry search URL after Cloudflare
            await page.goto(search_url, wait_until="domcontentloaded")
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
            # Navigate back to search after login
            await page.goto(search_url, wait_until="domcontentloaded")
            await human_delay(3_000, 5_000)

        # Handle Cloudflare after login redirect
        if await _detect_cloudflare(page):
            _record_cf_challenge(set_number)
            solved = await _wait_for_cloudflare(page, set_number)
            if not solved:
                return KeepaScrapeResult(
                    success=False,
                    set_number=set_number,
                    error="Cloudflare challenge not solved within timeout",
                )
            await human_delay(3_000, 5_000)

        # Wait for search results
        result_found = await _wait_for_search_results(page)

        if not result_found:
            # Check if CF widget appeared during/after search load
            if await _detect_cloudflare(page):
                _record_cf_challenge(set_number)
                solved = await _wait_for_cloudflare(page, set_number)
                if solved:
                    await page.goto(search_url, wait_until="domcontentloaded")
                    await human_delay(3_000, 5_000)
                    result_found = await _wait_for_search_results(page)

            if not result_found:
                body_text = await page.evaluate(
                    "() => document.body.innerText.substring(0, 500)"
                )
                logger.warning(
                    "No search result selectors matched. Page text: %s",
                    body_text[:200],
                )
                return KeepaScrapeResult(
                    success=False,
                    set_number=set_number,
                    error="Search results did not load within timeout",
                )

        await human_delay(1_000, 2_000)

        # Click first matching result
        clicked = await _click_first_result(page, set_number)
        if not clicked:
            return KeepaScrapeResult(
                success=False,
                set_number=set_number,
                error=f"No search results found for {set_number}",
            )

        await human_delay(5_000, 8_000)

        # Enable all chart legend series before sweeping
        await _enable_all_legend_series(page)
        await human_delay(2_000, 3_000)

        # Click "All" date range to load full history
        await click_all_date_range(page)
        await human_delay(4_000, 6_000)

        # Extract product data from the DOM statistics tables
        product_data = await extract_product_data(page, set_number)

        # Sweep the chart canvas to extract historical data via tooltips
        raw = await page.evaluate(_EXTRACT_JS_XTICKS)
        x_ticks = raw.get("xTicks", [])
        total_days = raw.get("totalDays")
        chart_points = await _sweep_chart_tooltips(page, x_ticks, total_days)
        if chart_points:
            logger.info(
                "Chart sweep collected %d tooltip readings", len(chart_points)
            )
            product_data = _merge_chart_points(product_data, chart_points)

        logger.info(
            "Keepa scrape for %s: amazon=%d pts, new=%d pts, "
            "buy_box=%d pts, sales_rank=%d pts, "
            "rating=%s, reviews=%s, tracking=%s",
            set_number,
            len(product_data.amazon_price),
            len(product_data.new_price),
            len(product_data.buy_box),
            len(product_data.sales_rank),
            product_data.rating,
            product_data.review_count,
            product_data.tracking_users,
        )

        _record_cf_clear()
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


_EXTRACT_JS_XTICKS = """() => {
    const xTicks = [];
    const tickLabels = document.querySelectorAll('.tickLabel');
    for (const el of tickLabels) {
        const text = (el.textContent || '').trim();
        const rect = el.getBoundingClientRect();
        const m = text.match(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+(\\d{4})/);
        if (m) {
            xTicks.push({
                text: text,
                x: Math.round(rect.x + rect.width / 2),
                month: m[1],
                year: parseInt(m[2], 10),
            });
        }
    }
    // Extract "All (1915 days)" for date range calculation
    let totalDays = null;
    const rangeCells = document.querySelectorAll('td.legendRange');
    for (const c of rangeCells) {
        const t = c.textContent.trim();
        const daysMatch = t.match(/All\\s*\\((\\d+)\\s*days?\\)/);
        if (daysMatch) {
            totalDays = parseInt(daysMatch[1], 10);
            break;
        }
    }
    return { xTicks, totalDays };
}"""


def _infer_year(
    x_pos: int,
    month_str: str,
    day: int,
    x_ticks: list[dict[str, Any]],
    chart_x: float,
    chart_width: float,
    total_days: int | None,
) -> int:
    """Infer the year for a tooltip date.

    Primary method: use totalDays from "All (N days)" to calculate
    the chart start date, then interpolate based on x position.

    Fallback: use x-axis tick labels for interpolation.
    """
    from datetime import timedelta

    months_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    now = datetime.now(tz=timezone.utc)

    # Primary: use totalDays to compute exact date from x position
    if total_days and chart_width > 0:
        chart_start = now - timedelta(days=total_days)
        frac = max(0.0, min(1.0, (x_pos - chart_x) / chart_width))
        interp_date = chart_start + timedelta(days=total_days * frac)
        # The tooltip gives us month+day; use interpolated date for year
        tooltip_month = months_map.get(month_str, 1)
        candidate_year = interp_date.year
        # If the interpolated month is far from tooltip month, adjust
        interp_month = interp_date.month
        if tooltip_month <= 2 and interp_month >= 11:
            candidate_year += 1
        elif tooltip_month >= 11 and interp_month <= 2:
            candidate_year -= 1
        return candidate_year

    # Fallback: use x-axis tick labels
    if x_ticks:
        sorted_ticks = sorted(x_ticks, key=lambda t: t["x"])

        for i in range(len(sorted_ticks) - 1):
            if sorted_ticks[i]["x"] <= x_pos <= sorted_ticks[i + 1]["x"]:
                t1 = sorted_ticks[i]
                t2 = sorted_ticks[i + 1]
                y1 = t1["year"] + (months_map.get(t1["month"], 1) - 1) / 12
                y2 = t2["year"] + (months_map.get(t2["month"], 1) - 1) / 12
                dx = t2["x"] - t1["x"]
                if dx == 0:
                    return t1["year"]
                frac = (x_pos - t1["x"]) / dx
                interp_year = y1 + frac * (y2 - y1)
                candidate_year = int(interp_year)
                tooltip_month = months_map.get(month_str, 6)
                if interp_year - candidate_year > 0.9 and tooltip_month <= 2:
                    candidate_year += 1
                return candidate_year

        if x_pos <= sorted_ticks[0]["x"]:
            return sorted_ticks[0]["year"]
        return sorted_ticks[-1]["year"]

    return now.year



async def _enable_all_legend_series(page: Page) -> None:
    """Enable all price series in the Keepa chart legend.

    Keepa legend: each series is a <tr> with a .legendColorBox <td>
    containing a .legendColorBoxCircle <div>, and a .legendLabel <td>.

    Enabled series have a thick colored border (border:6px solid <color>).
    Disabled series have a thin gray border (border:1px solid #ccc).
    Clicking a disabled TR toggles it on.
    """
    try:
        toggled = await page.evaluate("""() => {
            const toggled = [];
            const labels = document.querySelectorAll('td.legendLabel');
            for (const label of labels) {
                if (!label.offsetParent) continue;
                const tr = label.closest('tr');
                if (!tr) continue;
                const circle = tr.querySelector('.legendColorBoxCircle');
                if (!circle) continue;
                // Disabled series: border is "1px solid #ccc" (thin gray)
                const border = circle.style.border || '';
                if (border.includes('1px') && border.includes('#ccc')) {
                    tr.click();
                    toggled.push(label.textContent.trim());
                }
            }
            return toggled;
        }""")

        if toggled:
            logger.info("Enabled %d legend series: %s", len(toggled), toggled)
        else:
            logger.debug("All legend series already enabled")
    except Exception:
        logger.debug("Could not toggle legend series")


async def _sweep_chart_tooltips(
    page: Page,
    x_ticks: list[dict[str, Any]] | None = None,
    total_days: int | None = None,
) -> list[dict[str, Any]]:
    """Sweep the mouse across the chart canvas to collect tooltip data.

    Uses totalDays from "All (N days)" and x-axis tick labels to infer
    the year for each tooltip date (Keepa tooltips show "Sat, Sep 25 4:15"
    without year).

    Returns a list of dicts with 'date', 'label', 'price' keys.
    """
    ticks = x_ticks or []
    months_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    try:
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
            "Sweeping chart canvas: x=%.0f y=%.0f w=%.0f h=%.0f (%d x-ticks)",
            chart_box["x"], chart_box["y"],
            chart_box["width"], chart_box["height"],
            len(ticks),
        )

        chart_x = chart_box["x"]
        chart_y_mid = chart_box["y"] + chart_box["height"] * 0.4
        chart_width = chart_box["width"]

        step_size = 2  # pixels per step

        # Sweep the entire chart in a single JS call.  Dispatch
        # synthetic mousemove events from JS, read the tooltip after
        # each move, and collect only when the tooltip text changes.
        # Move exactly 1 step per animation frame so the chart has
        # time to update tooltips between moves.
        # Timeout prevents hang if requestAnimationFrame stops firing
        # (e.g. tab backgrounded, browser frozen).
        raw_tooltips: list[dict[str, Any]] = await asyncio.wait_for(
            page.evaluate(
                """([chartX, yMid, chartWidth, step]) => {
                return new Promise(resolve => {
                    const results = [];
                    const numSteps = Math.floor(chartWidth / step);
                    let lastText = '';
                    let i = 0;

                    function readTooltip() {
                        const date = document.getElementById('flotTipDate');
                        if (!date || date.style.display === 'none') return null;
                        const dateText = date.textContent.trim();
                        if (!dateText) return null;
                        const parts = [dateText];
                        const tips = document.querySelectorAll('.flotTip');
                        for (const tip of tips) {
                            if (tip.id === 'flotTipDate') continue;
                            if (tip.style.display === 'none') continue;
                            const text = tip.textContent.trim();
                            if (text && text.includes('$')) parts.push(text);
                        }
                        return parts.length > 1 ? parts.join('') : null;
                    }

                    function tick() {
                        if (i >= numSteps) { resolve(results); return; }
                        const x = chartX + step * i;
                        const target = document.elementFromPoint(x, yMid);
                        if (target) {
                            target.dispatchEvent(new MouseEvent('mousemove', {
                                clientX: x, clientY: yMid,
                                bubbles: true, cancelable: true,
                            }));
                        }
                        const text = readTooltip();
                        if (text && text !== lastText) {
                            results.push({step: i, x: Math.round(x), text: text});
                            lastText = text;
                        }
                        i++;
                        requestAnimationFrame(tick);
                    }
                    requestAnimationFrame(tick);
                });
                }""",
                [chart_x, chart_y_mid, chart_width, step_size],
            ),
            timeout=120,
        )

        points: list[dict[str, Any]] = []
        # Track which labels have appeared at least once during the sweep.
        # If a label was present before but is missing from a later tooltip,
        # it means that series is out of stock at that date — emit -1.
        seen_labels: set[str] = set()

        for item in raw_tooltips:
            tooltip = item.get("text", "")
            if not tooltip:
                continue

            # Parse: "Sat, Sep 25 4:15Amazon$ 24.99..."
            date_match = re.search(
                r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+"
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
                r"(\d{1,2})\s+\d{1,2}:\d{2}",
                tooltip,
            )

            if date_match:
                month_str = date_match.group(1)
                day = int(date_match.group(2))
                year = _infer_year(
                    item["x"], month_str, day, ticks,
                    chart_x, chart_width, total_days,
                )
                month_num = months_map.get(month_str, 1)
                date_iso = f"{year:04d}-{month_num:02d}-{day:02d}"
            else:
                date_iso = f"step_{item['step']}"

            search_text = tooltip[date_match.end():] if date_match else tooltip

            # Match prices: "Amazon$ 24.99" or "Amazon $ 24.99"
            price_matches = re.findall(
                r"(Amazon|New, 3rd Party FBA|New, 3rd Party FBM|"
                r"New|Buy Box|Used, like new|Used|"
                r"Warehouse Deals|Collectible|List Price)"
                r"[:\s]*\$\s*([\d,.]+)",
                search_text,
            )

            present_labels: set[str] = set()
            for label, price in price_matches:
                label = label.strip()
                present_labels.add(label)
                seen_labels.add(label)
                points.append({
                    "date": date_iso,
                    "label": label,
                    "price": price.strip(),
                })

            # Any label we've seen before but is missing now = OOS at this date
            for label in seen_labels - present_labels:
                points.append({
                    "date": date_iso,
                    "label": label,
                    "price": None,
                })

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

        raw_price = point["price"]
        if raw_price is None:
            cents = None
        else:
            try:
                cents = int(float(raw_price.replace(",", "")) * 100)
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
        rating=product_data.rating,
        review_count=product_data.review_count,
        tracking_users=product_data.tracking_users,
        chart_screenshot_path=product_data.chart_screenshot_path,
    )


def scrape_keepa_sync(
    set_number: str,
    *,
    headless: bool | None = None,
) -> KeepaScrapeResult:
    """Synchronous wrapper for scrape_keepa."""
    return asyncio.run(scrape_keepa(set_number, headless=headless))
