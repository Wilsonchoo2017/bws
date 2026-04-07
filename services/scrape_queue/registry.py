"""Self-registering executor registry.

New scrapers register themselves via the ``@executor`` decorator instead
of being added to a central dict in ``dispatcher.py``.  The dispatcher
imports :data:`REGISTRY` and iterates over whatever has been registered.

Usage::

    @executor(TaskType.KEEPA, concurrency=3, timeout=280, browser_profile="keepa")
    def execute_keepa(conn, set_number, *, worker_index=0) -> ExecutorResult:
        ...

Adding a new scraper = one new file + the decorator.  Zero changes to
the dispatcher.
"""

from __future__ import annotations

import logging

from services.scrape_queue.models import Executor, TaskType, TaskTypeConfig

logger = logging.getLogger("bws.scrape_queue.registry")


# ---------------------------------------------------------------------------
# Registry state
# ---------------------------------------------------------------------------

REGISTRY: dict[TaskType, TaskTypeConfig] = {}


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def executor(
    task_type: TaskType,
    *,
    concurrency: int = 1,
    timeout: int = 300,
    browser_profile: str | None = None,
):
    """Register a function as the executor for *task_type*.

    The function must satisfy the :class:`Executor` protocol (see
    ``models.py``).
    """
    def decorator(fn: Executor) -> Executor:
        if task_type in REGISTRY:
            logger.warning(
                "Overwriting executor for %s (was %s, now %s)",
                task_type.value,
                REGISTRY[task_type].executor.__name__,
                fn.__name__,  # type: ignore[union-attr]
            )
        REGISTRY[task_type] = TaskTypeConfig(
            task_type=task_type,
            executor=fn,
            concurrency=concurrency,
            timeout_seconds=timeout,
            browser_profile=browser_profile,
        )
        return fn

    return decorator


def get_config(task_type: TaskType) -> TaskTypeConfig:
    """Look up config for a task type. Raises if not registered."""
    try:
        return REGISTRY[task_type]
    except KeyError:
        raise ValueError(
            f"No executor registered for {task_type.value}. "
            f"Registered: {[t.value for t in REGISTRY]}"
        ) from None
