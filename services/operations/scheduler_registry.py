"""Central registry of background schedulers with run tracking.

This module is the single source of truth for:

* Which schedulers exist, what they do, and how often they fire.
* Whether each scheduler is currently enabled (runtime toggle, persisted
  to ``runtime_settings.json`` so it survives restarts).
* The ``scheduler_runs`` rows written at the top/bottom of every sweep
  iteration so the operations dashboard can show "last ran at", "queued
  N items", and "error count in last 24h".

Each scheduler file wraps its per-iteration work in:

    async with record_run("enrichment") as run:
        ...
        run.items_queued = queued

and checks ``is_enabled("enrichment")`` before doing work. A disabled
scheduler still ticks but records a run with status="disabled" and
``items_queued=0`` so the UI can show "last skipped at".
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

logger = logging.getLogger("bws.operations.schedulers")


@dataclass(frozen=True)
class SchedulerSpec:
    """Static metadata about a scheduler."""

    name: str
    label: str
    description: str
    category: str
    default_interval_seconds: int


SCHEDULERS: tuple[SchedulerSpec, ...] = (
    SchedulerSpec(
        name="enrichment",
        label="Enrichment",
        description="Scans lego_items for NULL metadata and enqueues scrape_tasks.",
        category="scrape",
        default_interval_seconds=30 * 60,
    ),
    SchedulerSpec(
        name="rescrape",
        label="Priority Rescrape",
        description="Re-enqueues tiered rescrapes (portfolio 30d / watchlist 30d / retiring 60d / general 150d).",
        category="scrape",
        default_interval_seconds=60 * 60,
    ),
    SchedulerSpec(
        name="saturation",
        label="Shopee Saturation",
        description="Finds sets with RRP that need a Shopee saturation re-check.",
        category="marketplace",
        default_interval_seconds=360 * 60,
    ),
    SchedulerSpec(
        name="shopee_competition",
        label="Shopee Competition",
        description="Tiered scan of Shopee competition snapshots (cart/watchlist/holdings/retiring).",
        category="marketplace",
        default_interval_seconds=720 * 60,
    ),
    SchedulerSpec(
        name="carousell_competition",
        label="Carousell Competition",
        description="Tiered scan of Carousell competition snapshots.",
        category="marketplace",
        default_interval_seconds=720 * 60,
    ),
    SchedulerSpec(
        name="keepa",
        label="Keepa Backfill",
        description="Queues Keepa scrape jobs for items missing a Keepa snapshot.",
        category="scrape",
        default_interval_seconds=60 * 60,
    ),
    SchedulerSpec(
        name="bricklink_listings",
        label="BrickLink Listings",
        description="Queues BRICKLINK_METADATA tasks for sets with missing/stale store listings.",
        category="scrape",
        default_interval_seconds=60 * 60,
    ),
    SchedulerSpec(
        name="images",
        label="Image Download",
        description="Batch downloads pending product images (paused while BrickLink metadata is queued).",
        category="scrape",
        default_interval_seconds=5 * 60,
    ),
    SchedulerSpec(
        name="retiring_soon",
        label="Retiring Soon",
        description="Scrapes BrickEconomy retiring-soon list and flags lego_items.",
        category="catalog",
        default_interval_seconds=150 * 86400,
    ),
    SchedulerSpec(
        name="analysis",
        label="BrickEconomy Analysis",
        description="Refreshes analysis-years / themes / subthemes aggregates used by ML features.",
        category="catalog",
        default_interval_seconds=150 * 86400,
    ),
    SchedulerSpec(
        name="prediction_snapshot",
        label="Prediction Snapshot",
        description="Daily ML prediction snapshot: scores all items + backfills actuals.",
        category="ml",
        default_interval_seconds=86400,
    ),
    SchedulerSpec(
        name="captcha_retention",
        label="Captcha Retention",
        description="Nightly prune of resolved/expired Shopee captcha snapshot dirs.",
        category="maintenance",
        default_interval_seconds=86400,
    ),
)

_BY_NAME: dict[str, SchedulerSpec] = {s.name: s for s in SCHEDULERS}


def get_spec(name: str) -> SchedulerSpec | None:
    return _BY_NAME.get(name)


# ---------------------------------------------------------------------------
# Enabled flag (persisted via runtime_settings)
# ---------------------------------------------------------------------------


def is_enabled(name: str) -> bool:
    """Return whether a named scheduler should do work on its next tick.

    Unknown names default to enabled so tests and ad-hoc schedulers that
    haven't been registered yet keep working.
    """
    from config.runtime_settings import runtime_settings

    flags = runtime_settings.get_section("scheduler_enabled")
    if not isinstance(flags, dict):
        return True
    value = flags.get(name)
    if value is None:
        return True
    return bool(value)


def set_enabled(name: str, enabled: bool) -> None:
    """Persist the enabled flag for a scheduler."""
    if name not in _BY_NAME:
        raise KeyError(f"Unknown scheduler: {name}")
    from config.runtime_settings import runtime_settings

    current = runtime_settings.get_section("scheduler_enabled")
    if not isinstance(current, dict):
        current = {}
    new = {**current, name: bool(enabled)}
    runtime_settings.update_section("scheduler_enabled", new)
    logger.info("Scheduler %s -> %s", name, "enabled" if enabled else "disabled")


def get_all_flags() -> dict[str, bool]:
    from config.runtime_settings import runtime_settings

    flags = runtime_settings.get_section("scheduler_enabled")
    if not isinstance(flags, dict):
        flags = {}
    return {spec.name: bool(flags.get(spec.name, True)) for spec in SCHEDULERS}


# ---------------------------------------------------------------------------
# Run tracking
# ---------------------------------------------------------------------------


@dataclass
class RunHandle:
    """Mutable handle passed to scheduler bodies so they can report counts."""

    items_queued: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@asynccontextmanager
async def record_run(name: str) -> AsyncIterator[RunHandle]:
    """Record a scheduler iteration in the ``scheduler_runs`` table.

    Inserts a ``running`` row on enter and updates it to ``ok`` / ``error``
    / ``disabled`` on exit. All DB work is off-loop via ``asyncio.to_thread``
    so the scheduler's own loop is never blocked by Postgres.

    Usage::

        async with record_run("enrichment") as run:
            ...
            run.items_queued = queued

    If ``is_enabled(name)`` is False the body should still run the context
    manager but skip its own work and set status via ``run.details["status"]
    = "disabled"``. For convenience, call ``record_disabled(name)`` instead.
    """
    handle = RunHandle()
    run_id = await asyncio.to_thread(_insert_running, name)
    try:
        yield handle
    except Exception as exc:  # noqa: BLE001
        await asyncio.to_thread(
            _finalize,
            run_id,
            status="error",
            items_queued=handle.items_queued,
            error=str(exc)[:500],
        )
        raise
    else:
        status = handle.details.get("status", "ok")
        await asyncio.to_thread(
            _finalize,
            run_id,
            status=status,
            items_queued=handle.items_queued,
            error=None,
        )


async def record_disabled(name: str) -> None:
    """Write a single ``disabled`` scheduler_runs row (for skipped ticks).

    Kept separate from ``record_run`` so disabled ticks don't spam the table
    when a scheduler is paused for days -- callers should rate-limit via the
    scheduler's own sleep interval.
    """
    run_id = await asyncio.to_thread(_insert_running, name)
    await asyncio.to_thread(
        _finalize, run_id, status="disabled", items_queued=0, error=None,
    )


def _insert_running(name: str) -> int | None:
    try:
        from db.connection import get_connection

        conn = get_connection()
        try:
            row = conn.execute(
                "INSERT INTO scheduler_runs (name, started_at, status) "
                "VALUES (?, ?, 'running') RETURNING id",
                [name, datetime.now(tz=timezone.utc)],
            ).fetchone()
            return int(row[0]) if row else None
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to insert scheduler_runs row for %s", name, exc_info=True)
        return None


def _finalize(
    run_id: int | None,
    *,
    status: str,
    items_queued: int,
    error: str | None,
) -> None:
    if run_id is None:
        return
    try:
        from db.connection import get_connection

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE scheduler_runs "
                "SET finished_at = ?, status = ?, items_queued = ?, error = ? "
                "WHERE id = ?",
                [
                    datetime.now(tz=timezone.utc),
                    status,
                    int(items_queued),
                    error,
                    run_id,
                ],
            )
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to finalize scheduler run %s", run_id, exc_info=True)


# ---------------------------------------------------------------------------
# Reads for the API layer
# ---------------------------------------------------------------------------


def load_scheduler_status(conn: Any) -> list[dict[str, Any]]:
    """Return one status row per registered scheduler.

    Joins the registry with the most-recent ``scheduler_runs`` row and
    24h error counts. Missing runs show ``last_run_at=None`` so the UI can
    render "never ran" without special-casing NULLs in the frontend.
    """
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (name)
                name, started_at, finished_at, status, items_queued, error
            FROM scheduler_runs
            ORDER BY name, started_at DESC
        ),
        last_ok AS (
            SELECT DISTINCT ON (name) name, started_at AS last_ok_at
            FROM scheduler_runs
            WHERE status = 'ok'
            ORDER BY name, started_at DESC
        ),
        err AS (
            SELECT name, COUNT(*) AS errors_24h
            FROM scheduler_runs
            WHERE status = 'error'
              AND started_at >= NOW() - INTERVAL '24 hours'
            GROUP BY name
        )
        SELECT
            latest.name,
            latest.started_at,
            latest.finished_at,
            latest.status,
            latest.items_queued,
            latest.error,
            last_ok.last_ok_at,
            COALESCE(err.errors_24h, 0) AS errors_24h
        FROM latest
        LEFT JOIN last_ok USING (name)
        LEFT JOIN err USING (name)
        """,
    ).fetchall()

    by_name: dict[str, dict[str, Any]] = {}
    for r in rows:
        by_name[r[0]] = {
            "last_run_at": r[1].isoformat() if r[1] else None,
            "last_finished_at": r[2].isoformat() if r[2] else None,
            "last_status": r[3],
            "last_items_queued": int(r[4] or 0),
            "last_error": r[5],
            "last_ok_at": r[6].isoformat() if r[6] else None,
            "errors_24h": int(r[7] or 0),
        }

    flags = get_all_flags()
    out: list[dict[str, Any]] = []
    for spec in SCHEDULERS:
        status_row = by_name.get(spec.name, {})
        out.append(
            {
                "name": spec.name,
                "label": spec.label,
                "description": spec.description,
                "category": spec.category,
                "interval_seconds": spec.default_interval_seconds,
                "enabled": flags.get(spec.name, True),
                "last_run_at": status_row.get("last_run_at"),
                "last_finished_at": status_row.get("last_finished_at"),
                "last_status": status_row.get("last_status"),
                "last_items_queued": status_row.get("last_items_queued", 0),
                "last_error": status_row.get("last_error"),
                "last_ok_at": status_row.get("last_ok_at"),
                "errors_24h": status_row.get("errors_24h", 0),
            },
        )
    return out


def find_duplicate_enqueues(
    conn: Any,
    *,
    days: int = 3,
    min_count: int = 2,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find (set_number, task_type) pairs enqueued more than once recently.

    The scrape_queue dedup window is 24h for completed and 7d for failed, so
    any pair with count > 1 inside the window means either:

    * the task keeps failing and the 7d window hasn't expired (bug: executor
      can't make progress on this set), or
    * tier rotation is creating duplicates across categories (e.g. a set
      lives in both portfolio and watchlist and the tiered rescrape fires
      twice).

    Both cases deserve visibility in the operations UI. Returns rows sorted
    by count DESC then most-recent-first.
    """
    if days <= 0:
        return []
    if min_count < 1:
        min_count = 1

    rows = conn.execute(
        """
        SELECT
            set_number,
            task_type,
            COUNT(*) AS enqueue_count,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN status IN ('pending', 'running') THEN 1 ELSE 0 END) AS in_flight,
            MAX(created_at) AS last_created_at,
            MAX(error) FILTER (WHERE status = 'failed') AS last_error
        FROM scrape_tasks
        WHERE created_at >= NOW() - make_interval(days => ?)
        GROUP BY set_number, task_type
        HAVING COUNT(*) >= ?
        ORDER BY enqueue_count DESC, last_created_at DESC
        LIMIT ?
        """,
        [days, min_count, limit],
    ).fetchall()

    return [
        {
            "set_number": r[0],
            "task_type": r[1],
            "enqueue_count": int(r[2] or 0),
            "completed": int(r[3] or 0),
            "failed": int(r[4] or 0),
            "in_flight": int(r[5] or 0),
            "last_created_at": r[6].isoformat() if r[6] else None,
            "last_error": r[7],
        }
        for r in rows
    ]
