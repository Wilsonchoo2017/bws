"""BrickLink catalog source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.shared import queue_enrichment_for_catalog_items
from api.workers.transforms import catalog_item_to_dict, extract_set_numbers_from_catalog

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class BricklinkCatalogWorker:
    scraper_id = "bricklink_catalog"
    max_concurrency = 2

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from db.connection import get_connection
        from db.schema import init_schema
        from services.bricklink.scraper import scrape_catalog_list

        conn = get_connection()
        init_schema(conn)

        def on_progress(current_page: int, total_pages: int, items_so_far: int) -> None:
            mgr.update_progress(
                job.job_id,
                f"Page {current_page}/{total_pages} -- {items_so_far} items found",
            )

        try:
            result = await scrape_catalog_list(conn, job.url, on_progress=on_progress)
        finally:
            conn.close()

        if not result.success:
            raise RuntimeError(result.error or "BrickLink catalog scrape failed")

        set_numbers = extract_set_numbers_from_catalog(result.items)
        items = [catalog_item_to_dict(item) for item in result.items]

        queue_enrichment_for_catalog_items(mgr, set_numbers)

        return WorkResult(
            items_found=result.items_found,
            items=items,
            log_summary=(
                f"{result.items_found} found, "
                f"{result.items_inserted} inserted, "
                f"{result.items_skipped} skipped"
            ),
        )
