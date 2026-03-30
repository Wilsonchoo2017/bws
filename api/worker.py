"""Background worker that processes scrape jobs from the queue."""


import asyncio
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
                _queue_enrichment_for_scraped_items(mgr, items)
                await _check_deal_signals()
            elif job.scraper_id == "toysrus":
                result = await _run_toysrus_scrape()
                mgr.mark_completed(
                    job_id,
                    items_found=len(result),
                    items=result,
                )
                logger.info("Job %s completed: %d items", job_id, len(result))
                _queue_enrichment_for_scraped_items(mgr, result)
                await _check_deal_signals()
            elif job.scraper_id == "shopee_saturation":
                result = await _run_saturation_batch(job.url)
                mgr.mark_completed(
                    job_id,
                    items_found=result["successful"],
                    items=[result],
                )
                logger.info(
                    "Saturation job %s completed: %d/%d successful",
                    job_id,
                    result["successful"],
                    result["total"],
                )
            elif job.scraper_id == "enrichment":
                result = await asyncio.to_thread(_run_enrichment, job.url)
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
                await _check_deal_signals()
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


async def _run_toysrus_scrape() -> list[dict]:
    """Run the ToysRUs LEGO catalog scrape and return items as dicts."""
    from db.connection import get_connection
    from db.schema import init_schema
    from services.toysrus.scraper import scrape_all_lego

    conn = get_connection()
    init_schema(conn)

    try:
        result = await scrape_all_lego(conn=conn)
    finally:
        conn.close()

    if not result.success:
        raise RuntimeError(result.error or "ToysRUs scrape failed")

    return [
        {
            "title": p.name,
            "price_display": f"RM {p.price_myr}",
            "sold_count": None,
            "rating": None,
            "shop_name": "Toys\"R\"Us Malaysia",
            "product_url": p.url,
            "image_url": p.image_url,
        }
        for p in result.products
    ]


async def _run_saturation_batch(job_url: str) -> dict:
    """Run Shopee saturation check batch.

    job_url format: "batch" (check all stale items) or "75192" (single set)
    """
    from db.connection import get_connection
    from db.schema import init_schema
    from services.shopee.saturation_repository import get_items_needing_saturation_check
    from services.shopee.saturation_scraper import run_saturation_batch

    conn = get_connection()
    init_schema(conn)
    try:
        if job_url == "batch":
            items = get_items_needing_saturation_check(conn)
        else:
            row = conn.execute(
                "SELECT set_number, title, rrp_cents FROM lego_items WHERE set_number = ?",
                [job_url],
            ).fetchone()
            items = (
                [{"set_number": row[0], "title": row[1], "rrp_cents": row[2]}]
                if row
                else []
            )
    finally:
        conn.close()

    if not items:
        return {"successful": 0, "failed": 0, "skipped": 0, "total": 0}

    result = await run_saturation_batch(items)
    return {
        "successful": result.successful,
        "failed": result.failed,
        "skipped": result.skipped,
        "total": result.total_items,
    }


def _run_enrichment(job_url: str) -> dict:
    """Run metadata enrichment for a single LEGO set.

    Synchronous -- called from the async worker loop via asyncio.to_thread.
    Uses the enrichment orchestrator with real fetchers.

    job_url format: "75192" (all sources) or "75192:bricklink" (specific source)
    """
    from db.connection import get_connection
    from db.schema import init_schema
    from services.enrichment.circuit_breaker import CircuitBreakerState
    from services.enrichment.config import SOURCE_CONFIGS
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

    # Parse job_url: "75192" or "75192:bricklink"
    if ":" in job_url:
        set_number, source_str = job_url.split(":", 1)
    else:
        set_number = job_url
        source_str = None

    all_fetchers = {
        SourceId.BRICKLINK: fetch_from_bricklink,
        SourceId.WORLDBRICKS: fetch_from_worldbricks,
        SourceId.BRICKRANKER: fetch_from_brickranker,
    }

    # Map source string to SourceId
    source_map = {s.value: s for s in SourceId}
    requested_source = source_map.get(source_str) if source_str else None

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

        # Build fetchers -- all or just the requested source
        if requested_source:
            fetcher_fn = all_fetchers.get(requested_source)
            if not fetcher_fn:
                return {
                    "set_number": set_number,
                    "fields_found": 0,
                    "fields_total": 0,
                    "error": f"Unknown source: {source_str}",
                }
            fetchers = {requested_source: lambda sn, f=fetcher_fn: f(conn, sn)}
            # Only enrich fields this source can provide
            fields = tuple(SOURCE_CONFIGS[requested_source].fields_provided)
        else:
            fetchers = {
                sid: (lambda sn, f=fn: f(conn, sn))
                for sid, fn in all_fetchers.items()
            }
            fields = None

        # Run enrichment
        cb_state = CircuitBreakerState()
        result, _ = enrich(set_number, item, fetchers, cb_state, fields=fields)

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


async def _check_deal_signals() -> None:
    """Run signal check and send Ntfy notifications for strong deals."""
    from db.connection import get_connection
    from db.schema import init_schema
    from services.notifications.deal_notifier import check_and_notify

    try:
        conn = get_connection()
        init_schema(conn)
        try:
            sent = await asyncio.to_thread(check_and_notify, conn)
            if sent:
                logger.info("Deal check: sent %d notifications", sent)
        finally:
            conn.close()
    except Exception:
        logger.exception("Deal signal check failed")


def _queue_enrichment_for_scraped_items(
    manager: JobManager,
    items: list[dict],
) -> None:
    """Extract set numbers from scraped items and queue enrichment jobs."""
    from services.enrichment.auto import queue_enrichment_batch
    from services.items.set_number import extract_set_number

    set_numbers: list[str] = []
    for item in items:
        title = item.get("title", "")
        if not title:
            continue
        sn = extract_set_number(title)
        if sn:
            set_numbers.append(sn)

    if set_numbers:
        queued = queue_enrichment_batch(manager, set_numbers)
        if queued > 0:
            logger.info(
                "Post-scrape: queued enrichment for %d/%d sets",
                queued,
                len(set_numbers),
            )
