"""Base types for source workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from api.jobs import Job, JobManager


@dataclass(frozen=True)
class WorkResult:
    """Uniform result returned by every source worker."""

    items_found: int
    items: list[Any]
    log_summary: str


class SourceWorker(Protocol):
    """Protocol that every source worker must satisfy."""

    scraper_id: str
    max_concurrency: int

    async def run(self, job: Job, mgr: JobManager) -> WorkResult: ...
