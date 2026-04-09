"""Keepa executor -- browser-based, uses PersistentBrowser.

Structured as a pipeline: fetch (IO) -> validate (pure) -> persist (IO).
"""

from __future__ import annotations

import logging

from services.core.result import Err, Ok, Result
from services.scrape_queue.models import ErrorCategory, ExecutorResult, TaskType
from services.scrape_queue.registry import executor
from typing import Any


logger = logging.getLogger("bws.scrape_queue.executor.keepa")


# ---------------------------------------------------------------------------
# Pure: lookup helpers
# ---------------------------------------------------------------------------


def _lookup_item_title(conn: Any, set_number: str) -> str | None:
    """Look up the item title from trusted enrichment sources only.

    Queries BrickLink and BrickEconomy directly -- these are curated
    catalogues so their titles are reliable.  Falls back to lego_items
    only when the row has been through enrichment (last_enriched_at set).

    Returns None when no trusted title exists, so Keepa falls back to
    set-number-only search rather than searching garbage like
    'Image Coming Soon' from a retail placeholder.
    """
    try:
        # 1. BrickLink catalogue (highest priority)
        row = conn.execute(
            "SELECT title FROM bricklink_items WHERE item_id = ?",
            [set_number],
        ).fetchone()
        if row and row[0]:
            return row[0]

        # 2. Latest BrickEconomy snapshot
        row = conn.execute(
            "SELECT title FROM brickeconomy_snapshots "
            "WHERE set_number = ? ORDER BY scraped_at DESC LIMIT 1",
            [set_number],
        ).fetchone()
        if row and row[0]:
            return row[0]

        # 3. lego_items only if enrichment has run (title came from a
        #    trusted source, not a retail scrape placeholder)
        row = conn.execute(
            "SELECT title FROM lego_items "
            "WHERE set_number = ? AND last_enriched_at IS NOT NULL",
            [set_number],
        ).fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        logger.warning("Failed to look up title for %s", set_number, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


def _fetch(browser, set_number: str, item_title: str | None) -> Result[object, ExecutorResult]:
    """IO boundary: run the browser scrape.  Returns Ok(result) or Err(ExecutorResult)."""
    from services.keepa.scraper import scrape_with_page

    try:
        result = browser.run(scrape_with_page, set_number, item_title)
    except Exception as exc:
        browser.restart()
        error = str(exc) or repr(exc) or "Browser exception (no message)"
        return Err(ExecutorResult.fail(error, category=ErrorCategory.BROWSER_CRASH))
    return Ok(result)


def _validate(
    scrape_result: object, set_number: str, browser: object,
) -> Result[object, ExecutorResult]:
    """Pure: check scrape result for errors and classify them."""
    if not scrape_result.success:
        if scrape_result.not_found:
            return Err(ExecutorResult.skip(scrape_result.error or "Not found on Keepa"))
        if scrape_result.mismatch:
            return Err(ExecutorResult.fail(
                scrape_result.error or "Keepa product mismatch",
                category=ErrorCategory.PRODUCT_MISMATCH,
                permanent=True,
            ))
        # Actual browser/page issue -- restart and retry
        browser.restart()
        return Err(ExecutorResult.fail(
            scrape_result.error or "Keepa scrape failed",
            category=ErrorCategory.BROWSER_CRASH,
        ))
    return Ok(scrape_result)


def _persist(conn: Any, scrape_result: object) -> Result[None, ExecutorResult]:
    """IO boundary: save snapshot and price records."""
    from services.keepa.repository import record_keepa_prices, save_keepa_snapshot

    try:
        save_keepa_snapshot(conn, scrape_result.product_data)
    except Exception:
        logger.error("Keepa snapshot insert failed", exc_info=True)
        return Err(ExecutorResult.fail("Failed to save Keepa snapshot", category=ErrorCategory.UNKNOWN))
    record_keepa_prices(conn, scrape_result.product_data)
    return Ok(None)


# ---------------------------------------------------------------------------
# Executor (composes the pipeline)
# ---------------------------------------------------------------------------


@executor(TaskType.KEEPA, concurrency=5, timeout=300, browser_profile="keepa-profile")
def execute_keepa(
    conn: Any,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape Keepa for Amazon price history."""
    from config.settings import KEEPA_CONFIG
    from services.browser import BrowserConfig, get_persistent_browser
    from services.keepa.scheduler import record_keepa_failure, record_keepa_success

    item_title = _lookup_item_title(conn, set_number)

    browser = get_persistent_browser(BrowserConfig(
        profile_name=f"keepa-{worker_index}",
        headless=KEEPA_CONFIG.headless,
        locale=KEEPA_CONFIG.locale,
        window=(KEEPA_CONFIG.viewport_width, KEEPA_CONFIG.viewport_height),
    ))

    # Pipeline: fetch -> validate -> persist
    result = (
        _fetch(browser, set_number, item_title)
        .flat_map(lambda r: _validate(r, set_number, browser))
    )

    # Record success/failure for scheduling
    if result.is_err():
        record_keepa_failure(set_number)
        return result.unwrap_or_else(lambda e: e)

    record_keepa_success(set_number)

    # Persist
    persist_result = _persist(conn, result.unwrap())
    if persist_result.is_err():
        return persist_result.unwrap_or_else(lambda e: e)

    logger.info("Keepa for %s: OK", set_number)
    return ExecutorResult.ok()
