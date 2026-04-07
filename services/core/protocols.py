"""Repository and service protocols for dependency inversion.

These protocols define the contracts that business logic depends on,
decoupling executors from concrete database implementations.  Tests can
provide in-memory fakes; production code injects the Postgres-backed
implementations.

The protocols are deliberately thin -- only the methods that executors
and the dispatcher actually call.  Internal helpers remain private to
the concrete implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from services.scrape_queue.models import (
        ErrorCategory,
        ScrapeTask,
        TaskType,
    )


# ---------------------------------------------------------------------------
# Scrape task queue
# ---------------------------------------------------------------------------


class ScrapeTaskRepository(Protocol):
    """Manages the lifecycle of scrape tasks."""

    def claim_next(
        self, worker_id: str, task_type: TaskType,
    ) -> ScrapeTask | None: ...

    def complete(self, task_id: str) -> None: ...

    def fail(self, task_id: str, error: str) -> None: ...

    def force_fail(self, task_id: str, error: str) -> None: ...

    def requeue_for_cooldown(self, task_id: str) -> None: ...

    def record_attempt(
        self,
        task_id: str,
        attempt_number: int,
        *,
        error_category: ErrorCategory | None = None,
        error_message: str | None = None,
        duration_seconds: float | None = None,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Item lookup (read-only)
# ---------------------------------------------------------------------------


class ItemRepository(Protocol):
    """Read-only access to LEGO item metadata."""

    def get_item_detail(self, set_number: str) -> dict | None: ...

    def get_title(self, set_number: str) -> str | None: ...


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------


class SnapshotWriter(Protocol):
    """Persists scrape results to storage."""

    def save(self, snapshot: object) -> None: ...


# ---------------------------------------------------------------------------
# Enrichment storage
# ---------------------------------------------------------------------------


class EnrichmentRepository(Protocol):
    """Stores resolved enrichment results back to the item table."""

    def store_result(self, result: object) -> None: ...
