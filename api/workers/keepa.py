"""Keepa source worker -- thin adapter that delegates to the scrape queue.

Manual Keepa jobs are converted to persistent scrape tasks.
The scrape dispatcher handles actual execution, ensuring only one
Keepa scrape runs at a time.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from api.workers.base import WorkResult

if TYPE_CHECKING:
    from api.jobs import Job, JobManager

logger = logging.getLogger("bws.keepa.worker")


class KeepaWorker:
    scraper_id = "keepa"
    max_concurrency = 1

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        """Convert a manual Keepa job to a persistent scrape task."""
        result = await asyncio.to_thread(_create_keepa_task, job.url.strip())
        return WorkResult(
            items_found=result["tasks_created"],
            items=[result],
            log_summary=f"Created {result['tasks_created']} Keepa scrape task for {result['set_number']}",
        )


def _create_keepa_task(set_number: str) -> dict:
    """Create a persistent Keepa scrape task in the database queue."""
    from db.connection import get_connection
    from db.schema import init_schema
    from services.scrape_queue.models import TaskType
    from services.scrape_queue.repository import create_task

    conn = get_connection()
    try:
        init_schema(conn)
        task = create_task(conn, set_number, TaskType.KEEPA)
        tasks_created = 1 if task else 0
        return {
            "set_number": set_number,
            "tasks_created": tasks_created,
            "task_types": [TaskType.KEEPA.value] if task else [],
        }
    finally:
        conn.close()
