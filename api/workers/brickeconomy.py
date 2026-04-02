"""BrickEconomy source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.transforms import brickeconomy_snapshot_to_dict
from services.brickeconomy.parser import is_excluded_packaging

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class BrickeconomyWorker:
    scraper_id = "brickeconomy"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from db.connection import get_connection
        from db.schema import init_schema

        if job.url.strip() == "batch":
            return await self._run_batch(job, mgr)

        return await self._run_single(job, mgr)

    async def _run_batch(self, job: Job, mgr: JobManager) -> WorkResult:
        """Find portfolio/watchlist items without a snapshot and queue individual jobs."""
        from db.connection import get_connection
        from db.schema import init_schema
        from services.items.repository import get_unscraped_priority_items

        conn = get_connection()
        init_schema(conn)
        set_numbers = get_unscraped_priority_items(conn)

        for sn in set_numbers:
            mgr.create_job(self.scraper_id, sn)

        return WorkResult(
            items_found=len(set_numbers),
            items=[],
            log_summary=f"Queued {len(set_numbers)} portfolio/watchlist items for BrickEconomy scraping",
        )

    async def _run_single(self, job: Job, mgr: JobManager) -> WorkResult:
        """Scrape a single set."""
        from db.connection import get_connection
        from db.schema import init_schema
        from services.brickeconomy.repository import record_current_value, save_snapshot
        from services.brickeconomy.scraper import scrape_set

        set_number = job.url.strip()

        result = await scrape_set(set_number)

        if not result.success:
            raise RuntimeError(result.error or "BrickEconomy scrape failed")

        conn = get_connection()
        init_schema(conn)

        # Delete non-standard packaging sets (foil packs, polybags, etc.)
        if is_excluded_packaging(result.snapshot.packaging):
            from services.items.repository import delete_item

            deleted = delete_item(conn, set_number)
            action = "deleted" if deleted else "not found"
            return WorkResult(
                items_found=0,
                items=[],
                log_summary=(
                    f"{set_number} has excluded packaging "
                    f"'{result.snapshot.packaging}' -- {action}"
                ),
            )

        save_snapshot(conn, result.snapshot)
        record_current_value(conn, result.snapshot)

        item = brickeconomy_snapshot_to_dict(result.snapshot)

        value_str = (
            f"${result.snapshot.value_new_cents / 100:.2f}"
            if result.snapshot.value_new_cents
            else "N/A"
        )

        return WorkResult(
            items_found=1,
            items=[item],
            log_summary=(
                f"{set_number} value={value_str}, "
                f"chart={len(result.snapshot.value_chart)} pts, "
                f"sales={len(result.snapshot.sales_trend)} months"
            ),
        )
