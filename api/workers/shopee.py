"""Shopee source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.shared import check_deal_signals, queue_enrichment_for_scraped_items
from api.workers.transforms import shopee_item_to_dict

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class ShopeeWorker:
    scraper_id = "shopee"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from services.shopee.scraper import scrape_shop_page

        def _progress(msg: str) -> None:
            mgr.update_progress(job.job_id, msg)

        result = await scrape_shop_page(job.url, max_items=10_000, on_progress=_progress)

        if not result.success:
            raise RuntimeError(result.error or "Scrape failed")

        items = [shopee_item_to_dict(item) for item in result.items]

        queue_enrichment_for_scraped_items(mgr, items)
        await check_deal_signals()

        return WorkResult(
            items_found=len(items),
            items=items,
            log_summary=f"{len(items)} items",
        )
