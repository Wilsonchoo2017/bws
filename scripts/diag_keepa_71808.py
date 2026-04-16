"""Diagnose why the Keepa scraper misses set 71808.

Launches Camoufox with the same persistent profile the scraper uses,
navigates to three Keepa URLs, and for each one:
  1. Screenshots the page
  2. Dumps all ag-grid row titles (what _get_search_candidates() would see)

URLs tested:
  A. search with number-first query (what the scraper currently uses)
  B. search with lego-first query (what the user typed manually)
  C. direct product page for the known-good ASIN B0CGY44HYD

Run with:
    python scripts/diag_keepa_71808.py

Runs NON-headless by default so you can watch and solve any CF/login
challenges. Pass --headless to re-run in headless mode and compare.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logging.getLogger("camoufox").setLevel(logging.WARNING)

from camoufox.async_api import AsyncCamoufox

from config.settings import KEEPA_CONFIG
from services.browser import human_delay
from services.keepa.auth import is_logged_in, login
from services.keepa.scraper import _detect_cloudflare

logger = logging.getLogger("diag_71808")

OUT_DIR = Path("/tmp/keepa-diag-71808")
OUT_DIR.mkdir(parents=True, exist_ok=True)

parser = argparse.ArgumentParser()
parser.add_argument("--headless", action="store_true", help="Run in headless mode (like the real scraper)")
args = parser.parse_args()
HEADLESS = args.headless
MODE_TAG = "headless" if HEADLESS else "headful"

KEEPA_BASE = "https://keepa.com"

URLS = [
    ("A_number_first", f"{KEEPA_BASE}/#!search/1-71808%20lego"),
    ("B_lego_first",   f"{KEEPA_BASE}/#!search/1-lego%2071808"),
    ("C_product",      f"{KEEPA_BASE}/#!product/1-B0CGY44HYD"),
]


async def dump_search_rows(page) -> list[dict]:
    """Return the same ag-grid rows that _get_search_candidates() would see."""
    try:
        return await page.evaluate(
            """() => {
                const rows = document.querySelectorAll('.ag-row, div[role="row"]');
                const out = [];
                for (const row of rows) {
                    const link = row.querySelector('a');
                    if (!link) continue;
                    const title = (link.textContent || '').trim();
                    if (!title) continue;
                    out.push({
                        title,
                        rowIndex: parseInt(
                            row.getAttribute('row-index')
                            || row.getAttribute('aria-rowindex')
                            || '999',
                            10,
                        ),
                    });
                }
                return out;
            }""",
        )
    except Exception as exc:
        logger.warning("dump_search_rows failed: %s", exc)
        return []


async def main() -> None:
    user_data_path = Path(KEEPA_CONFIG.user_data_dir).expanduser()
    user_data_path.mkdir(parents=True, exist_ok=True)

    from services.browser import _clear_stale_profile_lock
    _clear_stale_profile_lock(user_data_path)

    logger.info("Launching Camoufox (headless=%s) with profile=%s", HEADLESS, user_data_path)

    async with AsyncCamoufox(
        headless=HEADLESS,
        geoip=True,
        locale=KEEPA_CONFIG.locale,
        os="macos",
        humanize=True,
        persistent_context=True,
        user_data_dir=str(user_data_path),
        window=(KEEPA_CONFIG.viewport_width, KEEPA_CONFIG.viewport_height),
    ) as browser:
        page = await browser.new_page()

        # Prime the page with a baseline nav so we can check CF / login once.
        logger.info("Initial navigation: %s", KEEPA_BASE)
        await page.goto(KEEPA_BASE, wait_until="domcontentloaded")
        await human_delay(3_000, 5_000)

        if await _detect_cloudflare(page):
            logger.warning(
                "Cloudflare challenge detected on initial load — solve it manually in the browser window; diag waits 60s."
            )
            await asyncio.sleep(60)

        logged_in = await is_logged_in(page)
        logger.info("Login state after initial load: logged_in=%s", logged_in)
        if not logged_in:
            logger.info("Attempting programmatic login...")
            ok = await login(page)
            logger.info("Login result: %s", ok)

        for label, url in URLS:
            logger.info("=== %s: %s ===", label, url)
            await page.goto(url, wait_until="domcontentloaded")
            await human_delay(4_000, 7_000)

            if await _detect_cloudflare(page):
                logger.warning("CF on %s — waiting 30s for manual solve", label)
                await asyncio.sleep(30)
                await page.goto(url, wait_until="domcontentloaded")
                await human_delay(4_000, 7_000)

            # Let ag-grid virtual scroll settle
            await asyncio.sleep(5)

            screenshot_path = OUT_DIR / f"{MODE_TAG}_{label}.png"
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                logger.info("Saved screenshot: %s", screenshot_path)
            except Exception as exc:
                logger.warning("Screenshot failed for %s: %s", label, exc)

            if label.startswith("C_"):
                # Product page — dump title + ASIN instead of search rows
                title = await page.evaluate("() => document.title")
                url_now = page.url
                body_text = await page.evaluate(
                    "() => document.body.innerText.substring(0, 800)"
                )
                logger.info(
                    "PRODUCT page title=%r url=%s body_head=%r",
                    title, url_now, body_text[:300],
                )
                continue

            rows = await dump_search_rows(page)
            logger.info("%s: %d rows visible", label, len(rows))
            for i, r in enumerate(rows[:20]):
                logger.info("  [%d] row-index=%s title=%r", i, r.get("rowIndex"), r.get("title"))

            # Also check: does any row contain the literal "71808"?
            hits = [r for r in rows if "71808" in (r.get("title") or "").lower()]
            logger.info("%s: rows containing literal '71808': %d", label, len(hits))
            for h in hits:
                logger.info("  HIT row-index=%s title=%r", h.get("rowIndex"), h.get("title"))

        logger.info("Done. Screenshots in %s", OUT_DIR)
        logger.info("Holding browser open for 15s so you can inspect.")
        await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
