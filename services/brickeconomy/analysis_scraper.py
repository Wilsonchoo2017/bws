"""Scrape BrickEconomy analysis pages (years, themes, subthemes).

Uses the existing Camoufox browser infrastructure to navigate to
aggregate analysis pages and extract table data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from config.settings import BRICKECONOMY_CONFIG, BRICKECONOMY_RATE_LIMITER
from services.brickeconomy.analysis_parser import (
    SubthemeGrowth,
    ThemeGrowth,
    YearGrowth,
    parse_subthemes_page,
    parse_themes_page,
    parse_years_page,
)
from services.browser import human_delay, new_page, stealth_browser
from services.browser.cloudflare import (
    capture_cf_diagnostics,
    detect_cloudflare,
    wait_for_cloudflare,
)

logger = logging.getLogger("bws.brickeconomy.analysis_scraper")

ANALYSIS_URLS = {
    "years": f"{BRICKECONOMY_CONFIG.base_url}/analysis-years",
    "themes": f"{BRICKECONOMY_CONFIG.base_url}/analysis-themes",
    "subthemes": f"{BRICKECONOMY_CONFIG.base_url}/analysis-subthemes",
}

DATA_DIR = Path("data/brickeconomy_analysis")


async def _navigate_analysis_page(page, url: str, label: str) -> str | None:
    """Navigate to an analysis page, handling Cloudflare. Returns HTML or None."""
    await BRICKECONOMY_RATE_LIMITER.acquire()

    logger.info("Navigating to %s (%s)", url, label)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception:
        logger.warning("Navigation timeout for %s", label)
        return None

    await human_delay(2_000, 4_000)

    if await detect_cloudflare(page):
        await capture_cf_diagnostics(
            page, "challenge_detected",
            source="brickeconomy", query=label,
        )
        solved = await wait_for_cloudflare(
            page, label,
            source="brickeconomy",
            timeout_s=BRICKECONOMY_CONFIG.captcha_timeout_s,
            max_auto_attempts=3,
        )
        if not solved:
            logger.error("Cloudflare not solved for %s", label)
            return None
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            logger.warning("Post-CF navigation timeout for %s", label)
            return None
        await human_delay(2_000, 4_000)

    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        logger.debug("networkidle timeout on %s, continuing", label)

    await human_delay(1_000, 2_000)

    html = await page.content()
    title = await page.title()
    logger.info("Loaded %s: title='%s', html_len=%d", label, title, len(html))
    return html


async def scrape_analysis_pages(
    *,
    headless: bool | None = None,
    save_html: bool = True,
) -> dict[str, str]:
    """Scrape all three analysis pages and return their HTML.

    Args:
        headless: Override headless setting.
        save_html: Save raw HTML to data/ for debugging.

    Returns:
        Dict mapping page name -> HTML content.
    """
    if headless is None:
        headless = BRICKECONOMY_CONFIG.headless

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    async with stealth_browser(
        headless=headless,
        locale=BRICKECONOMY_CONFIG.locale,
        profile_name="brickeconomy",
    ) as browser:
        page = await new_page(browser)

        for name, url in ANALYSIS_URLS.items():
            html = await _navigate_analysis_page(page, url, name)
            if html:
                results[name] = html
                if save_html:
                    html_path = DATA_DIR / f"{name}.html"
                    html_path.write_text(html, encoding="utf-8")
                    logger.info("Saved HTML to %s", html_path)

            # Delay between pages
            if name != list(ANALYSIS_URLS.keys())[-1]:
                await human_delay(
                    BRICKECONOMY_CONFIG.min_delay_ms,
                    BRICKECONOMY_CONFIG.max_delay_ms,
                )

    return results


def parse_and_save(
    html_dict: dict[str, str] | None = None,
    *,
    load_from_disk: bool = False,
) -> dict[str, list]:
    """Parse analysis pages and save structured JSON.

    Args:
        html_dict: Dict of page name -> HTML. If None, loads from disk.
        load_from_disk: Load HTML from data/ directory.

    Returns:
        Dict mapping page name -> list of parsed records.
    """
    if html_dict is None or load_from_disk:
        html_dict = {}
        for name in ANALYSIS_URLS:
            html_path = DATA_DIR / f"{name}.html"
            if html_path.exists():
                html_dict[name] = html_path.read_text(encoding="utf-8")
                logger.info("Loaded %s from %s", name, html_path)

    parsed: dict[str, list] = {}

    if "years" in html_dict:
        years = parse_years_page(html_dict["years"])
        parsed["years"] = years
        _save_json("years", [asdict(y) for y in years])

    if "themes" in html_dict:
        themes = parse_themes_page(html_dict["themes"])
        parsed["themes"] = themes
        _save_json("themes", [asdict(t) for t in themes])

    if "subthemes" in html_dict:
        subthemes = parse_subthemes_page(html_dict["subthemes"])
        parsed["subthemes"] = subthemes
        _save_json("subthemes", [asdict(s) for s in subthemes])

    return parsed


def _save_json(name: str, records: list[dict]) -> None:
    """Save parsed records to JSON with metadata."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "data": records,
    }
    path = DATA_DIR / f"{name}.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Saved %d %s records to %s", len(records), name, path)


def load_analysis_data() -> dict[str, list[dict]]:
    """Load previously scraped analysis data from JSON files.

    Returns:
        Dict mapping page name -> list of record dicts.
    """
    result: dict[str, list[dict]] = {}
    for name in ("years", "themes", "subthemes"):
        path = DATA_DIR / f"{name}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            result[name] = data.get("data", [])
            logger.info("Loaded %d %s records from %s", len(result[name]), name, path)
    return result


async def run_scrape_and_parse(*, headless: bool | None = None) -> dict[str, list]:
    """Full pipeline: scrape pages, parse tables, save JSON."""
    html_dict = await scrape_analysis_pages(headless=headless)
    return parse_and_save(html_dict)


def run_sync(*, headless: bool | None = None) -> dict[str, list]:
    """Synchronous wrapper for run_scrape_and_parse."""
    return asyncio.run(run_scrape_and_parse(headless=headless))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    result = run_sync(headless=False)
    for name, records in result.items():
        print(f"{name}: {len(records)} records")
        if records:
            print(f"  sample: {records[0]}")
