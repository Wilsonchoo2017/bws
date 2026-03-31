"""Keepa source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult
from api.workers.transforms import keepa_product_to_dict

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class KeepaWorker:
    scraper_id = "keepa"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from db.connection import get_connection
        from db.schema import init_schema
        from services.keepa.repository import record_keepa_prices, save_keepa_snapshot
        from services.keepa.scraper import scrape_keepa

        # job.url is the set number (e.g. "60305")
        set_number = job.url.strip()

        result = await scrape_keepa(set_number)

        if not result.success:
            raise RuntimeError(result.error or "Keepa scrape failed")

        conn = get_connection()
        init_schema(conn)
        save_keepa_snapshot(conn, result.product_data)
        record_keepa_prices(conn, result.product_data)

        item = keepa_product_to_dict(result.product_data)

        buy_box_str = (
            f"${result.product_data.current_buy_box_cents / 100:.2f}"
            if result.product_data.current_buy_box_cents
            else "N/A"
        )

        return WorkResult(
            items_found=1,
            items=[item],
            log_summary=(
                f"{set_number} buy_box={buy_box_str}, "
                f"amazon={len(result.product_data.amazon_price)} pts, "
                f"new={len(result.product_data.new_price)} pts, "
                f"rank={len(result.product_data.sales_rank)} pts"
            ),
        )
