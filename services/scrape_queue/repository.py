"""Repository functions for the persistent scrape task queue."""

from __future__ import annotations

import logging
import uuid

from typing import Any

from services.scrape_queue.models import (
    ACTIVE_STATUSES,
    NON_SET_TASK_TYPES,
    TASK_DEPENDENCIES,
    TASK_PRIORITIES,
    ErrorCategory,
    ScrapeTask,
    TaskStatus,
    TaskType,
)


logger = logging.getLogger("bws.scrape_queue")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_rowcount(result: object) -> int:
    """Extract affected row count from a connection result."""
    # PgCursorResult wraps a psycopg2 cursor
    cursor = getattr(result, "_cursor", None)
    if cursor is not None and hasattr(cursor, "rowcount"):
        return cursor.rowcount

    # Fallback: result set with (Count,) for DML statements
    try:
        row = result.fetchone()
        if row is not None:
            return row[0]
    except Exception:
        pass
    return -1


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
_COLUMNS_SQL_PREFIXED = ", ".join(f"st.{c}" for c in _TASK_COLUMNS)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def _create_task_inner(
    conn: Any,
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

    recently_completed = conn.execute(
        "SELECT 1 FROM scrape_tasks "
        "WHERE set_number = ? AND task_type = ? AND status = 'completed' "
        "AND completed_at > CURRENT_TIMESTAMP - INTERVAL '24 hours' "
        "LIMIT 1",
        [set_number, task_type.value],
    ).fetchone()
    if recently_completed:
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
    conn: Any,
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


def is_polybag(set_number: str) -> bool:
    """Return True if the set number indicates a polybag, foil pack, or blister pack.

    Regular LEGO sets have 5-digit set numbers (e.g. 75335).
    Polybags, foil packs, and blister packs use 6+ digit numbers (e.g. 892291).
    """
    digits = set_number.split("-")[0]
    return len(digits) >= 6


def create_tasks_for_set(
    conn: Any,
    set_number: str,
) -> list[ScrapeTask]:
    """Create the full set of scrape tasks for a LEGO set.

    Tasks without dependencies start as ``pending``.
    Tasks with dependencies start as ``blocked``.
    Deduplicates: skips task types that already have an active task.
    Wrapped in a single transaction for atomicity.
    Skips polybags/foil packs (6+ digit set numbers).
    """
    if is_polybag(set_number):
        logger.debug("Skipping polybag/foil pack: %s", set_number)
        return []

    conn.execute("BEGIN TRANSACTION")
    try:
        created: list[ScrapeTask] = []
        for task_type in TaskType:
            if task_type in NON_SET_TASK_TYPES:
                continue
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
    conn: Any,
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
        type_filter = "AND st.task_type = ? "
        params = [task_type.value]

    conn.execute("BEGIN TRANSACTION")
    try:
        row = conn.execute(
            f"SELECT {_COLUMNS_SQL_PREFIXED} FROM scrape_tasks st "  # noqa: S608
            "LEFT JOIN lego_items li ON st.set_number = li.set_number "
            f"WHERE st.status = 'pending' {type_filter}"
            "ORDER BY COALESCE(li.year_released, 0) DESC, st.created_at ASC "
            "LIMIT 1",
            params,
        ).fetchone()
        if not row:
            conn.execute("COMMIT")
            return None

        task = _row_to_task(row, _TASK_COLUMNS)
        result = conn.execute(
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

        # Check if we actually claimed the row -- another worker may
        # have grabbed it between our SELECT and UPDATE.
        rows_affected = _get_rowcount(result)
        if rows_affected == 0:
            conn.execute("ROLLBACK")
            logger.debug(
                "Task %s already claimed by another worker", task.task_id,
            )
            return None

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
    conn: Any,
    task_id: str,
) -> None:
    """Mark a task as completed and unblock dependents.

    Only updates if the task is still running (guards against late writes
    from orphaned executor threads after a timeout).
    """
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
        WHERE task_id = ? AND status = 'running'
        """,
        [task_id],
    )

    _unblock_dependents(conn, set_number, task_type_str)


def fail_task(
    conn: Any,
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


def force_fail_task(
    conn: Any,
    task_id: str,
    error: str,
) -> None:
    """Immediately mark a task as failed, skipping remaining retries."""
    conn.execute(
        """
        UPDATE scrape_tasks
        SET status = 'failed', error = ?, completed_at = now(),
            locked_by = NULL, locked_at = NULL
        WHERE task_id = ?
        """,
        [error, task_id],
    )


def requeue_for_cooldown(
    conn: Any,
    task_id: str,
) -> None:
    """Return a task to pending without burning an attempt.

    Used when a source is in cooldown -- the task should be retried
    later, not counted as a failure.
    """
    conn.execute(
        """UPDATE scrape_tasks
           SET status = 'pending', locked_by = NULL, locked_at = NULL,
               attempt_count = attempt_count - 1
           WHERE task_id = ?""",
        [task_id],
    )


def force_fail_by_worker(
    conn: Any,
    worker_id: str,
    task_type_value: str,
    error: str,
) -> None:
    """Force-fail the running task locked by a specific worker.

    Used by the dispatcher timeout handler when only the worker_id
    and task_type are known (no task_id available).
    """
    conn.execute(
        """
        UPDATE scrape_tasks
        SET status = 'failed', error = ?, completed_at = now(),
            locked_by = NULL, locked_at = NULL
        WHERE locked_by = ? AND task_type = ? AND status = 'running'
        """,
        [error, worker_id, task_type_value],
    )


# ---------------------------------------------------------------------------
# Attempt history
# ---------------------------------------------------------------------------


def record_attempt(
    conn: Any,
    task_id: str,
    attempt_number: int,
    *,
    error_category: ErrorCategory | None = None,
    error_message: str | None = None,
    duration_seconds: float | None = None,
) -> None:
    """Record one attempt (success or failure) in the history table."""
    conn.execute(
        """
        INSERT INTO scrape_task_attempts
            (id, task_id, attempt_number, error_category, error_message,
             duration_seconds, created_at)
        VALUES (nextval('scrape_task_attempts_id_seq'), ?, ?, ?, ?, ?, now())
        """,
        [
            task_id,
            attempt_number,
            error_category.value if error_category else None,
            error_message,
            duration_seconds,
        ],
    )


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


def _unblock_dependents(
    conn: Any,
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


def reset_running_tasks(conn: Any) -> int:
    """Reset all running tasks to pending on startup.

    After a crash/restart, no workers are alive so any task still
    marked 'running' is orphaned.  Unconditionally resetting them is
    simpler and safer than the old stale-lock heuristic.
    """
    count = conn.execute(
        "SELECT COUNT(*) FROM scrape_tasks WHERE status = 'running'",
    ).fetchone()[0]

    if count > 0:
        # Only re-queue tasks that still have retries remaining
        conn.execute(
            "UPDATE scrape_tasks "
            "SET status = 'pending', locked_by = NULL, locked_at = NULL "
            "WHERE status = 'running' AND attempt_count < max_attempts",
        )
        # Fail tasks that have exhausted their retries
        conn.execute(
            "UPDATE scrape_tasks "
            "SET status = 'failed', error = 'Exhausted retries (crash recovery)', "
            "    completed_at = now(), locked_by = NULL, locked_at = NULL "
            "WHERE status = 'running' AND attempt_count >= max_attempts",
        )
        logger.info("Reset %d running tasks on startup", count)

    return count


def re_evaluate_blocked(conn: Any) -> int:
    """Re-evaluate blocked tasks whose dependencies may have completed.

    Called on startup after reset_running_tasks to handle the case where a
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
    conn: Any,
    set_number: str,
) -> list[ScrapeTask]:
    """Get all scrape tasks for a given set_number."""
    rows = conn.execute(
        f"SELECT {_COLUMNS_SQL} FROM scrape_tasks "  # noqa: S608
        "WHERE set_number = ? ORDER BY priority ASC, created_at ASC",
        [set_number],
    ).fetchall()
    return [_row_to_task(row, _TASK_COLUMNS) for row in rows]


def get_queue_stats(conn: Any) -> dict[str, int]:
    """Get counts of tasks by status."""
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM scrape_tasks GROUP BY status",
    ).fetchall()
    return {status: count for status, count in rows}


def has_pending_bricklink_tasks(conn: Any) -> bool:
    """Check if there are pending or in-progress BrickLink metadata tasks."""
    row = conn.execute(
        """SELECT COUNT(*) FROM scrape_tasks
           WHERE task_type = 'bricklink_metadata'
             AND status IN ('pending', 'in_progress')""",
    ).fetchone()
    return bool(row and row[0] > 0)


def get_priority_rescrape_candidates(
    conn: Any,
    task_type: TaskType,
    *,
    stale_days: int = 30,
) -> list[str]:
    """Find set_numbers needing a rescrape for the given task type.

    Returns sets where ALL of these are true:
    - The set is retiring soon, retired within the last 6 months, or in the portfolio
    - No task of ``task_type`` completed within ``stale_days``
    - No active (pending/running/blocked) task of ``task_type`` exists

    Returns a deduplicated list of set_numbers.
    """
    stale_days = int(stale_days)
    task_type_value = task_type.value
    active_list = [s.value for s in ACTIVE_STATUSES]
    active_placeholders = ", ".join("?" for _ in active_list)

    sql = f"""
        WITH priority_sets AS (
            -- Retiring soon
            SELECT li.set_number
            FROM lego_items li
            WHERE li.retiring_soon = TRUE

            UNION

            -- Retired within last 6 months (use retired_date when parseable)
            SELECT li.set_number
            FROM lego_items li
            WHERE li.retired_date IS NOT NULL
              AND li.retired_date ~ '^\\d{{4}}-\\d{{2}}'
              AND CAST(li.retired_date AS DATE) >= CURRENT_DATE - INTERVAL '6 months'

            UNION

            -- Retired within last 6 months (fallback: year_retired)
            SELECT li.set_number
            FROM lego_items li
            WHERE li.retired_date IS NULL
              AND li.year_retired IS NOT NULL
              AND li.year_retired >= EXTRACT(YEAR FROM CURRENT_DATE - INTERVAL '6 months')

            UNION

            -- Portfolio holdings
            SELECT pt.set_number
            FROM portfolio_transactions pt
            GROUP BY pt.set_number
            HAVING SUM(CASE WHEN pt.txn_type = 'BUY' THEN pt.quantity ELSE -pt.quantity END) > 0
        ),
        last_scrape AS (
            SELECT set_number, MAX(completed_at) AS last_completed
            FROM scrape_tasks
            WHERE task_type = ?
              AND status = 'completed'
            GROUP BY set_number
        )
        SELECT ps.set_number
        FROM priority_sets ps
        LEFT JOIN last_scrape ls ON ls.set_number = ps.set_number
        WHERE (ls.last_completed IS NULL
               OR ls.last_completed < CURRENT_TIMESTAMP - INTERVAL '{stale_days} days')
          AND NOT EXISTS (
              SELECT 1 FROM scrape_tasks st
              WHERE st.set_number = ps.set_number
                AND st.task_type = ?
                AND st.status IN ({active_placeholders})
          )
        ORDER BY ps.set_number
    """  # noqa: S608

    rows = conn.execute(sql, [task_type_value, task_type_value, *active_list]).fetchall()
    return [row[0] for row in rows]
