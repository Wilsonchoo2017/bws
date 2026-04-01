"""Enrichment source worker -- thin adapter that delegates to the scrape queue.

Legacy enrichment jobs are converted to persistent scrape tasks.
Kept in the worker registry for backward compatibility.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from api.workers.base import WorkResult

if TYPE_CHECKING:
    from api.jobs import Job, JobManager

logger = logging.getLogger("bws.worker")


def _parse_job_url(job_url: str) -> tuple[str, str | None]:
    """Parse set_number and optional source from a job URL like '75192:bricklink'."""
    parts = job_url.split(":", 1)
    return (parts[0], parts[1] if len(parts) > 1 else None)


def _error_result(set_number: str, error: str) -> dict:
    """Build a standardised error result dict."""
    return {
        "set_number": set_number,
        "fields_found": 0,
        "fields_total": 0,
        "error": error,
        "field_details": [],
    }


class EnrichmentWorker:
    scraper_id = "enrichment"
    max_concurrency = 2

    async def run(self, job: Job, mgr: JobManager) -> WorkResult:
        """Convert legacy enrichment job to persistent scrape tasks."""
        result = await asyncio.to_thread(_create_scrape_tasks, job.url)
        return WorkResult(
            items_found=result["tasks_created"],
            items=[result],
            log_summary=f"Created {result['tasks_created']} scrape tasks for {result['set_number']}",
        )


def _create_scrape_tasks(job_url: str) -> dict:
    """Create persistent scrape tasks from a legacy enrichment job URL."""
    from db.connection import get_connection
    from db.schema import init_schema
    from services.scrape_queue.models import TaskType
    from services.scrape_queue.repository import create_task, create_tasks_for_set

    set_number, source_str = _parse_job_url(job_url)

    conn = get_connection()
    init_schema(conn)

    try:
        if source_str:
            source_to_type = {
                "bricklink": TaskType.BRICKLINK_METADATA,
                "brickeconomy": TaskType.BRICKECONOMY,
            }
            task_type = source_to_type.get(source_str)
            if task_type:
                task = create_task(conn, set_number, task_type)
                tasks = [task] if task else []
            else:
                tasks = []
        else:
            tasks = create_tasks_for_set(conn, set_number)

        return {
            "set_number": set_number,
            "tasks_created": len(tasks),
            "task_types": [t.task_type.value for t in tasks],
        }
    finally:
        conn.close()
