"""Background worker that processes scrape jobs from the queue."""


import logging

from api.jobs import JobManager, job_manager
from api.schemas import JobStatus

logger = logging.getLogger("bws.worker")


async def run_worker(manager: JobManager | None = None) -> None:
    """Main worker loop -- dequeues jobs and runs scrapers.

    Runs forever, processing one job at a time.
    """
    mgr = manager or job_manager
    logger.info("Worker started, waiting for jobs...")

    while True:
        job_id = await mgr.dequeue()
        job = mgr.get_job(job_id)
        if not job:
            continue

        logger.info("Processing job %s: %s -> %s", job_id, job.scraper_id, job.url)
        mgr.mark_running(job_id)

        try:
            if job.scraper_id == "shopee":
                items = await _run_shopee_scrape(job.url)
                mgr.mark_completed(
                    job_id,
                    items_found=len(items),
                    items=items,
                )
                logger.info("Job %s completed: %d items", job_id, len(items))
            elif job.scraper_id == "enrichment":
                result = _run_enrichment(job.url)
                mgr.mark_completed(
                    job_id,
                    items_found=result["fields_found"],
                    items=[result],
                )
                logger.info(
                    "Enrichment job %s completed: %d/%d fields found",
                    job_id,
                    result["fields_found"],
                    result["fields_total"],
                )
            else:
                mgr.mark_failed(job_id, f"Unknown scraper: {job.scraper_id}")

        except Exception as e:
            logger.exception("Job %s failed", job_id)
            mgr.mark_failed(job_id, str(e))


async def _run_shopee_scrape(url: str) -> list[dict]:
    """Run a Shopee scrape and return items as dicts."""
    from services.shopee.scraper import scrape_shop_page

    result = await scrape_shop_page(url, max_items=200)

    if not result.success:
        raise RuntimeError(result.error or "Scrape failed")

    return [
        {
            "title": item.title,
            "price_display": item.price_display,
            "sold_count": item.sold_count,
            "rating": item.rating,
            "shop_name": item.shop_name,
            "product_url": item.product_url,
            "image_url": item.image_url,
        }
        for item in result.items
    ]


def _run_enrichment(set_number: str) -> dict:
    """Run metadata enrichment for a single LEGO set.

    Synchronous -- called from the async worker loop via the queue.
    Uses the enrichment orchestrator with real fetchers.
    """
    from db.connection import get_connection
    from db.schema import init_schema
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.fetchers import (
        fetch_from_bricklink,
        fetch_from_brickranker,
        fetch_from_worldbricks,
    )
    from services.enrichment.orchestrator import enrich
    from services.enrichment.repository import (
        store_enrichment_result,
    )
    from services.enrichment.types import FieldStatus, SourceId
    from services.items.repository import get_item_detail

    conn = get_connection()
    init_schema(conn)

    try:
        # Get current item state
        item = get_item_detail(conn, set_number)
        if not item:
            return {
                "set_number": set_number,
                "fields_found": 0,
                "fields_total": 0,
                "error": f"Item {set_number} not found in lego_items",
            }

        # Build fetchers that close over the DB connection
        fetchers = {
            SourceId.BRICKLINK: lambda sn: fetch_from_bricklink(conn, sn),
            SourceId.WORLDBRICKS: lambda sn: fetch_from_worldbricks(conn, sn),
            SourceId.BRICKRANKER: lambda sn: fetch_from_brickranker(conn, sn),
        }

        # Run enrichment
        # TODO: persist circuit breaker state across jobs
        cb_state = CircuitBreakerState()
        result, _ = enrich(set_number, item, fetchers, cb_state)

        # Store results
        store_enrichment_result(conn, result)

        # Build response
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

    finally:
        conn.close()
