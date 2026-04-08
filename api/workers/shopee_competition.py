"""Shopee competition tracker worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class ShopeeCompetitionWorker:
    scraper_id = "shopee_competition"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from db.connection import get_connection
        from db.schema import init_schema
        from services.shopee.competition_repository import (
            get_portfolio_items_needing_competition_check,
        )
        from services.shopee.competition_scraper import run_competition_batch

        conn = get_connection()
        init_schema(conn)
        try:
            if job.url == "batch":
                items = get_portfolio_items_needing_competition_check(conn)
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

            if not items:
                return WorkResult(
                    items_found=0,
                    items=[{"successful": 0, "failed": 0, "skipped": 0, "total": 0}],
                    log_summary="0/0 successful",
                )

            # Pass conn so the scraper can query previous listings for revisits
            result = await run_competition_batch(items, conn=conn)
        finally:
            conn.close()

        return WorkResult(
            items_found=result.successful,
            items=[{
                "successful": result.successful,
                "failed": result.failed,
                "skipped": result.skipped,
                "total": result.total_items,
            }],
            log_summary=f"{result.successful}/{result.total_items} successful",
        )
