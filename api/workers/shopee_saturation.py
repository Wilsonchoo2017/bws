"""Shopee saturation source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.transforms import EMPTY_SATURATION_SUMMARY, saturation_result_to_summary

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class ShopeeSaturationWorker:
    scraper_id = "shopee_saturation"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from db.connection import get_connection
        from db.schema import init_schema
        from services.shopee.saturation_repository import get_items_needing_saturation_check
        from services.shopee.saturation_scraper import run_saturation_batch

        conn = get_connection()
        init_schema(conn)
        try:
            if job.url == "batch":
                items = get_items_needing_saturation_check(conn)
            else:
                row = conn.execute(
                    "SELECT set_number, title, rrp_cents FROM lego_items WHERE set_number = ?",
                    [job.url],
                ).fetchone()
                items = (
                    [{"set_number": row[0], "title": row[1], "rrp_cents": row[2]}]
                    if row
                    else []
                )
        finally:
            conn.close()

        if not items:
            return WorkResult(
                items_found=0,
                items=[EMPTY_SATURATION_SUMMARY],
                log_summary="0/0 successful",
            )

        result = await run_saturation_batch(items)
        summary = saturation_result_to_summary(result)

        return WorkResult(
            items_found=result.successful,
            items=[summary],
            log_summary=f"{result.successful}/{result.total_items} successful",
        )
