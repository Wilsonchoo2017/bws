"""Minifigures executor -- scrapes BrickLink minifigure inventory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from services.scrape_queue.models import ExecutorResult

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue.executor.minifigures")


def execute_minifigures(
    conn: DuckDBPyConnection,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Scrape BrickLink minifigure inventory and individual minifig pages."""
    from services.bricklink.scraper import scrape_set_minifigures_sync
    from services.enrichment.config import PRICING_FRESHNESS

    item_id = f"{set_number}-1"

    bl_row = conn.execute(
        "SELECT item_id FROM bricklink_items WHERE item_id = ?",
        [item_id],
    ).fetchone()
    if not bl_row:
        return ExecutorResult.fail(
            f"BrickLink item {item_id} not found (metadata not scraped?)"
        )

    mf_result = scrape_set_minifigures_sync(
        conn, item_id, save=True, scrape_prices=True,
        pricing_freshness=PRICING_FRESHNESS,
    )
    logger.info(
        "Minifigures for %s: %d/%d scraped",
        set_number,
        mf_result.minifigures_scraped,
        mf_result.minifig_count,
    )
    return ExecutorResult.ok()
