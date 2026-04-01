"""Enrichment API routes."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.connection import get_connection
from db.schema import init_schema
from services.enrichment.repository import get_items_needing_enrichment

logger = logging.getLogger("bws.enrichment.routes")

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


VALID_SOURCES = {"bricklink", "brickeconomy"}


class EnrichRequest(BaseModel):
    set_number: str = Field(..., min_length=1, max_length=20, pattern=r"^\d{3,6}(-\d+)?$")
    source: str | None = Field(default=None, description="Specific source to enrich from")


class EnrichBatchRequest(BaseModel):
    set_numbers: list[str] | None = Field(
        default=None,
        description="Specific set numbers to enrich. If omitted, enriches all items with missing metadata.",
    )


class EnrichBatchResponse(BaseModel):
    queued: int
    set_numbers: list[str]


class NeedsEnrichmentResponse(BaseModel):
    success: bool
    data: list[dict]
    count: int


class ScrapeTasksResponse(BaseModel):
    created: int
    set_number: str
    tasks: list[dict]


_SOURCE_TO_TASK_TYPE = {
    "bricklink": "bricklink_metadata",
    "brickeconomy": "brickeconomy",
}


@router.post("/enrich", response_model=ScrapeTasksResponse)
async def enrich_item(request: EnrichRequest) -> ScrapeTasksResponse:
    """Create scrape tasks for a single LEGO set."""
    if request.source and request.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source: {request.source}. Must be one of: {', '.join(sorted(VALID_SOURCES))}",
        )

    from services.scrape_queue.models import TaskType
    from services.scrape_queue.repository import create_task, create_tasks_for_set

    conn = get_connection()
    try:
        init_schema(conn)
        if request.source:
            task_type_str = _SOURCE_TO_TASK_TYPE.get(request.source, request.source)
            task_type = TaskType(task_type_str)
            task = create_task(conn, request.set_number, task_type)
            tasks = [task] if task else []
        else:
            tasks = create_tasks_for_set(conn, request.set_number)
    finally:
        conn.close()

    return ScrapeTasksResponse(
        created=len(tasks),
        set_number=request.set_number,
        tasks=[
            {
                "task_id": t.task_id,
                "task_type": t.task_type.value,
                "priority": t.priority,
                "status": t.status.value,
            }
            for t in tasks
        ],
    )


@router.post("/enrich-missing", response_model=EnrichBatchResponse)
async def enrich_missing(
    request: EnrichBatchRequest | None = None,
) -> EnrichBatchResponse:
    """Create scrape tasks for items with missing metadata.

    If request.set_numbers is provided, only enrich those specific sets.
    Otherwise, enrich all items with missing metadata.
    """
    from services.scrape_queue.repository import create_tasks_for_set

    conn = get_connection()
    try:
        init_schema(conn)

        if request and request.set_numbers:
            placeholders = ", ".join(["?"] * len(request.set_numbers))
            rows = conn.execute(
                f"""
                SELECT li.set_number
                FROM lego_items li
                WHERE li.set_number IN ({placeholders})
                  AND (li.title IS NULL
                    OR li.theme IS NULL
                    OR li.year_released IS NULL
                    OR li.parts_count IS NULL
                    OR li.image_url IS NULL
                    OR NOT EXISTS (
                        SELECT 1 FROM brickeconomy_snapshots bs
                        WHERE bs.set_number = li.set_number
                    )
                    OR (
                        li.title IS NOT NULL
                        AND li.year_released IS NOT NULL
                        AND NOT EXISTS (
                            SELECT 1 FROM google_trends_snapshots gts
                            WHERE gts.set_number = li.set_number
                        )
                    ))
                """,  # noqa: S608
                request.set_numbers,
            ).fetchall()
            items = [{"set_number": r[0]} for r in rows]
        else:
            items = get_items_needing_enrichment(conn, limit=10000)

        queued_numbers: list[str] = []
        for item in items:
            set_number = item["set_number"]
            tasks = create_tasks_for_set(conn, set_number)
            if tasks:
                queued_numbers.append(set_number)

    except Exception:
        logger.exception("Failed to fetch items needing enrichment")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

    return EnrichBatchResponse(queued=len(queued_numbers), set_numbers=queued_numbers)


@router.post("/scrape-missing-minifigs", response_model=EnrichBatchResponse)
async def scrape_missing_minifigs(
    request: EnrichBatchRequest | None = None,
) -> EnrichBatchResponse:
    """Create scrape tasks for items with unknown minifig_count (NULL).

    Items with minifig_count = 0 (previously scraped, no minifigs) are skipped.
    Only items with minifig_count IS NULL (never scraped) are queued.
    """
    from services.scrape_queue.models import TaskType
    from services.scrape_queue.repository import create_task

    conn = get_connection()
    try:
        init_schema(conn)

        if request and request.set_numbers:
            placeholders = ", ".join(["?"] * len(request.set_numbers))
            rows = conn.execute(
                f"SELECT set_number FROM lego_items WHERE minifig_count IS NULL AND set_number IN ({placeholders})",  # noqa: S608
                request.set_numbers,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT set_number FROM lego_items WHERE minifig_count IS NULL",
            ).fetchall()

        queued_numbers: list[str] = []
        for (set_number,) in rows:
            # Create bricklink_metadata task (which discovers minifig_count)
            task = create_task(conn, set_number, TaskType.BRICKLINK_METADATA)
            if task:
                queued_numbers.append(set_number)

    except Exception:
        logger.exception("Failed to fetch items with missing minifig_count")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

    return EnrichBatchResponse(queued=len(queued_numbers), set_numbers=queued_numbers)


@router.post("/enrich-missing-dimensions", response_model=EnrichBatchResponse)
async def enrich_missing_dimensions(
    request: EnrichBatchRequest | None = None,
) -> EnrichBatchResponse:
    """Create scrape tasks for items with missing dimensions (NULL)."""
    from services.scrape_queue.models import TaskType
    from services.scrape_queue.repository import create_task

    conn = get_connection()
    try:
        init_schema(conn)

        if request and request.set_numbers:
            placeholders = ", ".join(["?"] * len(request.set_numbers))
            rows = conn.execute(
                f"SELECT set_number FROM lego_items WHERE dimensions IS NULL AND set_number IN ({placeholders})",  # noqa: S608
                request.set_numbers,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT set_number FROM lego_items WHERE dimensions IS NULL",
            ).fetchall()

        queued_numbers: list[str] = []
        for (set_number,) in rows:
            task = create_task(conn, set_number, TaskType.BRICKLINK_METADATA)
            if task:
                queued_numbers.append(set_number)

    except Exception:
        logger.exception("Failed to fetch items with missing dimensions")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

    return EnrichBatchResponse(queued=len(queued_numbers), set_numbers=queued_numbers)


@router.get("/needs-enrichment", response_model=NeedsEnrichmentResponse)
async def list_needs_enrichment(
    limit: int = Query(default=50, ge=1, le=500),
) -> NeedsEnrichmentResponse:
    """List items that have missing metadata fields."""
    conn = get_connection()
    try:
        init_schema(conn)
        items = get_items_needing_enrichment(conn, limit=limit)
    except Exception:
        logger.exception("Failed to list items needing enrichment")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

    return NeedsEnrichmentResponse(success=True, data=items, count=len(items))


@router.get("/scrape-tasks/{set_number}")
async def get_scrape_tasks(set_number: str) -> dict:
    """Get scrape task progress for a specific set."""
    from services.scrape_queue.repository import get_tasks_for_set

    conn = get_connection()
    try:
        init_schema(conn)
        tasks = get_tasks_for_set(conn, set_number)
    finally:
        conn.close()

    return {
        "set_number": set_number,
        "tasks": [
            {
                "task_id": t.task_id,
                "task_type": t.task_type.value,
                "priority": t.priority,
                "status": t.status.value,
                "depends_on": t.depends_on,
                "attempt_count": t.attempt_count,
                "error": t.error,
                "created_at": str(t.created_at) if t.created_at else None,
                "completed_at": str(t.completed_at) if t.completed_at else None,
            }
            for t in tasks
        ],
    }


@router.get("/scrape-queue-stats")
async def scrape_queue_stats() -> dict:
    """Get overall scrape queue statistics."""
    from services.scrape_queue.repository import get_queue_stats

    conn = get_connection()
    try:
        init_schema(conn)
        stats = get_queue_stats(conn)
    finally:
        conn.close()

    return {"stats": stats}
