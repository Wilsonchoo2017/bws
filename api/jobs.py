"""Job management -- in-memory queue backed by database for persistence."""


import asyncio
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from dataclasses import dataclass, field

from api.schemas import JobStatus


@dataclass
class Job:
    """A scrape job."""

    job_id: str
    scraper_id: str
    url: str
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    items_found: int = 0
    items: list = field(default_factory=list)
    error: str | None = None
    progress: str | None = None
    worker_no: int | None = None
    reason: str | None = None


class JobManager:
    """Manages scrape jobs with an in-memory store and async queue."""

    def __init__(self) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._max_history = 1000

    def create_job(self, scraper_id: str, url: str, *, reason: str | None = None) -> Job:
        """Create a new job and add it to the queue.

        If a job with the same scraper_id and url is already queued or
        running, returns the existing job instead of creating a duplicate.
        """
        for existing in self._jobs.values():
            if (
                existing.scraper_id == scraper_id
                and existing.url == url
                and existing.status in (JobStatus.QUEUED, JobStatus.RUNNING)
            ):
                return existing

        job_id = uuid.uuid4().hex[:12]
        job = Job(job_id=job_id, scraper_id=scraper_id, url=url, reason=reason)
        self._jobs[job_id] = job
        self._queue.put_nowait(job_id)
        self._trim_history()
        return job

    def find_last_similar(self, scraper_id: str, url: str) -> Job | None:
        """Find the most recent completed or failed job with the same scraper_id and url."""
        for job in reversed(self._jobs.values()):
            if (
                job.scraper_id == scraper_id
                and job.url == url
                and job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
            ):
                return job
        return None

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[Job]:
        """List recent jobs, newest first."""
        jobs = list(self._jobs.values())
        jobs.reverse()
        return jobs[:limit]

    def mark_running(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)

    def mark_completed(
        self,
        job_id: str,
        items_found: int,
        items: list | None = None,
    ) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.items_found = items_found
            if items is not None:
                job.items = items

    def update_progress(self, job_id: str, progress: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.progress = progress

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(timezone.utc)
            job.error = error

    def clear_finished(self) -> int:
        """Remove all completed and failed jobs. Returns count removed."""
        to_remove = [
            jid
            for jid, job in self._jobs.items()
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ]
        for jid in to_remove:
            del self._jobs[jid]
        return len(to_remove)

    async def dequeue(self) -> str:
        """Wait for and return the next job ID from the queue."""
        return await self._queue.get()

    def _trim_history(self) -> None:
        """Remove oldest jobs if exceeding max history."""
        while len(self._jobs) > self._max_history:
            self._jobs.popitem(last=False)


# Singleton
job_manager = JobManager()
