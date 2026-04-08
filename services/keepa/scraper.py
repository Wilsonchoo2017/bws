"""Keepa price history scraper with Cloudflare and login handling.

Uses Playwright + Camoufox to load Keepa, bypass Cloudflare,
log in, search for a LEGO set, and intercept price history data
from internal API responses.
"""

import asyncio
import dataclasses
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
from services.browser.cloudflare import (
    CF_CHALLENGE_TITLES,
    CF_DEBUG_DIR,
    CF_WIDGET_SELECTORS,
    capture_cf_diagnostics as _capture_cf_diagnostics,
    detect_cloudflare as _detect_cloudflare_generic,
    human_mouse_move as _human_mouse_move,
    idle_behavior as _idle_behavior,
    pre_click_wander as _pre_click_wander,
)
from services.keepa.auth import is_logged_in, login
from services.keepa.parser import click_all_date_range, extract_product_data
from services.keepa.types import KeepaDataPoint, KeepaProductData, KeepaScrapeResult

logger = logging.getLogger("bws.keepa.scraper")

KEEPA_BASE = "https://keepa.com"



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




async def _detect_cloudflare(page: Page) -> bool:
    """Check if the current page is a Cloudflare challenge.

    Delegates to the shared detector, then adds Keepa-specific
    anti-bot modal detection (contains Turnstile widget inside a
    custom dialog that may not match standard CF selectors).
    """
    if await _detect_cloudflare_generic(page):
        return True

    # Keepa-specific: in-page anti-bot modal with "anti-bot check" text
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


async def _try_click_keepa_antibot(
    page: Page,
    *,
    query: str = "",
    attempt: int = 0,
) -> bool:
    """Click the checkbox in Keepa's custom anti-bot modal.

    Keepa renders a Cloudflare Turnstile widget inline inside a custom
    modal dialog (not in an iframe). The widget uses a shadow DOM, so
    standard query_selector cannot reach the checkbox input. Instead we
    locate the Turnstile container element (identified by data-sitekey,
    cf-turnstile class, or nearby "Verify you are human" text) and
    click at the known checkbox offset within it.

    Returns True if a click was attempted, False if the modal/widget
    was not found.
    """
    # On first attempt, wander the mouse naturally before targeting
    # the checkbox (humans read the dialog first)
    if attempt <= 1:
        await _pre_click_wander(page)

    # Strategy 1: Find the Turnstile container by common attributes.
    # Cloudflare Turnstile managed mode creates a <div> with
    # data-sitekey or class cf-turnstile containing a shadow root.
    turnstile_selectors = (
        "[data-sitekey]",
        ".cf-turnstile",
        "#cf-turnstile",
        "#turnstile-wrapper",
        'div[class*="turnstile"]',
    )

    for selector in turnstile_selectors:
        try:
            el = await page.query_selector(selector)
            if not el or not await el.is_visible():
                continue

            box = await el.bounding_box()
            if not box:
                continue

            # The checkbox is at the left side of the Turnstile widget,
            # vertically centered. Standard Turnstile widget is ~300x65.
            click_x = box["x"] + min(28, box["width"] * 0.09)
            click_y = box["y"] + box["height"] / 2

            logger.info(
                "Clicking Keepa anti-bot via Turnstile container '%s' "
                "at (%.0f, %.0f), box=%s",
                selector, click_x, click_y, box,
            )

            await _capture_cf_diagnostics(
                page, "pre_click",
                query=query,
                click_coords=(click_x, click_y),
                strategy=f"turnstile_container:{selector}",
                attempt=attempt,
                extra={"widget_box": box},
            )
            await human_delay(400, 1000)
            await _human_mouse_move(page, click_x, click_y)
            await human_delay(50, 200)
            await page.mouse.click(
                click_x + secrets.randbelow(5) - 2,
                click_y + secrets.randbelow(3) - 1,
            )
            await human_delay(1_500, 2_500)
            await _capture_cf_diagnostics(
                page, "post_click",
                query=query,
                click_coords=(click_x, click_y),
                strategy=f"turnstile_container:{selector}",
                attempt=attempt,
            )
            return True
        except Exception as exc:
            logger.debug("Turnstile container click failed for %s: %s", selector, exc)
            continue

    # Strategy 2: Reach into the Turnstile shadow DOM to find the
    # actual checkbox element and its bounding box.
    try:
        shadow_cb_box = await page.evaluate("""() => {
            // Turnstile renders inside a shadow root on a container div.
            // Walk all elements looking for shadow roots that contain
            // an input[type="checkbox"] or a clickable label.
            const containers = document.querySelectorAll(
                '[data-sitekey], .cf-turnstile, #cf-turnstile, '
                + '#turnstile-wrapper, div[class*="turnstile"]'
            );
            for (const c of containers) {
                if (c.shadowRoot) {
                    const cb = c.shadowRoot.querySelector(
                        'input[type="checkbox"], .ctp-checkbox-label, '
                        + 'label, [role="checkbox"]'
                    );
                    if (cb) {
                        const r = cb.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0)
                            return {x: r.x, y: r.y, w: r.width, h: r.height};
                    }
                }
            }
            // Fallback: walk ALL shadow roots on the page
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.shadowRoot) {
                    const cb = el.shadowRoot.querySelector(
                        'input[type="checkbox"], [role="checkbox"]'
                    );
                    if (cb) {
                        const r = cb.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0)
                            return {x: r.x, y: r.y, w: r.width, h: r.height};
                    }
                }
            }
            return null;
        }""")
        if shadow_cb_box:
            click_x = shadow_cb_box["x"] + shadow_cb_box["w"] / 2
            click_y = shadow_cb_box["y"] + shadow_cb_box["h"] / 2
            logger.info(
                "Clicking Keepa anti-bot via shadow DOM checkbox "
                "at (%.0f, %.0f), box=%s", click_x, click_y, shadow_cb_box,
            )
            await _capture_cf_diagnostics(
                page, "pre_click",
                query=query,
                click_coords=(click_x, click_y),
                strategy="shadow_dom_checkbox",
                attempt=attempt,
                extra={"shadow_cb_box": shadow_cb_box},
            )
            await human_delay(400, 1000)
            await _human_mouse_move(page, click_x, click_y)
            await human_delay(50, 200)
            await page.mouse.click(
                click_x + secrets.randbelow(3) - 1,
                click_y + secrets.randbelow(3) - 1,
            )
            await human_delay(1_500, 2_500)
            await _capture_cf_diagnostics(
                page, "post_click",
                query=query,
                click_coords=(click_x, click_y),
                strategy="shadow_dom_checkbox",
                attempt=attempt,
            )
            return True
    except Exception as exc:
        logger.debug("Shadow DOM checkbox strategy failed: %s", exc)

    # Strategy 3: Locate via "Verify you are human" text and click
    # to its left where the checkbox is rendered.
    try:
        verify_el = page.get_by_text("Verify you are human", exact=False)
        if await verify_el.count() > 0:
            verify_box = await verify_el.first.bounding_box()
            if verify_box:
                # Checkbox is to the left of the text, same vertical center
                click_x = verify_box["x"] - 20
                click_y = verify_box["y"] + verify_box["height"] / 2

                logger.info(
                    "Clicking Keepa anti-bot via 'Verify you are human' text "
                    "offset at (%.0f, %.0f), text_box=%s",
                    click_x, click_y, verify_box,
                )

                await _capture_cf_diagnostics(
                    page, "pre_click",
                    query=query,
                    click_coords=(click_x, click_y),
                    strategy="verify_text_offset",
                    attempt=attempt,
                    extra={"text_box": verify_box},
                )
                await human_delay(400, 1000)
                await _human_mouse_move(page, click_x, click_y)
                await human_delay(50, 200)
                await page.mouse.click(
                    click_x + secrets.randbelow(5) - 2,
                    click_y + secrets.randbelow(3) - 1,
                )
                await human_delay(1_500, 2_500)
                await _capture_cf_diagnostics(
                    page, "post_click",
                    query=query,
                    click_coords=(click_x, click_y),
                    strategy="verify_text_offset",
                    attempt=attempt,
                )
                return True
    except Exception as exc:
        logger.debug("Verify-text strategy failed: %s", exc)

    # Strategy 4: Find the anti-bot modal dialog and click at the
    # known checkbox position within it. The modal is a centered
    # white dialog ~300px wide with the checkbox near top-left.
    try:
        # Look for the modal by its heading text
        antibot_heading = page.get_by_text("Anti-bot check", exact=False)
        if await antibot_heading.count() > 0:
            heading_box = await antibot_heading.first.bounding_box()
            if heading_box:
                # From screenshot analysis:
                # - Heading top: ~287, height: ~20, bottom: ~307
                # - Bordered widget box starts ~325 (18px gap)
                # - Checkbox center: ~355 (48px below heading bottom)
                # Offset from heading_y: height + 48 = ~68
                click_x = heading_box["x"] + 18
                click_y = heading_box["y"] + heading_box["height"] + 48

                logger.info(
                    "Clicking Keepa anti-bot via heading offset "
                    "at (%.0f, %.0f), heading_box=%s",
                    click_x, click_y, heading_box,
                )

                await _capture_cf_diagnostics(
                    page, "pre_click",
                    query=query,
                    click_coords=(click_x, click_y),
                    strategy="heading_offset",
                    attempt=attempt,
                    extra={"heading_box": heading_box},
                )
                await human_delay(400, 1000)
                await _human_mouse_move(page, click_x, click_y)
                await human_delay(50, 200)
                await page.mouse.click(
                    click_x + secrets.randbelow(5) - 2,
                    click_y + secrets.randbelow(3) - 1,
                )
                await human_delay(1_500, 2_500)
                await _capture_cf_diagnostics(
                    page, "post_click",
                    query=query,
                    click_coords=(click_x, click_y),
                    strategy="heading_offset",
                    attempt=attempt,
                )
                return True
    except Exception as exc:
        logger.debug("Heading-offset strategy failed: %s", exc)

    # Strategy 5 (legacy): Try iframe-based Turnstile (full-page CF)
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

            frame = await iframe_el.content_frame()
            if frame:
                try:
                    cb = await frame.query_selector(
                        'input[type="checkbox"], .ctp-checkbox-label, '
                        '#challenge-stage input'
                    )
                    if cb:
                        cb_box = await cb.bounding_box()
                        if cb_box:
                            click_x = cb_box["x"] + cb_box["width"] / 2
                            click_y = cb_box["y"] + cb_box["height"] / 2
                            logger.info(
                                "Clicking Turnstile checkbox via content_frame "
                                "at (%.0f, %.0f)", click_x, click_y,
                            )
                            await human_delay(400, 1000)
                            await _human_mouse_move(page, click_x, click_y)
                            await human_delay(50, 200)
                            await page.mouse.click(
                                click_x + secrets.randbelow(3) - 1,
                                click_y + secrets.randbelow(3) - 1,
                            )
                            return True
                except Exception as exc:
                    logger.debug("content_frame checkbox failed: %s", exc)

            box = await iframe_el.bounding_box()
            if not box:
                continue

            click_x = box["x"] + min(30, box["width"] * 0.15)
            click_y = box["y"] + box["height"] / 2
            logger.info(
                "Clicking Turnstile iframe bbox at (%.0f, %.0f)", click_x, click_y,
            )
            await human_delay(400, 1000)
            await _human_mouse_move(page, click_x, click_y)
            await human_delay(50, 200)
            await page.mouse.click(
                click_x + secrets.randbelow(5) - 2,
                click_y + secrets.randbelow(5) - 2,
            )
            return True
        except Exception as exc:
            logger.debug("Turnstile iframe click failed for %s: %s", selector, exc)
            continue

    # No widget found at all
    await _capture_cf_diagnostics(
        page, "no_widget_found",
        query=query,
        attempt=attempt,
    )
    return False


async def _wait_for_cloudflare(
    page: Page,
    query: str,
    timeout_s: int | None = None,
) -> bool:
    """Wait for a Cloudflare challenge to be solved.

    Attempts to auto-click the Turnstile checkbox, then polls until
    the challenge is gone or the timeout is reached.

    Returns True if challenge was solved, False on timeout.
    """
    timeout = timeout_s or KEEPA_CONFIG.captcha_timeout_s
    logger.warning("Cloudflare challenge detected for query: %s", query)

    # Capture initial challenge state
    await _capture_cf_diagnostics(
        page, "challenge_detected", query=query,
    )

    # Try up to 3 rapid auto-click attempts before falling back to human
    max_auto_attempts = 3
    for attempt in range(1, max_auto_attempts + 1):
        await human_delay(800, 1_500)
        clicked = await _try_click_keepa_antibot(
            page, query=query, attempt=attempt,
        )
        if clicked:
            # Wait for Turnstile to validate the click
            await human_delay(3_000, 5_000)
            if not await _detect_cloudflare(page):
                logger.info(
                    "Cloudflare challenge auto-solved on attempt %d", attempt,
                )
                await _capture_cf_diagnostics(
                    page, "challenge_auto_solved",
                    query=query, attempt=attempt,
                )
                return True
            logger.info(
                "Auto-click attempt %d/%d did not resolve challenge",
                attempt, max_auto_attempts,
            )
            await _capture_cf_diagnostics(
                page, "click_did_not_resolve",
                query=query, attempt=attempt,
            )
        else:
            break  # Widget not found, no point retrying

    logger.info("Auto-click exhausted, waiting for challenge resolution")

    elapsed = 0
    poll_interval = 3
    click_retry_interval = 10
    last_click_attempt = 0
    retry_count = 0
    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        if not await _detect_cloudflare(page):
            logger.info("Cloudflare challenge solved after %ds", elapsed)
            await _capture_cf_diagnostics(
                page, "challenge_human_solved",
                query=query,
                extra={"elapsed_s": elapsed},
            )
            return True
        # Retry clicking periodically (widget may re-render after human
        # interaction or page refresh)
        if elapsed - last_click_attempt >= click_retry_interval:
            last_click_attempt = elapsed
            retry_count += 1
            await _try_click_keepa_antibot(
                page, query=query, attempt=max_auto_attempts + retry_count,
            )

    await _capture_cf_diagnostics(
        page, "challenge_timeout",
        query=query,
        extra={"timeout_s": timeout},
    )
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
    item_title: str | None = None,
) -> KeepaScrapeResult:
    """Scrape Keepa price history for a LEGO set.

    Flow:
    1. Launch browser with persistent keepa profile (or reuse page)
    2. Navigate directly to Keepa search URL
    3. Handle Cloudflare challenge if present
    4. Log in if needed
    5. Click first matching result (verify it's by LEGO)
    6. Enable all chart legend series
    7. Set date range to 'All'
    8. Sweep chart tooltips for historical data

    Args:
        set_number: LEGO set number (e.g. "60305")
        headless: Override headless setting
        page: Reuse an existing Playwright page (for persistent browser).
        item_title: Known title from DB for verification (e.g. "Monkie Kid...")

    Returns:
        KeepaScrapeResult with parsed product data or error
    """
    await KEEPA_RATE_LIMITER.acquire()

    if page is not None:
        return await scrape_with_page(page, set_number, item_title)

    try:
        async with _keepa_browser() as browser:
            page = await browser.new_page()
            return await scrape_with_page(page, set_number, item_title)

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
    item_title: str | None = None,
) -> KeepaScrapeResult:
    """Core Keepa scraping logic operating on an existing page."""
    try:
        search_url = f"{KEEPA_BASE}/#!search/1-{set_number}%20lego"
        logger.info("Navigating to search: %s", search_url)
        await page.goto(search_url, wait_until="domcontentloaded")
        await human_delay(2_500, 6_000)

        # Handle Cloudflare challenge
        if await _detect_cloudflare(page):

            solved = await _wait_for_cloudflare(page, set_number)
            if not solved:
                return KeepaScrapeResult(
                    success=False,
                    set_number=set_number,
                    error="Cloudflare challenge not solved within timeout",
                )
            # Retry search URL after Cloudflare
            await page.goto(search_url, wait_until="domcontentloaded")
            await human_delay(2_500, 6_000)

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
            await human_delay(2_500, 6_000)

        # Handle Cloudflare after login redirect
        if await _detect_cloudflare(page):

            solved = await _wait_for_cloudflare(page, set_number)
            if not solved:
                return KeepaScrapeResult(
                    success=False,
                    set_number=set_number,
                    error="Cloudflare challenge not solved within timeout",
                )
            await human_delay(2_500, 6_000)

        # Wait for search results
        result_found = await _wait_for_search_results(page)

        if not result_found:
            # Check if CF widget appeared during/after search load
            if await _detect_cloudflare(page):
    
                solved = await _wait_for_cloudflare(page, set_number)
                if solved:
                    await page.goto(search_url, wait_until="domcontentloaded")
                    await human_delay(2_500, 6_000)
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

        await human_delay(800, 2_500)
        await _idle_behavior(page)

        # Click first matching result (verifies it's a LEGO product)
        clicked = await _click_first_result(page, set_number, item_title)
        if not clicked:
            return KeepaScrapeResult(
                success=False,
                set_number=set_number,
                error=f"Not listed on Amazon (no LEGO product found for {set_number})",
                not_found=True,
            )

        await human_delay(4_000, 9_000)
        await _idle_behavior(page)

        # Enable all chart legend series before sweeping
        await _enable_all_legend_series(page)
        await human_delay(1_500, 4_000)

        # Click "All" date range to load full history
        await click_all_date_range(page)
        await human_delay(3_000, 7_000)
        await _idle_behavior(page)

        # Extract product data from the DOM statistics tables
        product_data = await extract_product_data(page, set_number)

        # Cross-check: verify the Keepa product actually matches our set number.
        # The product title should contain the set number (e.g. "LEGO 60305 ...").
        # Without this, high-number sets like 122222 can match wrong products.
        if not _title_contains_set_number(product_data.title, set_number):
            logger.warning(
                "Keepa product mismatch for %s: title='%s' does not contain set number",
                set_number, product_data.title,
            )
            return KeepaScrapeResult(
                success=False,
                set_number=set_number,
                error=f"Keepa product title mismatch: '{product_data.title}' does not contain {_bare_set_number(set_number)}",
                mismatch=True,
            )

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


_ACCESSORY_KEYWORDS: tuple[str, ...] = (
    "display case",
    "acrylic",
    "storage",
    "carrying case",
    "light kit",
    "lighting kit",
    "led light",
    "dust cover",
    "baseplate",
    "base plate",
    "wall mount",
    "display stand",
    "display box",
    "protective case",
    "compatible with",
    "not included",
    "custom",
    "moc ",
    "alternative",
    "building blocks",
)

_MAX_RESULT_ATTEMPTS: int = 5


def _bare_set_number(set_number: str) -> str:
    """Strip the variant suffix (e.g. '60305-1' -> '60305')."""
    return set_number.split("-")[0]


def _title_contains_set_number(title: str | None, set_number: str) -> bool:
    """Check if a product title contains the bare set number."""
    if not title:
        return False
    return _bare_set_number(set_number) in title.lower()


def _score_result(title: str, set_number: str) -> int:
    """Score a search result title for relevance to the actual LEGO set.

    Higher score = more likely to be the real LEGO product.
    Returns -1 for results that should be excluded (obvious accessories).
    """
    lower = title.lower()

    if any(kw in lower for kw in _ACCESSORY_KEYWORDS):
        return -1

    score = 0

    if _title_contains_set_number(title, set_number):
        score += 30

    if lower.startswith("lego"):
        score += 20

    if "by lego" in lower or "lego group" in lower:
        score += 15

    if any(w in lower for w in ("building set", "building kit", "toy set", "pieces")):
        score += 5

    if "by " in lower and "by lego" not in lower:
        score -= 10

    return score


async def _get_search_candidates(
    page: Page, set_number: str,
) -> list[tuple[dict[str, Any], int]]:
    """Extract and rank search result candidates from the ag-grid.

    Returns a sorted list of (candidate, score) tuples, best first.
    Candidates with score -1 (obvious accessories) are excluded.
    """
    try:
        candidates = await page.evaluate(
            """() => {
                const rows = document.querySelectorAll(
                    '.ag-row, div[role="row"]'
                );
                const results = [];
                for (const row of rows) {
                    const link = row.querySelector('a');
                    if (!link) continue;
                    const title = link.textContent.trim();
                    if (!title) continue;
                    const rowIndex = row.getAttribute('row-index')
                        || row.getAttribute('aria-rowindex')
                        || '999';
                    results.push({
                        title: title,
                        rowIndex: parseInt(rowIndex, 10),
                    });
                }
                return results;
            }""",
        )
    except Exception as exc:
        logger.debug("Failed to extract search candidates: %s", exc)
        return []

    scored = [
        (c, _score_result(c["title"], set_number)) for c in candidates
    ]
    valid = [(c, s) for c, s in scored if s >= 0]
    valid.sort(key=lambda x: (-x[1], x[0]["rowIndex"]))

    skipped = [c["title"][:60] for c, s in scored if s < 0]
    if skipped:
        logger.info(
            "Filtered %d accessory results: %s", len(skipped), skipped,
        )

    return valid


async def _click_candidate(page: Page, title: str) -> bool:
    """Click a specific search result by its exact title text."""
    try:
        return await page.evaluate(
            """(targetTitle) => {
                const rows = document.querySelectorAll(
                    '.ag-row, div[role="row"]'
                );
                for (const row of rows) {
                    const link = row.querySelector('a');
                    if (link && link.textContent.trim() === targetTitle) {
                        link.click();
                        return true;
                    }
                }
                return false;
            }""",
            title,
        )
    except Exception as exc:
        logger.debug("Failed to click candidate '%s': %s", title[:40], exc)
        return False


async def _verify_lego_product(
    page: Page,
    set_number: str,
    item_title: str | None = None,
) -> bool:
    """Check if the current Keepa product page is for the correct LEGO product.

    Inspects the product info box for manufacturer/brand indicators
    and optionally cross-checks against the known item title from DB.
    Returns True if the product appears to be the right LEGO set.
    """
    try:
        info = await page.evaluate("""() => {
            const box = document.querySelector('#productInfoBox');
            if (!box) return { text: '', title: '' };
            const text = box.textContent || '';
            return {
                text: text.substring(0, 2000),
                title: document.title || '',
            };
        }""")

        page_text = info.get("text", "")
        combined = (page_text + " " + info.get("title", "")).lower()

        # Check for third-party brand signals first (fast reject)
        if any(kw in combined for kw in _ACCESSORY_KEYWORDS):
            logger.info("Rejected: accessory keywords in product page")
            return False

        # If "by " is present but not "by lego", it's third-party
        by_match = re.search(r"by\s+([A-Z][\w\s&]+)", page_text)
        if by_match:
            brand = by_match.group(1).strip().lower()
            if "lego" not in brand:
                logger.info(
                    "Rejected: brand is '%s', not LEGO",
                    by_match.group(1).strip(),
                )
                return False

        # Positive signals for LEGO
        is_lego = (
            "by lego" in combined
            or "lego group" in combined
            or page_text.strip().lower().startswith("lego")
        )

        if not is_lego:
            logger.info("Rejected: no LEGO brand signal on product page")
            return False

        # If we have a known title, verify the set number appears on the
        # product page (catches wrong-LEGO-set selections like picking
        # set 76244 when searching for 122220)
        if _bare_set_number(set_number) in combined:
            return True

        # Set number not on page -- cross-check with known title
        if item_title:
            # Check if significant words from the known title appear
            title_words = {
                w.lower()
                for w in item_title.split()
                if len(w) > 3 and w.lower() not in {"lego", "the", "with", "and"}
            }
            if title_words:
                matches = sum(1 for w in title_words if w in combined)
                ratio = matches / len(title_words)
                if ratio >= 0.3:
                    logger.info(
                        "Verified via title match (%.0f%% words): %s",
                        ratio * 100, item_title[:60],
                    )
                    return True
                logger.info(
                    "Rejected: title match too low (%.0f%%): expected '%s'",
                    ratio * 100, item_title[:60],
                )
                return False

        # LEGO product but can't verify it's the right one -- accept
        return True

    except Exception as exc:
        logger.debug("LEGO verification failed: %s", exc)
        return True  # fail-open to avoid breaking the scrape


async def _click_first_result(
    page: Page,
    set_number: str,
    item_title: str | None = None,
) -> bool:
    """Click the best search result that is the correct LEGO product.

    Iterates through scored candidates, clicking each and verifying
    on the product page that it's the right LEGO set. If a result
    turns out to be wrong (third-party accessory or different set),
    navigates back and tries the next candidate.

    When the initial search yields no candidates, retries with a
    title-based query (e.g. "lego Spider-Man's Car and Doc Ock") if
    an item_title is available.
    """
    search_url = page.url

    candidates = await _get_search_candidates(page, set_number)
    if not candidates and item_title:
        # Retry with a title-based search -- helps for DUPLO/toddler sets
        # where the set number alone returns irrelevant results.
        alt_query = f"lego {item_title}"
        alt_url = f"{KEEPA_BASE}/#!search/1-{alt_query}"
        logger.info(
            "No candidates for %s, retrying with title search: %s",
            set_number, alt_query,
        )
        await page.goto(alt_url, wait_until="domcontentloaded")
        await human_delay(3_000, 5_000)
        await _wait_for_search_results(page)
        await human_delay(1_000, 2_000)
        search_url = page.url
        candidates = await _get_search_candidates(page, set_number)
    if not candidates:
        logger.warning("No valid search candidates for %s", set_number)
        return False

    for i, (candidate, score) in enumerate(candidates[:_MAX_RESULT_ATTEMPTS]):
        logger.info(
            "Trying result %d/%d (score=%d): %s",
            i + 1, min(len(candidates), _MAX_RESULT_ATTEMPTS),
            score, candidate["title"][:80],
        )

        clicked = await _click_candidate(page, candidate["title"])
        if not clicked:
            continue

        # Wait for product page to load
        await human_delay(3_000, 5_000)

        # Verify this is the correct LEGO product
        if await _verify_lego_product(page, set_number, item_title):
            logger.info(
                "Verified LEGO product: %s", candidate["title"][:80],
            )
            return True

        # Wrong product -- go back to search results and try next
        logger.info(
            "Wrong product, going back: %s", candidate["title"][:80],
        )
        await page.goto(search_url, wait_until="domcontentloaded")
        await human_delay(2_000, 3_000)

        # Re-wait for search results to reload
        await _wait_for_search_results(page)
        await human_delay(1_000, 2_000)

    logger.warning(
        "Exhausted %d candidates for %s -- not listed on Amazon",
        min(len(candidates), _MAX_RESULT_ATTEMPTS), set_number,
    )
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
                    let resolved = false;

                    function done() {
                        if (resolved) return;
                        resolved = true;
                        resolve(results);
                    }

                    // Safety net: resolve with whatever we have after 30s
                    // in case requestAnimationFrame stops firing.
                    setTimeout(done, 30000);

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
                        if (resolved) return;
                        if (i >= numSteps) { done(); return; }
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
            timeout=45,
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
