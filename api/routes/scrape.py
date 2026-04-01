"""Scrape API routes."""


from fastapi import APIRouter, HTTPException

from api.jobs import job_manager
from api.schemas import (
    JobStatus,
    ScrapeItemResponse,
    ScrapeJobDetailResponse,
    ScrapeJobResponse,
    ScrapeRequest,
    ScraperInfo,
    ScrapeTargetInfo,
)

router = APIRouter(prefix="/scrape", tags=["scrape"])

# Registry of available scrapers
SCRAPERS: list[ScraperInfo] = [
    ScraperInfo(
        id="shopee",
        name="Shopee Malaysia",
        description="Scrape LEGO products from Shopee.com.my shops and collections",
        targets=[
            ScrapeTargetInfo(
                id="legoshopmy",
                label="LEGO Shop MY - Full Collection",
                url="https://shopee.com.my/legoshopmy?page=0&shopCollection=258084132",
                description="Official LEGO Shop Malaysia collection on Shopee",
            )
        ],
    ),
    ScraperInfo(
        id="toysrus",
        name='Toys"R"Us Malaysia',
        description="Scrape LEGO catalog from toysrus.com.my via Demandware API",
        targets=[
            ScrapeTargetInfo(
                id="lego-catalog",
                label="LEGO Full Catalog",
                url="https://www.toysrus.com.my/lego/",
                description='Full LEGO product catalog on Toys"R"Us Malaysia',
            )
        ],
    ),
    ScraperInfo(
        id="mightyutan",
        name="Mighty Utan Malaysia",
        description="Scrape LEGO catalog from mightyutan.com.my via SiteGiant storefront",
        targets=[
            ScrapeTargetInfo(
                id="lego-catalog",
                label="LEGO Full Catalog",
                url="https://mightyutan.com.my/collection/lego-1",
                description="Full LEGO product catalog on Mighty Utan Malaysia",
            )
        ],
    ),
    ScraperInfo(
        id="shopee_saturation",
        name="Shopee Saturation Checker",
        description="Check market saturation on Shopee for items with retail pricing",
        targets=[
            ScrapeTargetInfo(
                id="batch",
                label="All Items (Batch)",
                url="batch",
                description="Check all items with RRP that haven't been checked recently",
            )
        ],
    ),
    ScraperInfo(
        id="bricklink_catalog",
        name="BrickLink Catalog List",
        description="Discover items from a BrickLink catalog list page with full pagination",
        targets=[
            ScrapeTargetInfo(
                id="sets-2020",
                label="Sets - Year 2020",
                url="https://www.bricklink.com/catalogList.asp?pg=1&itemYear=2020&catType=S&v=1",
                description="All LEGO sets from 2020 on BrickLink",
            ),
        ],
    ),
    ScraperInfo(
        id="carousell",
        name="Carousell Malaysia",
        description="Search Carousell.com.my for LEGO listings -- seller count, prices, conditions",
        targets=[
            ScrapeTargetInfo(
                id="search-example",
                label="Search by Set Number",
                url="40346",
                description="Search Carousell for a LEGO set number (e.g. 40346)",
            ),
        ],
    ),
    ScraperInfo(
        id="brickeconomy",
        name="BrickEconomy",
        description="Scrape set value history, sale trends, and metadata from BrickEconomy.com",
        targets=[
            ScrapeTargetInfo(
                id="single-set",
                label="Single Set by Number",
                url="40346-1",
                description="Scrape BrickEconomy page for a LEGO set (e.g. 40346-1)",
            ),
            ScrapeTargetInfo(
                id="batch",
                label="Portfolio & Watchlist (Batch)",
                url="batch",
                description="Scrape all portfolio and watchlist items that have no BrickEconomy snapshot yet",
            ),
        ],
    ),
    ScraperInfo(
        id="keepa",
        name="Keepa",
        description="Scrape Amazon price history from Keepa.com -- Buy Box, New, 3P FBA/FBM, Used prices",
        targets=[
            ScrapeTargetInfo(
                id="single-set",
                label="Single Set by Number",
                url="60305",
                description="Scrape Keepa price history for a LEGO set (e.g. 60305)",
            ),
        ],
    ),
]

VALID_SCRAPER_IDS = {s.id for s in SCRAPERS}


@router.get("/scrapers", response_model=list[ScraperInfo])
async def list_scrapers():
    """List all available scrapers."""
    return SCRAPERS


@router.get("/scrapers/{scraper_id}", response_model=ScraperInfo)
async def get_scraper(scraper_id: str):
    """Get a scraper by ID."""
    for s in SCRAPERS:
        if s.id == scraper_id:
            return s
    raise HTTPException(status_code=404, detail=f"Scraper not found: {scraper_id}")


@router.post("/jobs", response_model=ScrapeJobResponse)
async def start_scrape(request: ScrapeRequest):
    """Enqueue a new scrape job. Returns immediately with a job ID."""
    if request.scraper_id not in VALID_SCRAPER_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scraper: {request.scraper_id}",
        )

    if request.scraper_id == "shopee" and not request.url.startswith(
        "https://shopee.com.my/"
    ):
        raise HTTPException(
            status_code=400,
            detail="URL must be a shopee.com.my URL",
        )

    if request.scraper_id == "toysrus" and not request.url.startswith(
        "https://www.toysrus.com.my/"
    ):
        raise HTTPException(
            status_code=400,
            detail="URL must be a toysrus.com.my URL",
        )

    if request.scraper_id == "mightyutan" and not request.url.startswith(
        "https://mightyutan.com.my/"
    ):
        raise HTTPException(
            status_code=400,
            detail="URL must be a mightyutan.com.my URL",
        )

    if request.scraper_id == "shopee_saturation" and not (
        request.url == "batch" or request.url.replace("-", "").isalnum()
    ):
        raise HTTPException(
            status_code=400,
            detail='URL must be "batch" or a LEGO set number',
        )

    if request.scraper_id == "bricklink_catalog" and "catalogList.asp" not in request.url:
        raise HTTPException(
            status_code=400,
            detail="URL must be a BrickLink catalogList.asp URL",
        )

    if request.scraper_id == "brickeconomy" and not (
        request.url == "batch" or request.url.replace("-", "").isalnum()
    ):
        raise HTTPException(
            status_code=400,
            detail='URL must be "batch" or a LEGO set number',
        )

    if request.scraper_id == "carousell" and not request.url.strip():
        raise HTTPException(
            status_code=400,
            detail="Search query must not be empty",
        )

    if request.scraper_id == "keepa" and not request.url.strip().replace("-", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="URL must be a LEGO set number",
        )

    job = job_manager.create_job(request.scraper_id, request.url)
    return _job_to_response(job)


@router.delete("/jobs")
async def clear_jobs():
    """Clear all completed and failed jobs from history (both in-memory and persistent)."""
    removed = job_manager.clear_finished()

    # Also clear terminal scrape tasks
    try:
        from db.connection import get_connection
        from db.schema import init_schema

        conn = get_connection()
        try:
            init_schema(conn)
            result = conn.execute(
                "SELECT COUNT(*) FROM scrape_tasks WHERE status IN ('completed', 'failed')",
            ).fetchone()
            task_count = result[0] if result else 0
            if task_count > 0:
                conn.execute(
                    "DELETE FROM scrape_tasks WHERE status IN ('completed', 'failed')",
                )
                removed += task_count
        finally:
            conn.close()
    except Exception:
        pass

    return {"cleared": removed}


@router.get("/jobs", response_model=list[ScrapeJobResponse])
async def list_jobs(limit: int = 1000):
    """List recent scrape jobs, including persistent scrape queue tasks."""
    # In-memory jobs (Shopee, ToysRUs, BrickLink catalog, etc.)
    jobs = [_job_to_response(j) for j in job_manager.list_jobs(limit)]

    # Persistent scrape queue tasks (enrichment pipeline)
    try:
        from db.connection import get_connection
        from db.schema import init_schema

        conn = get_connection()
        try:
            init_schema(conn)
            jobs.extend(_scrape_tasks_as_jobs(conn, limit))
        finally:
            conn.close()
    except Exception:
        pass  # Graceful degradation -- show in-memory jobs even if DB fails

    return jobs


@router.get("/jobs/{job_id}", response_model=ScrapeJobDetailResponse)
async def get_job(job_id: str):
    """Get a job's status and results."""
    # Check in-memory jobs first
    job = job_manager.get_job(job_id)
    if job:
        return ScrapeJobDetailResponse(
            job_id=job.job_id,
            status=job.status,
            scraper_id=job.scraper_id,
            url=job.url,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            items_found=job.items_found,
            error=job.error,
            progress=job.progress,
            items=[ScrapeItemResponse(**item) for item in job.items],
        )

    # Check persistent scrape tasks
    try:
        from db.connection import get_connection
        from db.schema import init_schema

        conn = get_connection()
        try:
            init_schema(conn)
            tasks = _scrape_tasks_as_jobs(conn, limit=1000)
            for task_job in tasks:
                if task_job.job_id == job_id:
                    return ScrapeJobDetailResponse(
                        job_id=task_job.job_id,
                        status=task_job.status,
                        scraper_id=task_job.scraper_id,
                        url=task_job.url,
                        created_at=task_job.created_at,
                        started_at=task_job.started_at,
                        completed_at=task_job.completed_at,
                        items_found=task_job.items_found,
                        error=task_job.error,
                        progress=task_job.progress,
                        items=[],
                    )
        finally:
            conn.close()
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Job not found")


def _job_to_response(job) -> ScrapeJobResponse:
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
        progress=job.progress,
        worker_no=job.worker_no,
    )


# Map scrape task statuses to job statuses for unified display.
_TASK_STATUS_TO_JOB_STATUS = {
    "pending": JobStatus.QUEUED,
    "blocked": JobStatus.QUEUED,
    "running": JobStatus.RUNNING,
    "completed": JobStatus.COMPLETED,
    "failed": JobStatus.FAILED,
}


def _scrape_tasks_as_jobs(conn, limit: int) -> list[ScrapeJobResponse]:
    """Convert persistent scrape_tasks rows into ScrapeJobResponse for the /jobs list."""
    from datetime import datetime, timezone

    rows = conn.execute(
        """
        SELECT task_id, set_number, task_type, status, priority,
               depends_on, attempt_count, max_attempts, error,
               created_at, started_at, completed_at, locked_by
        FROM scrape_tasks
        ORDER BY
            CASE status
                WHEN 'running' THEN 0
                WHEN 'pending' THEN 1
                WHEN 'blocked' THEN 2
                WHEN 'failed' THEN 3
                WHEN 'completed' THEN 4
            END,
            priority ASC,
            created_at DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    results: list[ScrapeJobResponse] = []
    for row in rows:
        (task_id, set_number, task_type, status, priority,
         depends_on, attempt_count, max_attempts, error,
         created_at, started_at, completed_at, locked_by) = row

        job_status = _TASK_STATUS_TO_JOB_STATUS.get(status, JobStatus.QUEUED)

        # Build a progress string showing useful context
        progress_parts: list[str] = []
        if status == "blocked" and depends_on:
            progress_parts.append(f"waiting for {depends_on}")
        if attempt_count > 1:
            progress_parts.append(f"attempt {attempt_count}/{max_attempts}")
        if locked_by and status == "running":
            progress_parts.append(locked_by)
        progress = " | ".join(progress_parts) if progress_parts else None

        # Ensure datetime objects
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if not created_at:
            created_at = datetime.now(tz=timezone.utc)

        results.append(ScrapeJobResponse(
            job_id=task_id,
            status=job_status,
            scraper_id=f"scrape:{task_type}",
            url=set_number,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            items_found=1 if status == "completed" and not error else 0,
            error=error,
            progress=progress,
            worker_no=None,
        ))

    return results
