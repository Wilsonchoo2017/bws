"""Auto-enrichment helpers -- dedup and queue enrichment jobs."""

import logging

from api.jobs import JobManager
from api.schemas import JobStatus

logger = logging.getLogger("bws.enrichment.auto")


def _get_pending_enrichment_set_numbers(manager: JobManager) -> set[str]:
    """Get set numbers that already have queued/running enrichment jobs."""
    pending: set[str] = set()
    for job in manager.list_jobs(limit=100):
        if job.scraper_id != "enrichment":
            continue
        if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            continue
        # Parse set_number from job URL ("75192" or "75192:bricklink")
        set_number = job.url.split(":")[0]
        pending.add(set_number)
    return pending


def queue_enrichment_if_needed(
    manager: JobManager,
    set_number: str,
) -> bool:
    """Queue an enrichment job if one isn't already pending for this set.

    Returns True if a job was queued, False if skipped (already pending).
    """
    pending = _get_pending_enrichment_set_numbers(manager)
    if set_number in pending:
        return False

    manager.create_job("enrichment", set_number)
    logger.info("Auto-queued enrichment for %s", set_number)
    return True


def queue_enrichment_batch(
    manager: JobManager,
    set_numbers: list[str],
) -> int:
    """Queue enrichment for multiple sets, deduplicating against pending jobs.

    Returns count of newly queued jobs.
    """
    pending = _get_pending_enrichment_set_numbers(manager)
    queued = 0

    for sn in set_numbers:
        if sn in pending:
            continue
        manager.create_job("enrichment", sn)
        pending.add(sn)  # prevent dupes within this batch
        queued += 1

    if queued > 0:
        logger.info("Auto-queued enrichment for %d sets", queued)

    return queued
