"""Keepa executor -- browser-based, uses PersistentBrowser."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from services.scrape_queue.models import ExecutorResult

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.executor.keepa")


def _lookup_item_title(conn: DuckDBPyConnection, set_number: str) -> str | None:
    """Look up the item title from bricklink_items for search verification."""
    try:
        row = conn.execute(
            "SELECT title FROM bricklink_items WHERE item_id = ?",
            [set_number],
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def execute_keepa(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape Keepa for Amazon price history."""
    from config.settings import KEEPA_CONFIG
    from services.browser import BrowserConfig, get_persistent_browser
    from services.keepa.repository import record_keepa_prices, save_keepa_snapshot
    from services.keepa.scheduler import record_keepa_failure, record_keepa_success
    from services.keepa.scraper import scrape_with_page

    item_title = _lookup_item_title(conn, set_number)

    browser = get_persistent_browser(BrowserConfig(
        profile_name=f"keepa-{worker_index}",
        headless=KEEPA_CONFIG.headless,
        locale=KEEPA_CONFIG.locale,
        window=(KEEPA_CONFIG.viewport_width, KEEPA_CONFIG.viewport_height),
    ))

    try:
        result = browser.run(scrape_with_page, set_number, item_title)
    except Exception as exc:
        record_keepa_failure(set_number)
        browser.restart()
        return ExecutorResult.fail(str(exc))

    if not result.success:
        record_keepa_failure(set_number)
        # Don't restart browser for "not listed" -- browser is fine
        if result.error and "not listed" not in result.error.lower():
            browser.restart()
        return ExecutorResult.fail(result.error or "Keepa scrape failed")

    record_keepa_success(set_number)
    try:
        save_keepa_snapshot(conn, result.product_data)
    except Exception:
        logger.error("Keepa snapshot insert failed for %s", set_number, exc_info=True)
        return ExecutorResult.fail("Failed to save Keepa snapshot")
    record_keepa_prices(conn, result.product_data)

    logger.info("Keepa for %s: OK", set_number)
    return ExecutorResult.ok()
