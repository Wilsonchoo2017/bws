"""BrickEconomy source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.transforms import brickeconomy_snapshot_to_dict

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class BrickeconomyWorker:
    scraper_id = "brickeconomy"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from db.connection import get_connection
        from db.schema import init_schema
        from services.brickeconomy.repository import record_current_value, save_snapshot
        from services.brickeconomy.scraper import scrape_set

        # job.url is the set number (e.g. "40346-1")
        set_number = job.url.strip()

        result = await scrape_set(set_number)

        if not result.success:
            raise RuntimeError(result.error or "BrickEconomy scrape failed")

        # Save snapshot and price record
        conn = get_connection()
        init_schema(conn)
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
