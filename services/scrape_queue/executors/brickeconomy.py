"""BrickEconomy executor -- browser-based, uses PersistentBrowser."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from services.scrape_queue.models import ExecutorResult

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.executor.brickeconomy")


def execute_brickeconomy(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape BrickEconomy and store enrichment fields + snapshot."""
    from config.settings import BRICKECONOMY_CONFIG
    from services.brickeconomy.scraper import scrape_with_search
    from services.browser import BrowserConfig, get_persistent_browser
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import store_enrichment_result
    from services.enrichment.source_adapter import adapt_brickeconomy, make_failed_result
    from services.enrichment.types import SourceId
    from services.items.repository import get_item_detail

    item = get_item_detail(conn, set_number)
    if not item:
        return ExecutorResult.fail(f"Item {set_number} not found in lego_items")

    browser = get_persistent_browser(BrowserConfig(
        profile_name=f"brickeconomy-{worker_index}",
        headless=BRICKECONOMY_CONFIG.headless,
        locale=BRICKECONOMY_CONFIG.locale,
    ))

    def _fetch_be(sn: str):
        from services.brickeconomy.parser import is_excluded_packaging
        from services.brickeconomy.repository import record_current_value, save_snapshot
        from services.items.repository import delete_item

        scrape_result = browser.run(scrape_with_search, sn)

        if not scrape_result.success:
            return make_failed_result(SourceId.BRICKECONOMY, scrape_result.error or "Unknown error")
        if scrape_result.snapshot is None:
            return make_failed_result(SourceId.BRICKECONOMY, "No data returned")

        # Delete non-standard packaging sets (foil packs, polybags, etc.)
        if is_excluded_packaging(scrape_result.snapshot.packaging):
            delete_item(conn, sn)
            return make_failed_result(
                SourceId.BRICKECONOMY,
                f"Excluded packaging '{scrape_result.snapshot.packaging}' -- item deleted",
            )

        save_snapshot(conn, scrape_result.snapshot)
        record_current_value(conn, scrape_result.snapshot)
        return adapt_brickeconomy(scrape_result.snapshot)

    fetchers = {SourceId.BRICKECONOMY: _fetch_be}
    cb_state = CircuitBreakerState()
    result, _ = enrich(set_number, item, fetchers, cb_state)

    if result.fields_found == 0:
        browser.restart()
        return ExecutorResult.fail("BrickEconomy returned no data (0 fields)")

    store_enrichment_result(conn, result)

    logger.info(
        "BrickEconomy for %s: %d/%d fields found",
        set_number,
        result.fields_found,
        len(result.field_results),
    )
    return ExecutorResult.ok()
