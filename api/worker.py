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
