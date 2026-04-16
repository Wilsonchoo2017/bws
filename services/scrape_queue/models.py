"""Scrape queue models -- task types, statuses, priorities, and dependencies.

Also defines ``ExecutorResult`` (the typed contract between executors and
the dispatcher) and ``TaskTypeConfig`` (single-source-of-truth for every
per-type knob the dispatcher needs).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskType(str, Enum):
    BRICKLINK_METADATA = "bricklink_metadata"
    BRICKECONOMY = "brickeconomy"
    KEEPA = "keepa"
    MINIFIGURES = "minifigures"
    GOOGLE_TRENDS = "google_trends"
    GOOGLE_TRENDS_THEME = "google_trends_theme"


class TaskStatus(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ErrorCategory(str, Enum):
    RATE_LIMITED = "rate_limited"
    BROWSER_CRASH = "browser_crash"
    DATA_MISSING = "data_missing"
    PRODUCT_MISMATCH = "product_mismatch"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    NETWORK = "network"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Executor result -- replaces the fragile (bool, str|None) + "cooldown:" hack
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutorResult:
    """Typed return value from every executor function.

    Replaces the old ``(bool, str | None)`` tuple where cooldowns were
    encoded as magic ``"cooldown:123"`` strings.

    Exactly one of ``success``, ``error``, or ``cooldown_seconds`` should
    be set per result:
      - success=True, error=None, cooldown=None  -> task completed
      - success=False, error="...", cooldown=None -> task failed
      - success=False, error=None, cooldown=3600  -> source in cooldown
    """

    success: bool
    error: str | None = None
    cooldown_seconds: float | None = None
    error_category: ErrorCategory | None = None
    permanent: bool = False
    outcome: str | None = None  # "success", "skipped" -- None for failures/cooldowns

    @staticmethod
    def ok() -> ExecutorResult:
        return ExecutorResult(success=True, outcome="success")

    @staticmethod
    def skip(reason: str) -> ExecutorResult:
        """Item not available at this source -- don't retry or restart browser."""
        return ExecutorResult(success=True, error=reason, outcome="skipped")

    @staticmethod
    def fail(
        error: str,
        *,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        permanent: bool = False,
    ) -> ExecutorResult:
        return ExecutorResult(
            success=False,
            error=error,
            error_category=category,
            permanent=permanent,
        )

    @staticmethod
    def cooldown(seconds: float) -> ExecutorResult:
        return ExecutorResult(success=False, cooldown_seconds=seconds)

    @property
    def is_cooldown(self) -> bool:
        return self.cooldown_seconds is not None and self.cooldown_seconds > 0


# ---------------------------------------------------------------------------
# Executor protocol -- type-safe interface for all executor functions
# ---------------------------------------------------------------------------


class Executor(Protocol):
    """Interface that every task-type executor must satisfy."""

    def __call__(
        self,
        conn: Any,
        set_number: str,
        *,
        worker_index: int = 0,
    ) -> ExecutorResult: ...


# ---------------------------------------------------------------------------
# Per-type configuration -- single source of truth
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskTypeConfig:
    """All dispatcher knobs for a single task type, in one place.

    Adding a new task type means adding ONE entry to TASK_TYPE_CONFIGS
    instead of updating 5+ separate dicts.
    """

    task_type: TaskType
    executor: Executor
    concurrency: int = 1
    timeout_seconds: float = 300
    browser_profile: str | None = None
    cooldown_check: Callable[[], float] | None = None

    @property
    def uses_browser(self) -> bool:
        return self.browser_profile is not None

    def browser_profile_for(self, worker_index: int) -> str | None:
        """Derive the concrete browser profile name for a given worker slot.

        Single source of truth for profile naming across executors and
        dispatcher cleanup.  Returns the base profile unchanged when
        concurrency is 1, and ``{base}-{worker_index}-profile`` otherwise.
        """
        if self.browser_profile is None:
            return None
        if self.concurrency <= 1:
            return self.browser_profile
        base = self.browser_profile.removesuffix("-profile")
        return f"{base}-{worker_index}-profile"


# ---------------------------------------------------------------------------
# Task model
# ---------------------------------------------------------------------------


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
    reason: str | None = None
    outcome: str | None = None
    source: str | None = None


# ---------------------------------------------------------------------------
# Static tables
# ---------------------------------------------------------------------------

# Lower number = higher priority.  Priority 1 tasks run first.
TASK_PRIORITIES: dict[TaskType, int] = {
    TaskType.BRICKLINK_METADATA: 1,
    TaskType.BRICKECONOMY: 1,
    TaskType.KEEPA: 2,
    TaskType.MINIFIGURES: 3,
    TaskType.GOOGLE_TRENDS: 4,
    TaskType.GOOGLE_TRENDS_THEME: 4,
}

# Task types that must complete (for the same set_number) before a given type can run.
TASK_DEPENDENCIES: dict[TaskType, TaskType] = {
    TaskType.MINIFIGURES: TaskType.BRICKLINK_METADATA,
    TaskType.GOOGLE_TRENDS: TaskType.BRICKLINK_METADATA,
}

# Task types excluded from automatic per-set task creation.
# These are managed via dedicated enqueue scripts.
NON_SET_TASK_TYPES: frozenset[TaskType] = frozenset({
    TaskType.GOOGLE_TRENDS_THEME,
})

# Statuses that indicate an active (non-terminal) task.
ACTIVE_STATUSES: frozenset[TaskStatus] = frozenset({
    TaskStatus.PENDING,
    TaskStatus.BLOCKED,
    TaskStatus.RUNNING,
})
