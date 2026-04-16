"""Operations monitoring endpoints.

Read the current state of every background scheduler, find sets that
keep getting re-enqueued (usually a sign of a stuck executor), and
toggle individual schedulers on/off without restarting the API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_db
from services.operations.scheduler_registry import (
    find_duplicate_enqueues,
    get_spec,
    load_scheduler_status,
    set_enabled,
)

if TYPE_CHECKING:
    from api.task_registry import TaskStatus
    from db.pg.dual_writer import DualWriter

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/schedulers")
async def list_schedulers(db: "DualWriter" = Depends(get_db)) -> dict:
    """Return status of every registered background scheduler."""
    rows = load_scheduler_status(db)
    return {"success": True, "data": rows}


@router.get("/schedulers/duplicates")
async def list_duplicate_enqueues(
    days: int = Query(3, ge=1, le=30),
    min_count: int = Query(2, ge=1, le=50),
    limit: int = Query(50, ge=1, le=500),
    db: "DualWriter" = Depends(get_db),
) -> dict:
    """Return (set_number, task_type) pairs enqueued repeatedly in the window."""
    rows = find_duplicate_enqueues(
        db, days=days, min_count=min_count, limit=limit,
    )
    return {
        "success": True,
        "data": rows,
        "meta": {"days": days, "min_count": min_count, "total": len(rows)},
    }


@router.post("/schedulers/{name}/toggle")
async def toggle_scheduler(name: str, enabled: bool = Query(...)) -> dict:
    """Enable or disable a named scheduler (persisted to runtime_settings)."""
    if get_spec(name) is None:
        raise HTTPException(status_code=404, detail=f"Unknown scheduler: {name}")
    try:
        set_enabled(name, enabled)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "data": {"name": name, "enabled": enabled}}


# ---------------------------------------------------------------------------
# Background task health & restart
# ---------------------------------------------------------------------------


def _serialize_task_status(status: "TaskStatus") -> dict:
    """Convert a TaskStatus dataclass to an API-safe dict."""
    from dataclasses import asdict

    return asdict(status)


@router.get("/tasks")
async def list_background_tasks() -> dict:
    """Return health status of all registered background asyncio tasks."""
    from api.task_registry import get_all_statuses

    return {"success": True, "data": [_serialize_task_status(s) for s in get_all_statuses()]}


@router.post("/tasks/{name}/restart")
async def restart_background_task(name: str) -> dict:
    """Restart a crashed or finished background task."""
    from api.task_registry import restart

    try:
        result = restart(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "data": _serialize_task_status(result)}
