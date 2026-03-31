"""ToysRUs source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.shared import check_deal_signals, queue_enrichment_for_scraped_items
from api.workers.transforms import toysrus_product_to_dict

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class ToysrusWorker:
    scraper_id = "toysrus"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
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

        items = [toysrus_product_to_dict(p) for p in result.products]

        queue_enrichment_for_scraped_items(mgr, items)
        await check_deal_signals()

        return WorkResult(
            items_found=len(items),
            items=items,
            log_summary=f"{len(items)} items",
        )
