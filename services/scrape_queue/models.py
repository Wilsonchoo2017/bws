"""Scrape queue models -- task types, statuses, priorities, and dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskType(str, Enum):
    BRICKLINK_METADATA = "bricklink_metadata"
    BRICKECONOMY = "brickeconomy"
    KEEPA = "keepa"
    MINIFIGURES = "minifigures"
    GOOGLE_TRENDS = "google_trends"


class TaskStatus(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ScrapeTask:
    id: int
    task_id: str
    set_number: str
    task_type: TaskType
    priority: int
    status: TaskStatus
    depends_on: str | None
    attempt_count: int
    max_attempts: int
    error: str | None
    created_at: object
    started_at: object | None
    completed_at: object | None
    locked_by: str | None
    locked_at: object | None


# Lower number = higher priority.  Priority 1 tasks run first.
TASK_PRIORITIES: dict[TaskType, int] = {
    TaskType.BRICKLINK_METADATA: 1,
    TaskType.BRICKECONOMY: 1,
    TaskType.KEEPA: 2,
    TaskType.MINIFIGURES: 3,
    TaskType.GOOGLE_TRENDS: 4,
}

# Task types that must complete (for the same set_number) before a given type can run.
TASK_DEPENDENCIES: dict[TaskType, TaskType] = {
    TaskType.MINIFIGURES: TaskType.BRICKLINK_METADATA,
    TaskType.GOOGLE_TRENDS: TaskType.BRICKLINK_METADATA,
}

# Statuses that indicate an active (non-terminal) task.
ACTIVE_STATUSES: frozenset[TaskStatus] = frozenset({
    TaskStatus.PENDING,
    TaskStatus.BLOCKED,
    TaskStatus.RUNNING,
})
