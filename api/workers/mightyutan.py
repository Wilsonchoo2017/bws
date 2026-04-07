"""Mighty Utan source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.shared import check_deal_signals, queue_enrichment_for_scraped_items
from api.workers.transforms import mightyutan_product_to_dict

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class MightyutanWorker:
    scraper_id = "mightyutan"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from db.connection import get_connection
        from db.schema import init_schema
        from services.mightyutan.scraper import scrape_all_lego

        conn = get_connection()
        init_schema(conn)

        def _progress(msg: str) -> None:
            mgr.update_progress(job.job_id, msg)

        try:
            result = await scrape_all_lego(conn=conn, on_progress=_progress)
        finally:
            conn.close()

        if not result.success:
            raise RuntimeError(result.error or "Mighty Utan scrape failed")

        items = [mightyutan_product_to_dict(p) for p in result.products]

        queue_enrichment_for_scraped_items(mgr, items)
        await check_deal_signals()

        return WorkResult(
            items_found=len(items),
            items=items,
            log_summary=f"{len(items)} items",
        )
