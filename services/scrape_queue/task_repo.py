"""Database-backed implementation of ScrapeTaskRepository.

Wraps the existing free functions in ``repository.py`` behind the
:class:`~services.core.protocols.ScrapeTaskRepository` protocol so
that executors and the dispatcher can depend on the protocol instead
of raw ``conn + free-function`` calls.
"""

from __future__ import annotations


from services.scrape_queue import repository as repo
from services.scrape_queue.models import ErrorCategory, ScrapeTask, TaskType
from typing import Any


class PgScrapeTaskRepo:
    """Concrete :class:`ScrapeTaskRepository` backed by Postgres."""

    __slots__ = ("_conn",)

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    # -- Protocol methods ----------------------------------------------------

    def claim_next(
        self, worker_id: str, task_type: TaskType,
    ) -> ScrapeTask | None:
        return repo.claim_next(self._conn, worker_id, task_type)

    def complete(self, task_id: str) -> None:
        repo.complete_task(self._conn, task_id)

    def fail(self, task_id: str, error: str) -> None:
        repo.fail_task(self._conn, task_id, error)

    def force_fail(self, task_id: str, error: str) -> None:
        repo.force_fail_task(self._conn, task_id, error)

    def requeue_for_cooldown(self, task_id: str) -> None:
        repo.requeue_for_cooldown(self._conn, task_id)

    def record_attempt(
        self,
        task_id: str,
        attempt_number: int,
        *,
        error_category: ErrorCategory | None = None,
        error_message: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        repo.record_attempt(
            self._conn, task_id, attempt_number,
            error_category=error_category,
            error_message=error_message,
            duration_seconds=duration_seconds,
        )
