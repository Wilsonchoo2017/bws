"""Repository functions for the persistent scrape task queue."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from services.scrape_queue.models import (
    ACTIVE_STATUSES,
    TASK_DEPENDENCIES,
    TASK_PRIORITIES,
    ScrapeTask,
    TaskStatus,
    TaskType,
)

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.scrape_queue")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_task(row: tuple, columns: list[str]) -> ScrapeTask:
    d = dict(zip(columns, row))
    return ScrapeTask(
        id=d["id"],
        task_id=d["task_id"],
        set_number=d["set_number"],
        task_type=TaskType(d["task_type"]),
        priority=d["priority"],
        status=TaskStatus(d["status"]),
        depends_on=d.get("depends_on"),
        attempt_count=d["attempt_count"],
        max_attempts=d["max_attempts"],
        error=d.get("error"),
        created_at=d["created_at"],
        started_at=d.get("started_at"),
        completed_at=d.get("completed_at"),
        locked_by=d.get("locked_by"),
        locked_at=d.get("locked_at"),
    )


_TASK_COLUMNS = [
    "id", "task_id", "set_number", "task_type", "priority", "status",
    "depends_on", "attempt_count", "max_attempts", "error",
    "created_at", "started_at", "completed_at", "locked_by", "locked_at",
]

_COLUMNS_SQL = ", ".join(_TASK_COLUMNS)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def _create_task_inner(
    conn: DuckDBPyConnection,
    set_number: str,
    task_type: TaskType,
) -> ScrapeTask | None:
    """Create a single scrape task within an existing transaction.

    Returns None if an active task already exists for (set_number, task_type).
    Caller must manage BEGIN/COMMIT.
    """
    active_list = [s.value for s in ACTIVE_STATUSES]
    placeholders = ", ".join("?" for _ in active_list)
    existing = conn.execute(
        f"SELECT 1 FROM scrape_tasks "  # noqa: S608
        f"WHERE set_number = ? AND task_type = ? AND status IN ({placeholders}) "
        "LIMIT 1",
        [set_number, task_type.value, *active_list],
    ).fetchone()
    if existing:
        return None

    task_id = uuid.uuid4().hex
    priority = TASK_PRIORITIES[task_type]
    dep = TASK_DEPENDENCIES.get(task_type)
    depends_on = dep.value if dep else None
    status = TaskStatus.BLOCKED if dep else TaskStatus.PENDING

    seq_id = conn.execute("SELECT nextval('scrape_tasks_id_seq')").fetchone()[0]
    conn.execute(
        """
        INSERT INTO scrape_tasks (id, task_id, set_number, task_type, priority,
                                  status, depends_on)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [seq_id, task_id, set_number, task_type.value, priority,
         status.value, depends_on],
    )

    row = conn.execute(
        f"SELECT {_COLUMNS_SQL} FROM scrape_tasks WHERE task_id = ?",  # noqa: S608
        [task_id],
    ).fetchone()
    return _row_to_task(row, _TASK_COLUMNS) if row else None


def create_task(
    conn: DuckDBPyConnection,
    set_number: str,
    task_type: TaskType,
) -> ScrapeTask | None:
    """Create a single scrape task, deduplicating against active tasks.

    Returns None if an active task already exists for (set_number, task_type).
    Wraps in a transaction to prevent TOCTOU races.
    """
    conn.execute("BEGIN TRANSACTION")
    try:
        result = _create_task_inner(conn, set_number, task_type)
        conn.execute("COMMIT")
        return result
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_tasks_for_set(
    conn: DuckDBPyConnection,
    set_number: str,
) -> list[ScrapeTask]:
    """Create the full set of scrape tasks for a LEGO set.

    Tasks without dependencies start as ``pending``.
    Tasks with dependencies start as ``blocked``.
    Deduplicates: skips task types that already have an active task.
    Wrapped in a single transaction for atomicity.
    """
    conn.execute("BEGIN TRANSACTION")
    try:
        created: list[ScrapeTask] = []
        for task_type in TaskType:
            task = _create_task_inner(conn, set_number, task_type)
            if task is not None:
                created.append(task)

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    if created:
        logger.info(
            "Created %d scrape tasks for %s: %s",
            len(created),
            set_number,
            ", ".join(t.task_type.value for t in created),
        )
    return created


# ---------------------------------------------------------------------------
# Claim / execute lifecycle
# ---------------------------------------------------------------------------


def claim_next(
    conn: DuckDBPyConnection,
    worker_id: str,
    task_type: TaskType | None = None,
) -> ScrapeTask | None:
    """Atomically claim the next pending task, optionally filtered by type.

    When ``task_type`` is given, only tasks of that type are considered.
    This allows each data source to have its own independent worker
    without being starved by higher-priority tasks of other types.

    Uses an explicit transaction to prevent two workers from claiming
    the same task.

    Returns None when the queue is empty (for the given type).
    """
    type_filter = ""
    params: list = []
    if task_type is not None:
        type_filter = "AND task_type = ? "
        params = [task_type.value]

    conn.execute("BEGIN TRANSACTION")
    try:
        row = conn.execute(
            f"SELECT {_COLUMNS_SQL} FROM scrape_tasks "  # noqa: S608
            f"WHERE status = 'pending' {type_filter}"
            "ORDER BY created_at ASC "
            "LIMIT 1",
            params,
        ).fetchone()
        if not row:
            conn.execute("COMMIT")
            return None

        task = _row_to_task(row, _TASK_COLUMNS)
        conn.execute(
            """
            UPDATE scrape_tasks
            SET status = 'running',
                locked_by = ?,
                locked_at = now(),
                started_at = now(),
                attempt_count = attempt_count + 1
            WHERE task_id = ? AND status = 'pending'
            """,
            [worker_id, task.task_id],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    updated = conn.execute(
        f"SELECT {_COLUMNS_SQL} FROM scrape_tasks WHERE task_id = ?",  # noqa: S608
        [task.task_id],
    ).fetchone()
    return _row_to_task(updated, _TASK_COLUMNS) if updated else None


def complete_task(
    conn: DuckDBPyConnection,
    task_id: str,
) -> None:
    """Mark a task as completed and unblock dependents."""
    row = conn.execute(
        "SELECT set_number, task_type FROM scrape_tasks WHERE task_id = ?",
        [task_id],
    ).fetchone()
    if not row:
        return

    set_number, task_type_str = row

    conn.execute(
        """
        UPDATE scrape_tasks
        SET status = 'completed', completed_at = now(),
            locked_by = NULL, locked_at = NULL
        WHERE task_id = ?
        """,
        [task_id],
    )

    _unblock_dependents(conn, set_number, task_type_str)


def fail_task(
    conn: DuckDBPyConnection,
    task_id: str,
    error: str,
) -> None:
    """Record a task failure. Retries if under max_attempts, else marks failed."""
    row = conn.execute(
        "SELECT attempt_count, max_attempts FROM scrape_tasks WHERE task_id = ?",
        [task_id],
    ).fetchone()
    if not row:
        return

    attempt_count, max_attempts = row
    if attempt_count >= max_attempts:
        conn.execute(
            """
            UPDATE scrape_tasks
            SET status = 'failed', error = ?, completed_at = now(),
                locked_by = NULL, locked_at = NULL
            WHERE task_id = ?
            """,
            [error, task_id],
        )
    else:
        conn.execute(
            """
            UPDATE scrape_tasks
            SET status = 'pending', error = ?,
                locked_by = NULL, locked_at = NULL
            WHERE task_id = ?
            """,
            [error, task_id],
        )


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


def _unblock_dependents(
    conn: DuckDBPyConnection,
    set_number: str,
    completed_type: str,
) -> None:
    """Transition blocked tasks to pending when their dependency completes.

    Special cases:
    - minifigures: skip (mark completed) when minifig_count is 0 or NULL.
    - google_trends: skip when title or year_released is missing.
    """
    blocked_rows = conn.execute(
        f"SELECT {_COLUMNS_SQL} FROM scrape_tasks "  # noqa: S608
        "WHERE set_number = ? AND depends_on = ? AND status = 'blocked'",
        [set_number, completed_type],
    ).fetchall()

    for row in blocked_rows:
        task = _row_to_task(row, _TASK_COLUMNS)

        if task.task_type == TaskType.MINIFIGURES:
            mf_row = conn.execute(
                "SELECT minifig_count FROM lego_items WHERE set_number = ?",
                [set_number],
            ).fetchone()
            minifig_count = mf_row[0] if mf_row and mf_row[0] else 0
            if minifig_count <= 0:
                conn.execute(
                    """
                    UPDATE scrape_tasks
                    SET status = 'completed', completed_at = now(),
                        error = 'minifig_count is 0'
                    WHERE task_id = ?
                    """,
                    [task.task_id],
                )
                continue

        if task.task_type == TaskType.GOOGLE_TRENDS:
            item_row = conn.execute(
                "SELECT title, year_released FROM lego_items WHERE set_number = ?",
                [set_number],
            ).fetchone()
            if not item_row or not item_row[0] or not item_row[1]:
                conn.execute(
                    """
                    UPDATE scrape_tasks
                    SET status = 'completed', completed_at = now(),
                        error = 'missing title or year_released'
                    WHERE task_id = ?
                    """,
                    [task.task_id],
                )
                continue

        conn.execute(
            "UPDATE scrape_tasks SET status = 'pending' WHERE task_id = ?",
            [task.task_id],
        )


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------


def reclaim_stale(
    conn: DuckDBPyConnection,
    stale_minutes: int = 30,
) -> int:
    """Reset running tasks with stale locks back to pending.

    Returns the number of tasks reclaimed.
    """
    count = conn.execute(
        """
        SELECT COUNT(*) FROM scrape_tasks
        WHERE status = 'running'
          AND locked_at < CURRENT_TIMESTAMP - to_minutes(CAST(? AS INTEGER))
        """,
        [stale_minutes],
    ).fetchone()[0]

    if count > 0:
        conn.execute(
            """
            UPDATE scrape_tasks
            SET status = 'pending', locked_by = NULL, locked_at = NULL
            WHERE status = 'running'
              AND locked_at < CURRENT_TIMESTAMP - to_minutes(CAST(? AS INTEGER))
            """,
            [stale_minutes],
        )
        logger.info("Reclaimed %d stale scrape tasks", count)

    return count


def re_evaluate_blocked(conn: DuckDBPyConnection) -> int:
    """Re-evaluate blocked tasks whose dependencies may have completed.

    Called on startup after reclaim_stale to handle the case where a
    dependency completed before a crash but the blocked task wasn't
    yet transitioned.

    Returns count of tasks unblocked.
    """
    blocked_rows = conn.execute(
        f"SELECT {_COLUMNS_SQL} FROM scrape_tasks WHERE status = 'blocked'",  # noqa: S608
    ).fetchall()

    unblocked = 0
    for row in blocked_rows:
        task = _row_to_task(row, _TASK_COLUMNS)
        if not task.depends_on:
            conn.execute(
                "UPDATE scrape_tasks SET status = 'pending' WHERE task_id = ?",
                [task.task_id],
            )
            unblocked += 1
            continue

        dep_completed = conn.execute(
            """
            SELECT 1 FROM scrape_tasks
            WHERE set_number = ? AND task_type = ? AND status = 'completed'
            LIMIT 1
            """,
            [task.set_number, task.depends_on],
        ).fetchone()
        if dep_completed:
            _unblock_dependents(conn, task.set_number, task.depends_on)
            unblocked += 1

    if unblocked > 0:
        logger.info("Re-evaluated blocked tasks: unblocked %d", unblocked)
    return unblocked


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def get_tasks_for_set(
    conn: DuckDBPyConnection,
    set_number: str,
) -> list[ScrapeTask]:
    """Get all scrape tasks for a given set_number."""
    rows = conn.execute(
        f"SELECT {_COLUMNS_SQL} FROM scrape_tasks "  # noqa: S608
        "WHERE set_number = ? ORDER BY priority ASC, created_at ASC",
        [set_number],
    ).fetchall()
    return [_row_to_task(row, _TASK_COLUMNS) for row in rows]


def get_queue_stats(conn: DuckDBPyConnection) -> dict[str, int]:
    """Get counts of tasks by status."""
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM scrape_tasks GROUP BY status",
    ).fetchall()
    return {status: count for status, count in rows}
