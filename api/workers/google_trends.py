"""Google Trends source worker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.workers.base import WorkResult

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


class GoogleTrendsWorker:
    scraper_id = "google_trends"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        from db.connection import get_connection
        from db.schema import init_schema
        from services.google_trends.repository import save_trends_snapshot
        from services.google_trends.scraper import fetch_interest

        set_number = job.url.strip()

        conn = get_connection()
        try:
            init_schema(conn)

            # Look up year_released from lego_items if available.
            year_released: int | None = None
            row = conn.execute(
                "SELECT year_released FROM lego_items WHERE set_number = ?",
                [set_number],
            ).fetchone()
            if row and row[0]:
                year_released = int(row[0])

            result = fetch_interest(set_number, year_released=year_released)

            if not result.success:
                raise RuntimeError(result.error or "Google Trends scrape failed")

            save_trends_snapshot(conn, result.data)
        finally:
            conn.close()

        points_count = len(result.data.interest_over_time)
        peak_str = (
            f"peak={result.data.peak_value} at {result.data.peak_date}"
            if result.data.peak_value is not None
            else "no data"
        )

        return WorkResult(
            items_found=1,
            items=[{
                "set_number": set_number,
                "keyword": result.data.keyword,
                "points": points_count,
                "peak_value": result.data.peak_value,
                "peak_date": result.data.peak_date,
                "average_value": result.data.average_value,
            }],
            log_summary=f"{set_number} {points_count} pts, {peak_str}",
        )
