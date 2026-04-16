"""Background task registry -- tracks asyncio tasks and allows restart of crashed ones.

Each background task (worker loop, scheduler sweep, dispatcher, etc.) is
registered with a name and a factory callable.  The factory is stored so
that a crashed task can be re-created without restarting the whole server.

Responsibilities are intentionally narrow:
  - Track (name -> live asyncio.Task) mappings
  - Derive task health from asyncio.Task state
  - Recreate a dead task via its stored factory

Serialization to API response dicts is NOT done here -- the route layer
owns that concern.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Literal

logger = logging.getLogger("bws.task_registry")

TaskFactory = Callable[[], Coroutine[Any, Any, Any]]
TaskState = Literal["running", "crashed", "cancelled", "finished"]


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskStatus:
    """Immutable snapshot of a background task's health."""

    name: str
    label: str
    state: TaskState
    error: str | None


@dataclass(frozen=True)
class _TaskEntry:
    """Immutable registration record (internal)."""

    name: str
    label: str
    task: asyncio.Task[Any]
    factory: TaskFactory


# ---------------------------------------------------------------------------
# Registry (module-level singleton)
#
# All callers run on the asyncio event loop -- no thread-safety needed.
# Do not call register/restart/get_* from threads (e.g. asyncio.to_thread).
# ---------------------------------------------------------------------------

_registry: dict[str, _TaskEntry] = {}


def _derive_state(task: asyncio.Task[Any]) -> tuple[TaskState, str | None]:
    """Derive (state, error) from an asyncio.Task."""
    if not task.done():
        return ("running", None)
    if task.cancelled():
        return ("cancelled", None)
    exc = task.exception()
    if exc is not None:
        return ("crashed", str(exc))
    return ("finished", None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register(name: str, label: str, factory: TaskFactory) -> asyncio.Task[Any]:
    """Create an asyncio task and register it for monitoring / restart."""
    task = asyncio.create_task(factory(), name=name)
    _registry[name] = _TaskEntry(name=name, label=label, task=task, factory=factory)
    return task


def get_status(name: str) -> TaskStatus:
    """Return health snapshot for a single task.  Raises KeyError if unknown."""
    entry = _registry[name]
    state, error = _derive_state(entry.task)
    return TaskStatus(name=entry.name, label=entry.label, state=state, error=error)


def get_all_statuses() -> list[TaskStatus]:
    """Return health snapshot for every registered task."""
    return [get_status(name) for name in _registry]


def restart(name: str) -> TaskStatus:
    """Restart a crashed/finished background task.

    Returns the new status.  Raises KeyError if name is unknown,
    ValueError if the task is still running.
    """
    entry = _registry.get(name)
    if entry is None:
        raise KeyError(f"Unknown background task: {name}")

    if not entry.task.done():
        raise ValueError(f"Task {name!r} is still running")

    logger.info("Restarting background task %s", name)
    new_task = asyncio.create_task(entry.factory(), name=name)
    _registry[name] = _TaskEntry(
        name=entry.name,
        label=entry.label,
        task=new_task,
        factory=entry.factory,
    )
    return get_status(name)


def get_all_tasks() -> list[asyncio.Task[Any]]:
    """Return all live asyncio.Task objects (for shutdown)."""
    return [entry.task for entry in _registry.values()]
