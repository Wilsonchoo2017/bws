"""Enrichment API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.jobs import job_manager
from api.schemas import ScrapeJobResponse
from db.connection import get_connection
from db.schema import init_schema
from services.enrichment.repository import get_items_needing_enrichment

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


class EnrichRequest(BaseModel):
    set_number: str


class EnrichBatchResponse(BaseModel):
    queued: int
    set_numbers: list[str]


@router.post("/enrich", response_model=ScrapeJobResponse)
async def enrich_item(request: EnrichRequest):
    """Queue an enrichment job for a single LEGO set."""
    job = job_manager.create_job("enrichment", request.set_number)
    return ScrapeJobResponse(
        job_id=job.job_id,
        status=job.status,
        scraper_id=job.scraper_id,
        url=job.url,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        items_found=job.items_found,
        error=job.error,
    )


@router.post("/enrich-missing", response_model=EnrichBatchResponse)
async def enrich_missing(limit: int = 20):
    """Scan for items with missing metadata and queue enrichment jobs."""
    try:
        conn = get_connection()
        init_schema(conn)
        items = get_items_needing_enrichment(conn, limit=limit)
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    queued_numbers: list[str] = []
    for item in items:
        set_number = item["set_number"]
        job_manager.create_job("enrichment", set_number)
        queued_numbers.append(set_number)

    return EnrichBatchResponse(queued=len(queued_numbers), set_numbers=queued_numbers)


@router.get("/needs-enrichment")
async def list_needs_enrichment(limit: int = 50):
    """List items that have missing metadata fields."""
    try:
        conn = get_connection()
        init_schema(conn)
        items = get_items_needing_enrichment(conn, limit=limit)
        conn.close()
        return {"success": True, "data": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
