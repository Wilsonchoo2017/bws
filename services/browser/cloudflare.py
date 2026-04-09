"""Shared Cloudflare challenge detection, auto-clicking, and diagnostics.

Extracted from the Keepa scraper so that any scraper (BrickEconomy,
Carousell, etc.) can reuse the same human-like Turnstile solving
and forensic snapshot capture.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import Page

from services.browser.helpers import human_delay

logger = logging.getLogger("bws.browser.cloudflare")

# Diagnostics directory for all CF challenge snapshots
CF_DEBUG_DIR = Path.home() / ".bws" / "cf-debug"

# ---------------------------------------------------------------------------
# Detection constants
# ---------------------------------------------------------------------------

CF_CHALLENGE_TITLES: tuple[str, ...] = (
    "just a moment",
    "attention required",
    "checking your browser",
)

CF_WIDGET_SELECTORS: tuple[str, ...] = (
    'iframe[src*="challenges.cloudflare.com"]',
    'iframe[src*="cloudflare.com/cdn-cgi/challenge"]',
    "#cf-turnstile",
    ".cf-turnstile",
    "#turnstile-wrapper",
)

# DOM selectors that indicate a Cloudflare challenge page
CF_CHALLENGE_SELECTORS: tuple[str, ...] = (
    "#challenge-running",
    "#challenge-stage",
    "#cf-challenge-running",
    ".cf-browser-verification",
    "#turnstile-wrapper",
    "#challenge-form",
)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


async def detect_cloudflare(page: Page) -> bool:
    """Check if the current page is a Cloudflare challenge.

    Uses title-based, DOM selector, and in-page widget detection.
    """
    # Title-based detection
    try:
        title = await page.title()
        if any(cf in title.lower() for cf in CF_CHALLENGE_TITLES):
            return True
    except Exception:
        pass

    # DOM selector detection (challenge page elements)
    try:
        cf_found = await page.evaluate(
            """() => {
                const selectors = %s;
                return selectors.some(s => document.querySelector(s) !== null);
            }"""
            % str(list(CF_CHALLENGE_SELECTORS))
        )
        if cf_found:
            return True
    except Exception:
        pass

    # In-page Turnstile widget (checkbox dialog)
    try:
        for selector in CF_WIDGET_SELECTORS:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                logger.info("Cloudflare Turnstile widget detected: %s", selector)
                return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# Diagnostics capture
# ---------------------------------------------------------------------------


async def capture_cf_diagnostics(
    page: Page,
    label: str,
    *,
    source: str = "",
    query: str = "",
    click_coords: tuple[float, float] | None = None,
    strategy: str = "",
    attempt: int = 0,
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """Capture a full diagnostic snapshot of Cloudflare challenge state.

    Saves a screenshot, page metadata, iframe attributes, visible text,
    and click coordinates to CF_DEBUG_DIR as a timestamped bundle.
    Returns the directory path of the snapshot, or None on failure.

    Args:
        page: Playwright page.
        label: Short label for the snapshot (e.g. "pre_click").
        source: Scraper name (e.g. "keepa", "brickeconomy").
        query: Search query or set number that triggered the challenge.
        click_coords: (x, y) if a click is about to happen / just happened.
        strategy: Name of the clicking strategy used.
        attempt: Attempt number.
        extra: Arbitrary extra data to include in diagnostics JSON.
    """
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        prefix = f"{source}_" if source else ""
        snap_dir = CF_DEBUG_DIR / f"{ts}_{prefix}{label}"
        snap_dir.mkdir(parents=True, exist_ok=True)

        # Screenshot
        screenshot_path = snap_dir / "page.png"
        await page.screenshot(path=str(screenshot_path), full_page=False)

        # Collect page state
        title = ""
        url = ""
        try:
            title = await page.title()
            url = page.url
        except Exception:
            pass

        # Collect all iframe attributes for analysis
        iframe_info: list[dict[str, Any]] = []
        try:
            iframes = await page.query_selector_all("iframe")
            for iframe in iframes:
                attrs: dict[str, Any] = {}
                for attr in ("src", "title", "id", "class", "name", "width", "height"):
                    val = await iframe.get_attribute(attr)
                    if val:
                        attrs[attr] = val
                box = await iframe.bounding_box()
                if box:
                    attrs["bounding_box"] = box
                attrs["visible"] = await iframe.is_visible()
                iframe_info.append(attrs)
        except Exception as exc:
            iframe_info.append({"error": str(exc)})

        # Save full page HTML for post-mortem analysis
        try:
            full_html = await page.content()
            html_path = snap_dir / "page.html"
            html_path.write_text(full_html, encoding="utf-8")
        except Exception:
            pass

        # Visible text snippet (first 2000 chars)
        body_text = ""
        try:
            body_text = await page.evaluate(
                "() => document.body.innerText.substring(0, 2000)"
            )
        except Exception:
            pass

        # Check which CF selectors matched
        matched_selectors: list[str] = []
        for selector in CF_WIDGET_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    matched_selectors.append(selector)
            except Exception:
                pass

        # Turnstile iframe content (if accessible)
        turnstile_inner: dict[str, Any] = {}
        try:
            for sel in (
                'iframe[src*="challenges.cloudflare.com"]',
                'iframe[src*="turnstile"]',
            ):
                iframe_el = await page.query_selector(sel)
                if not iframe_el:
                    continue
                frame = await iframe_el.content_frame()
                if frame:
                    try:
                        inner_html = await frame.evaluate(
                            "() => document.body.innerHTML.substring(0, 3000)"
                        )
                        turnstile_inner["selector"] = sel
                        turnstile_inner["inner_html"] = inner_html
                        cb = await frame.query_selector('input[type="checkbox"]')
                        if cb:
                            turnstile_inner["checkbox_checked"] = await cb.is_checked()
                            turnstile_inner["checkbox_visible"] = await cb.is_visible()
                            cb_box = await cb.bounding_box()
                            if cb_box:
                                turnstile_inner["checkbox_box"] = cb_box
                    except Exception as exc:
                        turnstile_inner["inner_error"] = str(exc)
                    break
        except Exception as exc:
            turnstile_inner["error"] = str(exc)

        # Anti-bot DOM structure
        antibot_dom: dict[str, Any] = {}
        try:
            antibot_dom = await page.evaluate("""() => {
                const result = {};
                const sitekey = document.querySelector('[data-sitekey]');
                if (sitekey) {
                    const r = sitekey.getBoundingClientRect();
                    result.sitekey = {
                        tag: sitekey.tagName,
                        id: sitekey.id,
                        className: sitekey.className,
                        sitekey: sitekey.getAttribute('data-sitekey'),
                        rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                        outerHTML: sitekey.outerHTML.substring(0, 500),
                    };
                }
                const cft = document.querySelector('.cf-turnstile, #cf-turnstile');
                if (cft) {
                    const r = cft.getBoundingClientRect();
                    result.cf_turnstile = {
                        tag: cft.tagName, id: cft.id,
                        className: cft.className,
                        rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                    };
                }
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                result.checkboxes = Array.from(cbs).map(cb => {
                    const r = cb.getBoundingClientRect();
                    return {
                        id: cb.id, name: cb.name, checked: cb.checked,
                        visible: r.width > 0 && r.height > 0,
                        rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                    };
                });
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT
                );
                while (walker.nextNode()) {
                    if (walker.currentNode.textContent.includes('Verify')) {
                        const el = walker.currentNode.parentElement;
                        if (el) {
                            const r = el.getBoundingClientRect();
                            result.verify_text = {
                                tag: el.tagName, className: el.className,
                                text: el.textContent.substring(0, 100),
                                rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                            };
                        }
                        break;
                    }
                }
                return result;
            }""")
        except Exception as exc:
            antibot_dom = {"error": str(exc)}

        # Enumerate all frames (Playwright frame tree can see frames
        # that querySelectorAll("iframe") misses, e.g. cross-origin)
        frame_info: list[dict[str, Any]] = []
        try:
            for frame in page.frames:
                frame_info.append({
                    "url": frame.url,
                    "name": frame.name,
                    "is_main": frame == page.main_frame,
                })
        except Exception:
            pass

        record = {
            "timestamp": ts,
            "label": label,
            "source": source,
            "query": query,
            "attempt": attempt,
            "strategy": strategy,
            "click_coords": (
                {"x": click_coords[0], "y": click_coords[1]}
                if click_coords
                else None
            ),
            "page_url": url,
            "page_title": title,
            "matched_cf_selectors": matched_selectors,
            "iframes": iframe_info,
            "frames": frame_info,
            "turnstile_inner": turnstile_inner or None,
            "antibot_dom": antibot_dom,
            "body_text_snippet": body_text[:500],
            "extra": extra or {},
        }

        record_path = snap_dir / "diagnostics.json"
        record_path.write_text(
            json.dumps(record, indent=2, default=str), encoding="utf-8"
        )

        logger.info("CF diagnostics captured: %s (%s)", label, snap_dir)
        return snap_dir

    except Exception as exc:
        logger.warning("Failed to capture CF diagnostics: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Human-like mouse movement
# ---------------------------------------------------------------------------


async def human_mouse_move(
    page: Page,
    target_x: float,
    target_y: float,
    *,
    start_x: float | None = None,
    start_y: float | None = None,
) -> None:
    """Move mouse to target with a curved, human-like trajectory.

    Simulates natural hand movement with:
    - Bezier-like curve (random control point offset for arc)
    - Variable speed (slower at start/end, faster in middle)
    - Lateral jitter that peaks mid-path
    - Occasional micro-pause (humans hesitate)
    - Slight overshoot + correction on ~30% of movements
    """
    sx = start_x if start_x is not None else target_x + secrets.randbelow(100) - 50
    sy = start_y if start_y is not None else target_y - 50 - secrets.randbelow(60)
    await page.mouse.move(sx, sy)
    await human_delay(50, 150)

    # Random control point for bezier-like curve
    ctrl_x = (sx + target_x) / 2 + secrets.randbelow(40) - 20
    ctrl_y = (sy + target_y) / 2 + secrets.randbelow(30) - 15

    steps = 5 + secrets.randbelow(6)  # 5-10 steps
    for i in range(1, steps + 1):
        t = i / steps
        inv_t = 1 - t
        # Quadratic bezier: B(t) = (1-t)^2*P0 + 2*(1-t)*t*P1 + t^2*P2
        mid_x = inv_t * inv_t * sx + 2 * inv_t * t * ctrl_x + t * t * target_x
        mid_y = inv_t * inv_t * sy + 2 * inv_t * t * ctrl_y + t * t * target_y

        # Jitter: peaks in the middle of the path
        jitter = (1 - abs(t - 0.5) * 2) * 6
        mid_x += secrets.randbelow(max(1, int(jitter * 2 + 1))) - jitter
        mid_y += secrets.randbelow(max(1, int(jitter * 2 + 1))) - jitter

        await page.mouse.move(mid_x, mid_y)

        # Variable speed: slower at start/end, faster in middle
        if t < 0.2 or t > 0.8:
            await human_delay(40, 120)
        else:
            await human_delay(15, 50)

        # Occasional micro-pause (human hesitation, ~15% chance)
        if secrets.randbelow(100) < 15:
            await human_delay(80, 250)

    # ~30% chance of slight overshoot then correction
    if secrets.randbelow(100) < 30:
        overshoot_x = target_x + secrets.randbelow(8) - 2
        overshoot_y = target_y + secrets.randbelow(6) - 1
        await page.mouse.move(overshoot_x, overshoot_y)
        await human_delay(60, 180)

    # Final settle on target with tiny offset
    await page.mouse.move(
        target_x + secrets.randbelow(3) - 1,
        target_y + secrets.randbelow(3) - 1,
    )


async def pre_click_wander(page: Page) -> None:
    """Simulate natural human behavior before clicking the checkbox.

    When a human sees an anti-bot dialog, they don't immediately click
    the checkbox. They read it, maybe move the mouse around, perhaps
    scroll slightly. This adds that natural pre-click behavior.
    """
    viewport = page.viewport_size or {"width": 1366, "height": 768}
    vw, vh = viewport["width"], viewport["height"]

    # Move mouse to a random "reading" position near center of page
    await page.mouse.move(
        vw * 0.3 + secrets.randbelow(int(vw * 0.4)),
        vh * 0.3 + secrets.randbelow(int(vh * 0.3)),
    )
    await human_delay(500, 1500)

    # Maybe do a small scroll (human habit), ~40% chance
    if secrets.randbelow(100) < 40:
        scroll_y = secrets.randbelow(60) - 30
        await page.mouse.wheel(0, scroll_y)
        await human_delay(300, 800)

    # 1-2 additional random mouse movements (reading/scanning)
    wander_count = 1 + secrets.randbelow(2)
    for _ in range(wander_count):
        await page.mouse.move(
            vw * 0.2 + secrets.randbelow(int(vw * 0.6)),
            vh * 0.2 + secrets.randbelow(int(vh * 0.5)),
        )
        await human_delay(200, 700)


async def idle_behavior(page: Page) -> None:
    """Occasional random mouse movement and micro-scroll between actions.

    Called between major page interactions to break up the mechanical
    pattern of navigate -> wait -> click -> wait -> click. Humans
    fidget, glance at different parts of the page, scroll idly.
    Only does something ~50% of the time to keep it unpredictable.
    """
    if secrets.randbelow(100) >= 50:
        return

    viewport = page.viewport_size or {"width": 1366, "height": 768}
    vw, vh = viewport["width"], viewport["height"]

    # Random mouse drift
    await page.mouse.move(
        secrets.randbelow(int(vw * 0.8)) + int(vw * 0.1),
        secrets.randbelow(int(vh * 0.6)) + int(vh * 0.15),
    )
    await human_delay(200, 600)

    # Micro-scroll (~30% within this path)
    if secrets.randbelow(100) < 30:
        await page.mouse.wheel(0, secrets.randbelow(80) - 40)
        await human_delay(150, 400)


# ---------------------------------------------------------------------------
# Generic Turnstile auto-click
# ---------------------------------------------------------------------------


async def _wait_for_turnstile_widget(
    page: Page, *, timeout_s: int = 15
) -> bool:
    """Poll until a Turnstile widget element appears in the DOM.

    The managed challenge page loads Cloudflare JS asynchronously which
    then injects the Turnstile iframe / container. This function polls
    every 500ms for any recognisable widget selector or iframe to appear.

    Returns True if a widget was found, False on timeout.
    """
    all_selectors = (
        *CF_WIDGET_SELECTORS,
        *CF_CHALLENGE_SELECTORS,
        "[data-sitekey]",
        'div[class*="turnstile"]',
    )
    selector_css = ", ".join(all_selectors)

    deadline = time.monotonic() + timeout_s
    poll_s = 0.5
    while time.monotonic() < deadline:
        try:
            found = await page.evaluate(
                "(sel) => !!document.querySelector(sel)", selector_css
            )
            if found:
                elapsed = timeout_s - (deadline - time.monotonic())
                logger.debug("Turnstile widget appeared after %.1fs", elapsed)
                # Give it a beat to fully render
                await human_delay(300, 600)
                return True
        except Exception as exc:
            logger.debug("Turnstile poll evaluate failed: %s", exc)
        await asyncio.sleep(poll_s)

    return False


async def try_click_turnstile(
    page: Page,
    *,
    source: str = "",
    query: str = "",
    attempt: int = 0,
) -> bool:
    """Attempt to click the Cloudflare Turnstile checkbox.

    Uses multiple strategies in order:
    1. Find Turnstile container by common attributes (data-sitekey, cf-turnstile)
    2. Penetrate shadow DOM to locate actual checkbox input
    3. Locate via "Verify you are human" text and click to its left
    4. Find Turnstile iframe and click at checkbox offset

    On first attempt, performs natural pre-click wandering.
    Returns True if a click was attempted, False if no widget found.
    """
    if attempt <= 1:
        await pre_click_wander(page)

    # Wait for Turnstile widget to appear in the DOM.
    # The managed challenge page loads CF JS asynchronously, which then
    # injects the Turnstile iframe/widget. Without this wait, the click
    # strategies find nothing because the widget hasn't rendered yet.
    widget_appeared = await _wait_for_turnstile_widget(page, timeout_s=15)
    if not widget_appeared:
        logger.info("[%s] Turnstile widget did not appear within timeout", source)

    # Strategy 1: Find the Turnstile container by common attributes.
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
                "[%s] Clicking Turnstile container '%s' at (%.0f, %.0f), box=%s",
                source, selector, click_x, click_y, box,
            )

            await capture_cf_diagnostics(
                page, "pre_click",
                source=source, query=query,
                click_coords=(click_x, click_y),
                strategy=f"turnstile_container:{selector}",
                attempt=attempt,
                extra={"widget_box": box},
            )
            await human_delay(400, 1000)
            await human_mouse_move(page, click_x, click_y)
            await human_delay(50, 200)
            await page.mouse.click(
                click_x + secrets.randbelow(5) - 2,
                click_y + secrets.randbelow(3) - 1,
            )
            await human_delay(1_500, 2_500)
            await capture_cf_diagnostics(
                page, "post_click",
                source=source, query=query,
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
                "[%s] Clicking Turnstile shadow DOM checkbox at (%.0f, %.0f), box=%s",
                source, click_x, click_y, shadow_cb_box,
            )
            await capture_cf_diagnostics(
                page, "pre_click",
                source=source, query=query,
                click_coords=(click_x, click_y),
                strategy="shadow_dom_checkbox",
                attempt=attempt,
                extra={"shadow_cb_box": shadow_cb_box},
            )
            await human_delay(400, 1000)
            await human_mouse_move(page, click_x, click_y)
            await human_delay(50, 200)
            await page.mouse.click(
                click_x + secrets.randbelow(3) - 1,
                click_y + secrets.randbelow(3) - 1,
            )
            await human_delay(1_500, 2_500)
            await capture_cf_diagnostics(
                page, "post_click",
                source=source, query=query,
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
                click_x = verify_box["x"] - 20
                click_y = verify_box["y"] + verify_box["height"] / 2

                logger.info(
                    "[%s] Clicking via 'Verify you are human' text offset "
                    "at (%.0f, %.0f), text_box=%s",
                    source, click_x, click_y, verify_box,
                )

                await capture_cf_diagnostics(
                    page, "pre_click",
                    source=source, query=query,
                    click_coords=(click_x, click_y),
                    strategy="verify_text_offset",
                    attempt=attempt,
                    extra={"text_box": verify_box},
                )
                await human_delay(400, 1000)
                await human_mouse_move(page, click_x, click_y)
                await human_delay(50, 200)
                await page.mouse.click(
                    click_x + secrets.randbelow(5) - 2,
                    click_y + secrets.randbelow(3) - 1,
                )
                await human_delay(1_500, 2_500)
                await capture_cf_diagnostics(
                    page, "post_click",
                    source=source, query=query,
                    click_coords=(click_x, click_y),
                    strategy="verify_text_offset",
                    attempt=attempt,
                )
                return True
    except Exception as exc:
        logger.debug("Verify-text strategy failed: %s", exc)

    # Strategy 4: Try iframe-based Turnstile (full-page CF challenge)
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
                                "[%s] Clicking Turnstile checkbox via content_frame "
                                "at (%.0f, %.0f)",
                                source, click_x, click_y,
                            )
                            await human_delay(400, 1000)
                            await human_mouse_move(page, click_x, click_y)
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
                "[%s] Clicking Turnstile iframe bbox at (%.0f, %.0f)",
                source, click_x, click_y,
            )
            await human_delay(400, 1000)
            await human_mouse_move(page, click_x, click_y)
            await human_delay(50, 200)
            await page.mouse.click(
                click_x + secrets.randbelow(5) - 2,
                click_y + secrets.randbelow(5) - 2,
            )
            return True
        except Exception as exc:
            logger.debug("Turnstile iframe click failed for %s: %s", selector, exc)
            continue

    # Strategy 5: Playwright accessibility tree / frame enumeration.
    # Closed shadow DOMs hide elements from querySelectorAll but
    # Playwright's role-based locators use the accessibility tree.
    try:
        cb_locator = page.get_by_role("checkbox")
        if await cb_locator.count() > 0:
            first_cb = cb_locator.first
            cb_box = await first_cb.bounding_box()
            if cb_box:
                click_x = cb_box["x"] + cb_box["width"] / 2
                click_y = cb_box["y"] + cb_box["height"] / 2
                logger.info(
                    "[%s] Clicking via accessibility checkbox at (%.0f, %.0f), "
                    "box=%s",
                    source, click_x, click_y, cb_box,
                )
                await capture_cf_diagnostics(
                    page, "pre_click",
                    source=source, query=query,
                    click_coords=(click_x, click_y),
                    strategy="a11y_checkbox",
                    attempt=attempt,
                    extra={"checkbox_box": cb_box},
                )
                await human_delay(400, 1000)
                await human_mouse_move(page, click_x, click_y)
                await human_delay(50, 200)
                await page.mouse.click(
                    click_x + secrets.randbelow(3) - 1,
                    click_y + secrets.randbelow(3) - 1,
                )
                await human_delay(1_500, 2_500)
                await capture_cf_diagnostics(
                    page, "post_click",
                    source=source, query=query,
                    click_coords=(click_x, click_y),
                    strategy="a11y_checkbox",
                    attempt=attempt,
                )
                return True
    except Exception as exc:
        logger.debug("Accessibility checkbox strategy failed: %s", exc)

    # Strategy 6: Find Turnstile in child frames (Playwright frame tree
    # can enumerate frames that querySelectorAll("iframe") misses).
    try:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                cb = frame.get_by_role("checkbox")
                if await cb.count() > 0:
                    cb_box = await cb.first.bounding_box()
                    if cb_box:
                        click_x = cb_box["x"] + cb_box["width"] / 2
                        click_y = cb_box["y"] + cb_box["height"] / 2
                        logger.info(
                            "[%s] Clicking via child frame checkbox "
                            "at (%.0f, %.0f), box=%s",
                            source, click_x, click_y, cb_box,
                        )
                        await human_delay(400, 1000)
                        await human_mouse_move(page, click_x, click_y)
                        await human_delay(50, 200)
                        await page.mouse.click(
                            click_x + secrets.randbelow(3) - 1,
                            click_y + secrets.randbelow(3) - 1,
                        )
                        await human_delay(1_500, 2_500)
                        return True
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Child frame checkbox strategy failed: %s", exc)

    # Strategy 7: Use Playwright's frame tree to find the Turnstile iframe
    # element. querySelectorAll("iframe") often returns nothing for CF
    # challenge iframes, but Playwright tracks frames internally and
    # frame.frame_element() returns the host <iframe> HTMLElement.
    try:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            if "challenges.cloudflare.com" not in frame.url and "turnstile" not in frame.url:
                continue
            try:
                frame_el = await frame.frame_element()
                box = await frame_el.bounding_box()
                if box and box["width"] > 10 and box["height"] > 10:
                    # Checkbox is at left side, vertically centered
                    click_x = box["x"] + min(28, box["width"] * 0.09)
                    click_y = box["y"] + box["height"] / 2
                    logger.info(
                        "[%s] Clicking Turnstile via frame_element() "
                        "at (%.0f, %.0f), box=%s",
                        source, click_x, click_y, box,
                    )
                    await capture_cf_diagnostics(
                        page, "pre_click",
                        source=source, query=query,
                        click_coords=(click_x, click_y),
                        strategy="frame_element_bbox",
                        attempt=attempt,
                        extra={"iframe_box": box},
                    )
                    await human_delay(400, 1000)
                    await human_mouse_move(page, click_x, click_y)
                    await human_delay(50, 200)
                    await page.mouse.click(
                        click_x + secrets.randbelow(3) - 1,
                        click_y + secrets.randbelow(3) - 1,
                    )
                    await human_delay(1_500, 2_500)
                    await capture_cf_diagnostics(
                        page, "post_click",
                        source=source, query=query,
                        click_coords=(click_x, click_y),
                        strategy="frame_element_bbox",
                        attempt=attempt,
                    )
                    return True
            except Exception as exc:
                logger.debug("frame_element() strategy failed for %s: %s", frame.url[:60], exc)
    except Exception as exc:
        logger.debug("Frame tree enumeration failed: %s", exc)

    # Strategy 8: Coordinate-based fallback for managed challenge pages.
    # When the Turnstile widget is in a closed shadow DOM invisible to all
    # DOM and a11y queries, use visible page text as a positional anchor.
    # On the CF managed challenge page, the Turnstile widget renders BELOW
    # the "Performing security verification" heading text.
    try:
        title = await page.title()
        if any(cf in title.lower() for cf in CF_CHALLENGE_TITLES):
            anchor_box = await page.evaluate("""() => {
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT
                );
                const anchors = [
                    'performing security verification',
                    'checking your browser',
                    'security service',
                ];
                while (walker.nextNode()) {
                    const text = walker.currentNode.textContent.toLowerCase();
                    for (const a of anchors) {
                        if (text.includes(a)) {
                            const el = walker.currentNode.parentElement;
                            if (el) {
                                const r = el.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) {
                                    return {x: r.x, y: r.y, w: r.width, h: r.height};
                                }
                            }
                        }
                    }
                }
                return null;
            }""")

            if anchor_box:
                # The Turnstile widget renders BELOW the heading/description
                # text. The checkbox is ~40px below the "Performing security
                # verification" heading, at the left edge of the content area.
                # Standard layout: heading at y~186, widget at y~210-250,
                # checkbox center at ~(x-127, y+40) relative to anchor.
                click_x = anchor_box["x"] - 127 + secrets.randbelow(6)
                click_y = anchor_box["y"] + 40 + secrets.randbelow(10)

                logger.info(
                    "[%s] Coordinate-based fallback click at (%.0f, %.0f), "
                    "anchor_box=%s",
                    source, click_x, click_y, anchor_box,
                )

                await capture_cf_diagnostics(
                    page, "pre_click",
                    source=source, query=query,
                    click_coords=(click_x, click_y),
                    strategy="coordinate_fallback",
                    attempt=attempt,
                    extra={"anchor_box": anchor_box},
                )
                await human_delay(400, 1000)
                await human_mouse_move(page, click_x, click_y)
                await human_delay(50, 200)
                await page.mouse.click(
                    click_x + secrets.randbelow(3) - 1,
                    click_y + secrets.randbelow(3) - 1,
                )
                await human_delay(1_500, 2_500)
                await capture_cf_diagnostics(
                    page, "post_click",
                    source=source, query=query,
                    click_coords=(click_x, click_y),
                    strategy="coordinate_fallback",
                    attempt=attempt,
                )
                return True
    except Exception as exc:
        logger.debug("Coordinate-based fallback failed: %s", exc)

    # No widget found by any strategy — capture detailed layout info
    layout_extra: dict[str, Any] = {}
    try:
        layout_extra["frame_count"] = len(page.frames)
        layout_extra["frame_urls"] = [f.url for f in page.frames[:10]]
        # Get bounding boxes of all visible block-level elements for debugging
        layout_extra["content_boxes"] = await page.evaluate("""() => {
            const boxes = [];
            const els = document.querySelectorAll('h1,h2,h3,p,div,section,main');
            for (const el of els) {
                const r = el.getBoundingClientRect();
                if (r.width > 10 && r.height > 5) {
                    boxes.push({
                        tag: el.tagName, id: el.id,
                        cls: el.className.substring(0, 60),
                        text: el.textContent.substring(0, 80).trim(),
                        rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                    });
                }
            }
            return boxes.slice(0, 20);
        }""")
    except Exception:
        pass

    await capture_cf_diagnostics(
        page, "no_widget_found",
        source=source, query=query, attempt=attempt,
        extra=layout_extra,
    )
    return False


# ---------------------------------------------------------------------------
# Wait-for-solve loop (auto-click + human fallback)
# ---------------------------------------------------------------------------


async def wait_for_cloudflare(
    page: Page,
    query: str,
    *,
    source: str = "",
    timeout_s: int = 120,
    max_auto_attempts: int = 3,
    notify_fn: Callable[[str], None] | None = None,
) -> bool:
    """Wait for a Cloudflare challenge to be solved.

    First attempts to auto-click the Turnstile checkbox up to
    *max_auto_attempts* times. If that doesn't resolve it, calls
    *notify_fn* (if provided) and polls until the challenge is gone
    or the timeout is reached.

    Returns True if challenge was solved, False on timeout.
    """
    logger.warning("[%s] Cloudflare challenge detected for: %s", source, query)

    # Capture initial challenge state
    await capture_cf_diagnostics(
        page, "challenge_detected", source=source, query=query,
    )

    # Auto-click attempts
    for attempt in range(1, max_auto_attempts + 1):
        await human_delay(800, 1_500)
        clicked = await try_click_turnstile(
            page, source=source, query=query, attempt=attempt,
        )
        if clicked:
            await human_delay(3_000, 5_000)
            if not await detect_cloudflare(page):
                logger.info(
                    "[%s] Cloudflare challenge auto-solved on attempt %d",
                    source, attempt,
                )
                await capture_cf_diagnostics(
                    page, "challenge_auto_solved",
                    source=source, query=query, attempt=attempt,
                )
                return True
            logger.info(
                "[%s] Auto-click attempt %d/%d did not resolve challenge",
                source, attempt, max_auto_attempts,
            )
            await capture_cf_diagnostics(
                page, "click_did_not_resolve",
                source=source, query=query, attempt=attempt,
            )
        else:
            await capture_cf_diagnostics(
                page, "no_widget_found",
                source=source, query=query, attempt=attempt,
            )
            # Widget may not have rendered yet; continue to next
            # attempt after a longer wait rather than giving up.
            await human_delay(2_000, 4_000)

    # Fall back to human intervention
    logger.info("[%s] Auto-click exhausted, notifying for human help", source)
    if notify_fn is not None:
        notify_fn(query)

    elapsed = 0
    poll_interval = 3
    click_retry_interval = 10
    last_click_attempt = 0
    retry_count = 0
    while elapsed < timeout_s:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        if not await detect_cloudflare(page):
            logger.info(
                "[%s] Cloudflare challenge solved after %ds", source, elapsed,
            )
            await capture_cf_diagnostics(
                page, "challenge_human_solved",
                source=source, query=query,
                extra={"elapsed_s": elapsed},
            )
            return True
        # Retry clicking periodically (widget may re-render)
        if elapsed - last_click_attempt >= click_retry_interval:
            last_click_attempt = elapsed
            retry_count += 1
            await try_click_turnstile(
                page, source=source, query=query,
                attempt=max_auto_attempts + retry_count,
            )

    await capture_cf_diagnostics(
        page, "challenge_timeout",
        source=source, query=query,
        extra={"timeout_s": timeout_s},
    )
    logger.error(
        "[%s] Cloudflare challenge timeout after %ds for: %s",
        source, timeout_s, query,
    )
    return False
