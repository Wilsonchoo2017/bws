"""Enrichment source worker."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.shared import check_deal_signals
from api.workers.transforms import enrichment_log_summary

if TYPE_CHECKING:
    from api.jobs import Job, JobManager

logger = logging.getLogger("bws.worker")


class EnrichmentWorker:
    scraper_id = "enrichment"
    max_concurrency = 2

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        result = await asyncio.to_thread(_run_enrichment, job.url)

        await check_deal_signals()

        return WorkResult(
            items_found=result["fields_found"],
            items=[result],
            log_summary=enrichment_log_summary(result.get("field_details", [])),
        )


def _run_enrichment(job_url: str) -> dict:
    """Run metadata enrichment for a single LEGO set.

    Synchronous -- called from the async worker loop via asyncio.to_thread.
    """
    from db.connection import get_connection
    from db.schema import init_schema
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.config import SOURCE_CONFIGS
    from services.enrichment.fetchers import (
        fetch_from_brickeconomy,
        fetch_from_bricklink,
        fetch_from_brickranker,
    )
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import store_enrichment_result
    from services.enrichment.types import FieldStatus, SourceId
    from services.items.repository import get_item_detail

    set_number, source_str = _parse_job_url(job_url)

    all_fetchers = {
        SourceId.BRICKLINK: fetch_from_bricklink,
        SourceId.BRICKRANKER: fetch_from_brickranker,
        SourceId.BRICKECONOMY: fetch_from_brickeconomy,
    }

    source_map = {s.value: s for s in SourceId}
    requested_source = source_map.get(source_str) if source_str else None

    conn = get_connection()
    init_schema(conn)

    try:
        item = get_item_detail(conn, set_number)
        if not item:
            return _error_result(set_number, f"Item {set_number} not found in lego_items")

        if requested_source:
            fetcher_fn = all_fetchers.get(requested_source)
            if not fetcher_fn:
                return _error_result(set_number, f"Unknown source: {source_str}")
            fetchers = {requested_source: lambda sn, f=fetcher_fn: f(conn, sn)}
            fields = tuple(SOURCE_CONFIGS[requested_source].fields_provided)
        else:
            fetchers = {
                sid: (lambda sn, f=fn: f(conn, sn))
                for sid, fn in all_fetchers.items()
            }
            fields = None

        cb_state = CircuitBreakerState()
        result, _ = enrich(set_number, item, fetchers, cb_state, fields=fields)

        store_enrichment_result(conn, result)
        _try_scrape_minifigures(conn, set_number, result)

        return _build_enrichment_response(set_number, result)

    finally:
        conn.close()


# -- Pure helpers (no side effects) ------------------------------------------


def _parse_job_url(job_url: str) -> tuple[str, str | None]:
    """Parse enrichment job URL into (set_number, source_str | None)."""
    if ":" in job_url:
        set_number, source_str = job_url.split(":", 1)
        return set_number, source_str
    return job_url, None


def _error_result(set_number: str, error: str) -> dict:
    """Build an error response dict for enrichment."""
    return {
        "set_number": set_number,
        "fields_found": 0,
        "fields_total": 0,
        "error": error,
        "field_details": [],
    }


def _build_enrichment_response(set_number: str, result: object) -> dict:
    """Build the enrichment response dict from an EnrichmentResult."""
    from services.enrichment.types import FieldStatus

    field_details = [
        {
            "field": r.field.value,
            "status": r.status.value,
            "value": r.value if r.status == FieldStatus.FOUND else None,
            "source": r.source.value if r.source else None,
            "errors": list(r.errors),
        }
        for r in result.field_results
    ]

    return {
        "set_number": set_number,
        "fields_found": result.fields_found,
        "fields_total": len(result.field_results),
        "sources_called": [s.value for s in result.sources_called],
        "field_details": field_details,
    }


# -- Side-effectful helper ---------------------------------------------------


def _try_scrape_minifigures(conn: object, set_number: str, result: object) -> None:
    """Attempt minifigure scrape if the set has minifigs. Swallows exceptions."""
    from services.enrichment.types import FieldStatus

    try:
        minifig_count = _extract_minifig_count(result, conn, set_number)
        if not minifig_count or minifig_count <= 0:
            return

        from services.bricklink.scraper import scrape_set_minifigures_sync
        from services.enrichment.config import PRICING_FRESHNESS

        item_id = f"{set_number}-1"
        bl_row = conn.execute(
            "SELECT item_id FROM bricklink_items WHERE item_id = ?",
            [item_id],
        ).fetchone()
        if bl_row:
            mf_result = scrape_set_minifigures_sync(
                conn, item_id, save=True, scrape_prices=True,
                pricing_freshness=PRICING_FRESHNESS,
            )
            logger.info(
                "Minifig scrape for %s: %d/%d scraped",
                set_number,
                mf_result.minifigures_scraped,
                mf_result.minifig_count,
            )
    except Exception:
        logger.exception("Minifig scrape failed for %s", set_number)


def _extract_minifig_count(
    result: object, conn: object, set_number: str
) -> int | None:
    """Get minifig count from enrichment result or DB fallback."""
    from services.enrichment.types import FieldStatus

    for r in result.field_results:
        if (
            r.field.value == "minifig_count"
            and r.status == FieldStatus.FOUND
            and r.value
        ):
            return int(r.value)

    row = conn.execute(
        "SELECT minifig_count FROM lego_items WHERE set_number = ?",
        [set_number],
    ).fetchone()
    if row and row[0] and int(row[0]) > 0:
        return int(row[0])

    return None
