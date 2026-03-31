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

    job = job_manager.create_job(request.scraper_id, request.url)
    return _job_to_response(job)


@router.delete("/jobs")
async def clear_jobs():
    """Clear all completed and failed jobs from history."""
    removed = job_manager.clear_finished()
    return {"cleared": removed}


@router.get("/jobs", response_model=list[ScrapeJobResponse])
async def list_jobs(limit: int = 1000):
    """List recent scrape jobs."""
    return [_job_to_response(j) for j in job_manager.list_jobs(limit)]


@router.get("/jobs/{job_id}", response_model=ScrapeJobDetailResponse)
async def get_job(job_id: str):
    """Get a job's status and results."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

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
    )
