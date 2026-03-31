"""Background worker that processes scrape jobs from the queue."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from api.jobs import job_manager
from api.workers import WORKER_REGISTRY
from api.workers.base import SourceWorker

if TYPE_CHECKING:
    from api.jobs import JobManager, Job

logger = logging.getLogger("bws.worker")


def _build_semaphores() -> dict[str, asyncio.Semaphore]:
    """Create one semaphore per source, sized by max_concurrency."""
    return {
        scraper_id: asyncio.Semaphore(worker.max_concurrency)
        for scraper_id, worker in WORKER_REGISTRY.items()
    }


class _WorkerSlots:
    """Track which worker-number slots are in use per scraper."""

    def __init__(self) -> None:
        self._active: dict[str, set[int]] = {}

    def acquire(self, scraper_id: str, max_concurrency: int) -> int:
        active = self._active.setdefault(scraper_id, set())
        for slot in range(1, max_concurrency + 1):
            if slot not in active:
                active.add(slot)
                return slot
        # fallback -- should not happen due to semaphore
        slot = max(active) + 1 if active else 1
        active.add(slot)
        return slot

    def release(self, scraper_id: str, slot: int) -> None:
        active = self._active.get(scraper_id)
        if active:
            active.discard(slot)


async def _process_job(
    mgr: JobManager,
    job: Job,
    worker: SourceWorker,
    semaphore: asyncio.Semaphore,
    slots: _WorkerSlots,
) -> None:
    """Execute a single job behind its source's semaphore."""
    async with semaphore:
        multi = worker.max_concurrency > 1
        worker_no = slots.acquire(job.scraper_id, worker.max_concurrency) if multi else None
        job.worker_no = worker_no
        mgr.mark_running(job.job_id)
        log_prefix = (
            f"[{job.scraper_id} #{worker_no}]" if multi else f"[{job.scraper_id}]"
        )
        logger.info("%s Job %s started: %s", log_prefix, job.job_id, job.url)
        try:
            result = await worker.run(job, mgr)
            mgr.mark_completed(
                job.job_id,
                items_found=result.items_found,
                items=result.items,
            )
            logger.info("%s Job %s completed: %s", log_prefix, job.job_id, result.log_summary)
        except Exception as e:
            logger.exception("%s Job %s failed", log_prefix, job.job_id)
            mgr.mark_failed(job.job_id, str(e))
        finally:
            if multi and worker_no is not None:
                slots.release(job.scraper_id, worker_no)


async def run_worker(manager: JobManager | None = None) -> None:
    """Main worker loop -- dequeues jobs and dispatches to source workers.

    Jobs run concurrently, bounded per source by max_concurrency.
    """
    mgr = manager or job_manager
    semaphores = _build_semaphores()
    slots = _WorkerSlots()
    logger.info("Worker started, waiting for jobs...")

    while True:
        job_id = await mgr.dequeue()
        job = mgr.get_job(job_id)
        if not job:
            continue

        logger.info("Dispatching job %s: %s -> %s", job_id, job.scraper_id, job.url)

        worker = WORKER_REGISTRY.get(job.scraper_id)
        if not worker:
            mgr.mark_failed(job_id, f"Unknown scraper: {job.scraper_id}")
            continue

        sem = semaphores.get(job.scraper_id)
        if not sem:
            sem = asyncio.Semaphore(1)
            semaphores[job.scraper_id] = sem

        asyncio.create_task(_process_job(mgr, job, worker, sem, slots))
