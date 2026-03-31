"""Carousell source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.transforms import carousell_listing_to_dict

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class CarousellWorker:
    scraper_id = "carousell"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from services.carousell.scraper import search_carousell

        # URL is the search query (e.g. "40346" or "lego 40346")
        query = job.url

        result = await search_carousell(query, max_items=100, max_pages=5)

        if not result.success:
            raise RuntimeError(result.error or "Carousell scrape failed")

        items = [carousell_listing_to_dict(listing) for listing in result.listings]

        return WorkResult(
            items_found=len(items),
            items=items,
            log_summary=f"{len(items)} listings (total: {result.total_count})",
        )
