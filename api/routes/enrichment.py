"""Enrichment API routes."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.jobs import job_manager
from api.schemas import ScrapeJobResponse
from db.connection import get_connection
from db.schema import init_schema
from services.enrichment.repository import get_items_needing_enrichment

logger = logging.getLogger("bws.enrichment.routes")

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


VALID_SOURCES = {"bricklink", "brickranker"}


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


@router.post("/enrich", response_model=ScrapeJobResponse)
async def enrich_item(request: EnrichRequest) -> ScrapeJobResponse:
    """Queue an enrichment job for a single LEGO set."""
    if request.source and request.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source: {request.source}. Must be one of: {', '.join(sorted(VALID_SOURCES))}",
        )

    # Encode source into job URL: "75192" or "75192:bricklink"
    job_url = request.set_number
    if request.source:
        job_url = f"{request.set_number}:{request.source}"

    job = job_manager.create_job("enrichment", job_url)
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
async def enrich_missing(
    request: EnrichBatchRequest | None = None,
) -> EnrichBatchResponse:
    """Enrich items with missing metadata.

    If request.set_numbers is provided, only enrich those specific sets.
    Otherwise, enrich all items with missing metadata.
    """
    conn = get_connection()
    try:
        init_schema(conn)

        if request and request.set_numbers:
            # Enrich specific sets -- skip the price_records filter
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
                    OR li.image_url IS NULL)
                """,  # noqa: S608
                request.set_numbers,
            ).fetchall()
            items = [{"set_number": r[0]} for r in rows]
        else:
            items = get_items_needing_enrichment(conn, limit=10000)
    except Exception:
        logger.exception("Failed to fetch items needing enrichment")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()

    queued_numbers: list[str] = []
    for item in items:
        set_number = item["set_number"]
        job_manager.create_job("enrichment", set_number)
        queued_numbers.append(set_number)

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
