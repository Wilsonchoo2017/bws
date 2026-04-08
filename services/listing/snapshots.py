"""Listing automation diagnostic snapshots.

Captures screenshot, full page HTML, and metadata JSON at each step
of the Shopee product creation flow. Used for R&D and debugging.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger("bws.listing.snapshots")

LISTING_DEBUG_DIR = Path.home() / ".bws" / "listing-debug"


async def capture_listing_snapshot(
    page: Page,
    step: str,
    *,
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """Capture a full diagnostic snapshot of the current page state.

    Saves screenshot, full HTML, and metadata to a timestamped directory
    under ``~/.bws/listing-debug/``.

    Args:
        page: Playwright page.
        step: Short label for this step (e.g. "add_product_page").
        extra: Arbitrary extra data to include in the metadata JSON.

    Returns:
        Path to the snapshot directory, or None on failure.
    """
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        snap_dir = LISTING_DEBUG_DIR / f"{ts}_{step}"
        snap_dir.mkdir(parents=True, exist_ok=True)

        # Screenshot
        await page.screenshot(
            path=str(snap_dir / "page.png"), full_page=True,
        )

        # Full page HTML
        try:
            html = await page.content()
            (snap_dir / "page.html").write_text(html, encoding="utf-8")
        except Exception:
            pass

        # Collect page metadata
        title = ""
        url = ""
        try:
            title = await page.title()
            url = page.url
        except Exception:
            pass

        # Visible text snippet
        body_text = ""
        try:
            body_text = await page.evaluate(
                "() => document.body.innerText.substring(0, 3000)"
            )
        except Exception:
            pass

        # All form input values on the page
        form_values: list[dict[str, Any]] = []
        try:
            form_values = await page.evaluate("""() => {
                const inputs = document.querySelectorAll(
                    'input, textarea, select'
                );
                return Array.from(inputs).slice(0, 50).map(el => {
                    const r = el.getBoundingClientRect();
                    return {
                        tag: el.tagName,
                        type: el.type || '',
                        name: el.name || '',
                        id: el.id || '',
                        value: el.value?.substring(0, 200) || '',
                        placeholder: el.placeholder || '',
                        checked: el.checked || false,
                        visible: r.width > 0 && r.height > 0,
                        rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                    };
                });
            }""")
        except Exception:
            pass

        # Toggle/switch states
        toggles: list[dict[str, Any]] = []
        try:
            toggles = await page.evaluate("""() => {
                const switches = document.querySelectorAll(
                    '[class*="switch"], [class*="toggle"], [role="switch"]'
                );
                return Array.from(switches).slice(0, 20).map(el => {
                    const r = el.getBoundingClientRect();
                    const label = el.closest('[class*="shipping"]')
                        ?.querySelector('[class*="title"], [class*="label"]')
                        ?.textContent?.trim() || '';
                    return {
                        className: el.className?.substring(0, 100) || '',
                        checked: el.getAttribute('aria-checked') === 'true'
                            || el.classList.contains('checked')
                            || el.classList.contains('active'),
                        label: label.substring(0, 80),
                        rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                    };
                });
            }""")
        except Exception:
            pass

        record = {
            "timestamp": ts,
            "step": step,
            "page_url": url,
            "page_title": title,
            "body_text_snippet": body_text[:1000],
            "form_inputs": form_values,
            "toggles": toggles,
            "extra": extra or {},
        }

        (snap_dir / "diagnostics.json").write_text(
            json.dumps(record, indent=2, default=str), encoding="utf-8",
        )

        logger.info("Listing snapshot captured: %s (%s)", step, snap_dir)
        return snap_dir

    except Exception as exc:
        logger.warning("Failed to capture listing snapshot '%s': %s", step, exc)
        return None
