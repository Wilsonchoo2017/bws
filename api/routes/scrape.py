"""Scrape API routes."""


import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from api.jobs import job_manager
from api.schemas import (
    JobStatus,
    ScrapeAttemptResponse,
    ScrapeItemResponse,
    ScrapeJobDetailResponse,
    ScrapeJobResponse,
    ScrapeJobsResponse,
    ScrapeQueueStats,
    ScrapeRequest,
    ScrapeSnapshotInfo,
    ScraperInfo,
    ScrapeTargetInfo,
)

logger = logging.getLogger("bws.api.scrape")

router = APIRouter(prefix="/scrape", tags=["scrape"])

# Registry of available scrapers
SCRAPERS: list[ScraperInfo] = [
    # -- Retail --
    ScraperInfo(
        id="shopee",
        name="Shopee Malaysia",
        category="retail",
        description="Scrape LEGO products from Shopee.com.my shops and collections",
        targets=[
            ScrapeTargetInfo(
                id="legoshopmy",
                label="LEGO Shop MY",
                url="https://shopee.com.my/legoshopmy",
                description="Official LEGO Shop Malaysia on Shopee",
            ),
            ScrapeTargetInfo(
                id="brickssmart",
                label="Bricks Smart",
                url="https://shopee.com.my/brickssmart",
                description="Bricks Smart LEGO shop on Shopee",
            ),
            ScrapeTargetInfo(
                id="brickandblock",
                label="Brick and Block",
                url="https://shopee.com.my/brick.and.block",
                description="Brick and Block LEGO shop on Shopee",
            ),
        ],
    ),
    ScraperInfo(
        id="toysrus",
        name='Toys"R"Us Malaysia',
        category="retail",
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
        category="retail",
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
        id="hobbydigi",
        name="HobbyDigi Malaysia",
        category="retail",
        description="Scrape LEGO catalog from hobbydigi.com/my via Camoufox browser (Magento)",
        targets=[
            ScrapeTargetInfo(
                id="lego-catalog",
                label="LEGO Full Catalog",
                url="https://www.hobbydigi.com/my/lego",
                description="Full LEGO product catalog on HobbyDigi Malaysia",
            )
        ],
    ),
    # -- Market Analysis --
    ScraperInfo(
        id="shopee_saturation",
        name="Shopee Saturation Checker",
        category="market",
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
        id="shopee_competition",
        name="Shopee Competition Tracker",
        category="market",
        description="Track competing sellers on Shopee for portfolio items",
        targets=[
            ScrapeTargetInfo(
                id="batch",
                label="All Portfolio Items (Batch)",
                url="batch",
                description="Check all portfolio holdings that haven't been checked recently",
            )
        ],
    ),
    ScraperInfo(
        id="carousell",
        name="Carousell Malaysia",
        category="marketplace",
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
    # -- Reference Data --
    ScraperInfo(
        id="bricklink_catalog",
        name="BrickLink Catalog List",
        category="reference",
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
        id="brickeconomy",
        name="BrickEconomy",
        category="reference",
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
        category="reference",
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

    if request.scraper_id == "hobbydigi" and not request.url.startswith(
        "https://www.hobbydigi.com/my/"
    ):
        raise HTTPException(
            status_code=400,
            detail="URL must be a hobbydigi.com/my URL",
        )

    if request.scraper_id == "shopee_saturation" and not (
        request.url == "batch" or request.url.replace("-", "").isalnum()
    ):
        raise HTTPException(
            status_code=400,
            detail='URL must be "batch" or a LEGO set number',
        )

    if request.scraper_id == "shopee_competition" and not (
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

    job = job_manager.create_job(request.scraper_id, request.url, reason="manual")
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


@router.get("/jobs", response_model=ScrapeJobsResponse)
async def list_jobs(limit: int = 10000):
    """List recent scrape jobs, including persistent scrape queue tasks.

    Returns jobs (paginated by LIMIT) and accurate queue stats
    computed directly from the DB (not affected by the LIMIT).
    """
    # In-memory jobs (Shopee, ToysRUs, BrickLink catalog, etc.)
    jobs = [_job_to_response(j) for j in job_manager.list_jobs(limit)]
    stats = ScrapeQueueStats()

    # Persistent scrape queue tasks (enrichment pipeline)
    try:
        from db.connection import get_connection
        from db.schema import init_schema
        from services.scrape_queue.repository import get_queue_stats

        conn = get_connection()
        try:
            init_schema(conn)
            jobs.extend(_scrape_tasks_as_jobs(conn, limit))

            # Compute accurate stats from DB (not affected by LIMIT)
            raw_stats = get_queue_stats(conn)
            stats = ScrapeQueueStats(
                total=sum(raw_stats.values()),
                queued=raw_stats.get("pending", 0) + raw_stats.get("blocked", 0),
                running=raw_stats.get("running", 0),
                completed=raw_stats.get("completed", 0),
                failed=raw_stats.get("failed", 0),
            )
        finally:
            conn.close()
    except Exception:
        pass  # Graceful degradation -- show in-memory jobs even if DB fails

    # Add in-memory job stats
    for job in job_manager.list_jobs(limit):
        stats.total += 1
        if job.status == JobStatus.QUEUED:
            stats.queued += 1
        elif job.status == JobStatus.RUNNING:
            stats.running += 1
        elif job.status == JobStatus.COMPLETED:
            stats.completed += 1
        elif job.status == JobStatus.FAILED:
            stats.failed += 1

    return ScrapeJobsResponse(jobs=jobs, stats=stats)


@router.get("/jobs/{job_id}", response_model=ScrapeJobDetailResponse)
async def get_job(job_id: str):
    """Get a job's status and results, including attempt history and snapshots."""
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
            return _get_scrape_task_detail(conn, job_id)
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Job not found")


def _get_scrape_task_detail(conn, job_id: str) -> ScrapeJobDetailResponse:
    """Build a detailed response for a persistent scrape task."""
    from datetime import datetime, timezone

    from services.scrape_queue.repository import COLUMNS_SQL, TASK_COLUMNS, row_to_task

    row = conn.execute(
        f"SELECT {COLUMNS_SQL} FROM scrape_tasks WHERE task_id = ?",  # noqa: S608
        [job_id],
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    task = row_to_task(row, TASK_COLUMNS)

    job_status = _TASK_STATUS_TO_JOB_STATUS.get(task.status.value, JobStatus.QUEUED)

    created_at = task.created_at
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if not created_at:
        created_at = datetime.now(tz=timezone.utc)

    # Attempt history
    attempt_rows = conn.execute(
        """SELECT attempt_number, error_category, error_message,
                  duration_seconds, created_at
           FROM scrape_task_attempts
           WHERE task_id = ?
           ORDER BY created_at ASC""",
        [job_id],
    ).fetchall()
    attempts = [
        ScrapeAttemptResponse(
            attempt_number=a[0],
            error_category=a[1],
            error_message=a[2],
            duration_seconds=a[3],
            created_at=a[4],
        )
        for a in attempt_rows
    ]

    # Snapshot data collected for this set_number by this task_type
    snapshots = _get_snapshots_for_task(conn, task.set_number, task.task_type.value)

    # Duration from latest attempt
    duration_ms = None
    if attempt_rows:
        last_dur = attempt_rows[-1][3]
        if last_dur is not None:
            duration_ms = int(last_dur * 1000)

    return ScrapeJobDetailResponse(
        job_id=task.task_id,
        status=job_status,
        scraper_id=f"scrape:{task.task_type.value}",
        url=task.set_number,
        created_at=created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        items_found=1 if task.status.value == "completed" and not task.error else 0,
        error=task.error,
        progress=None,
        reason=task.reason or "scheduled",
        outcome=task.outcome,
        duration_ms=duration_ms,
        source=task.source,
        items=[],
        attempts=attempts,
        snapshots=snapshots,
        set_number=task.set_number,
        task_type=task.task_type.value,
        attempt_count=task.attempt_count,
        max_attempts=task.max_attempts,
        depends_on=task.depends_on,
        locked_by=task.locked_by,
    )


def _get_snapshots_for_task(
    conn, set_number: str, task_type: str,
) -> list[ScrapeSnapshotInfo]:
    """Fetch the most recent snapshot(s) collected for this set by the task type."""
    snapshots: list[ScrapeSnapshotInfo] = []

    if task_type == "bricklink_metadata":
        # BrickLink item metadata
        row = conn.execute(
            "SELECT last_scraped_at FROM bricklink_items WHERE set_number = ? "
            "ORDER BY last_scraped_at DESC NULLS LAST LIMIT 1",
            [set_number],
        ).fetchone()
        if row and row[0]:
            snapshots.append(ScrapeSnapshotInfo(
                source="BrickLink item metadata", scraped_at=row[0],
            ))

        # Price history
        row = conn.execute(
            "SELECT scraped_at FROM bricklink_price_history "
            "WHERE set_number = ? ORDER BY scraped_at DESC LIMIT 1",
            [set_number],
        ).fetchone()
        if row and row[0]:
            snapshots.append(ScrapeSnapshotInfo(
                source="BrickLink price history", scraped_at=row[0],
            ))

        # Monthly sales
        row = conn.execute(
            "SELECT MAX(scraped_at) FROM bricklink_monthly_sales WHERE set_number = ?",
            [set_number],
        ).fetchone()
        if row and row[0]:
            snapshots.append(ScrapeSnapshotInfo(
                source="BrickLink monthly sales", scraped_at=row[0],
            ))

        # Store listings
        row = conn.execute(
            "SELECT scraped_at, COUNT(*) FROM bricklink_store_listings "
            "WHERE set_number = ? GROUP BY scraped_at ORDER BY scraped_at DESC LIMIT 1",
            [set_number],
        ).fetchone()
        if row and row[0]:
            snapshots.append(ScrapeSnapshotInfo(
                source="BrickLink store listings", scraped_at=row[0],
                summary=f"{row[1]} listings",
            ))

    elif task_type == "brickeconomy":
        row = conn.execute(
            "SELECT scraped_at, value_new_cents, value_used_cents "
            "FROM brickeconomy_snapshots WHERE set_number = ? "
            "ORDER BY scraped_at DESC LIMIT 1",
            [set_number],
        ).fetchone()
        if row and row[0]:
            parts = []
            if row[1] is not None:
                parts.append(f"new=${row[1]/100:.0f}")
            if row[2] is not None:
                parts.append(f"used=${row[2]/100:.0f}")
            snapshots.append(ScrapeSnapshotInfo(
                source="BrickEconomy snapshot", scraped_at=row[0],
                summary=", ".join(parts) if parts else None,
            ))

    elif task_type == "keepa":
        row = conn.execute(
            "SELECT scraped_at, asin, title "
            "FROM keepa_snapshots WHERE set_number = ? "
            "ORDER BY scraped_at DESC LIMIT 1",
            [set_number],
        ).fetchone()
        if row and row[0]:
            parts = []
            if row[1]:
                parts.append(f"ASIN: {row[1]}")
            snapshots.append(ScrapeSnapshotInfo(
                source="Keepa snapshot", scraped_at=row[0],
                summary=", ".join(parts) if parts else None,
            ))

    elif task_type == "minifigures":
        row = conn.execute(
            "SELECT COUNT(*), MAX(scraped_at) FROM set_minifigures WHERE set_number = ?",
            [set_number],
        ).fetchone()
        if row and row[1]:
            snapshots.append(ScrapeSnapshotInfo(
                source="Minifigures", scraped_at=row[1],
                summary=f"{row[0]} minifigures",
            ))

    elif task_type in ("google_trends", "google_trends_theme"):
        row = conn.execute(
            "SELECT scraped_at, peak_value, average_value "
            "FROM google_trends_snapshots WHERE set_number = ? "
            "ORDER BY scraped_at DESC LIMIT 1",
            [set_number],
        ).fetchone()
        if row and row[0]:
            parts = []
            if row[1] is not None:
                parts.append(f"peak={row[1]}")
            if row[2] is not None:
                parts.append(f"avg={row[2]:.1f}")
            snapshots.append(ScrapeSnapshotInfo(
                source="Google Trends", scraped_at=row[0],
                summary=", ".join(parts) if parts else None,
            ))

    return snapshots


def _job_to_response(job) -> ScrapeJobResponse:
    last = job_manager.find_last_similar(job.scraper_id, job.url)
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
        reason=job.reason,
        last_run_at=last.completed_at if last else None,
        last_run_status=last.status.value if last else None,
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
    from services.scrape_queue.repository import COLUMNS_SQL, TASK_COLUMNS, row_to_task

    rows = conn.execute(
        f"""
        SELECT {COLUMNS_SQL}
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
        """,  # noqa: S608
        [limit],
    ).fetchall()

    tasks = [row_to_task(r, TASK_COLUMNS) for r in rows]

    # Batch-fetch latest attempt duration for each task
    task_ids = [t.task_id for t in tasks]
    attempt_durations: dict[str, float] = {}
    if task_ids:
        placeholders = ", ".join("?" for _ in task_ids)
        dur_rows = conn.execute(
            f"SELECT DISTINCT ON (task_id) task_id, duration_seconds "  # noqa: S608
            f"FROM scrape_task_attempts "
            f"WHERE task_id IN ({placeholders}) "
            "ORDER BY task_id, created_at DESC",
            task_ids,
        ).fetchall()
        for dr in dur_rows:
            if dr[1] is not None:
                attempt_durations[dr[0]] = dr[1]

    # Batch-fetch last completed run for each (set_number, task_type) pair
    last_runs: dict[tuple[str, str], tuple[object, str]] = {}
    if tasks:
        last_run_rows = conn.execute(
            """
            SELECT DISTINCT ON (set_number, task_type)
                   set_number, task_type, completed_at, status
            FROM scrape_tasks
            WHERE status IN ('completed', 'failed')
              AND completed_at IS NOT NULL
            ORDER BY set_number, task_type, completed_at DESC
            """,
        ).fetchall()
        for lr_row in last_run_rows:
            last_runs[(lr_row[0], lr_row[1])] = (lr_row[2], lr_row[3])

    results: list[ScrapeJobResponse] = []
    for task in tasks:
        status = task.status.value
        task_type = task.task_type.value
        last_duration = attempt_durations.get(task.task_id)

        job_status = _TASK_STATUS_TO_JOB_STATUS.get(status, JobStatus.QUEUED)

        # Build a progress string showing useful context
        progress_parts: list[str] = []
        if status == "blocked" and task.depends_on:
            progress_parts.append(f"waiting for {task.depends_on}")
        if task.attempt_count > 1:
            progress_parts.append(f"attempt {task.attempt_count}/{task.max_attempts}")
        if task.locked_by and status == "running":
            progress_parts.append(task.locked_by)
        progress = " | ".join(progress_parts) if progress_parts else None

        # Ensure datetime objects
        created_at = task.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if not created_at:
            created_at = datetime.now(tz=timezone.utc)

        # Last similar run
        last_run = last_runs.get((task.set_number, task_type))
        last_run_at = last_run[0] if last_run else None
        last_run_status_raw = last_run[1] if last_run else None
        last_run_status = (
            _TASK_STATUS_TO_JOB_STATUS.get(last_run_status_raw, JobStatus.QUEUED).value
            if last_run_status_raw
            else None
        )
        # Don't show "last run" pointing to the current task itself
        if last_run_at == task.completed_at and status in ("completed", "failed"):
            last_run_at = None
            last_run_status = None

        duration_ms = (
            int(last_duration * 1000) if last_duration is not None else None
        )

        results.append(ScrapeJobResponse(
            job_id=task.task_id,
            status=job_status,
            scraper_id=f"scrape:{task_type}",
            url=task.set_number,
            created_at=created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            items_found=1 if status == "completed" and not task.error else 0,
            error=task.error,
            progress=progress,
            worker_no=None,
            reason=task.reason or "scheduled",
            last_run_at=last_run_at,
            last_run_status=last_run_status,
            outcome=task.outcome,
            duration_ms=duration_ms,
            source=task.source,
        ))

    return results


# ---------------------------------------------------------------------------
# Shopee captcha verification routes
# ---------------------------------------------------------------------------

class CaptchaEventResponse(BaseModel):
    id: int
    job_id: str | None = None
    source_url: str
    snapshot_dir: str
    detection_reason: str
    detection_signals: dict | None = None
    detected_at: str


class CaptchaEventsListResponse(BaseModel):
    events: list[CaptchaEventResponse]


def _event_to_response(ev) -> "CaptchaEventResponse":
    def _iso(dt):
        return dt.isoformat() if dt else None
    return CaptchaEventResponse(
        id=ev.id,
        job_id=ev.job_id,
        source_url=ev.source_url,
        snapshot_dir=ev.snapshot_dir,
        detection_reason=ev.detection_reason,
        detection_signals=ev.detection_signals,
        detected_at=_iso(ev.detected_at) or "",
    )


@router.get(
    "/shopee/captcha-events",
    response_model=CaptchaEventsListResponse,
)
async def list_captcha_events(limit: int = 50):
    """List recent Shopee captcha events, newest first."""
    from db.connection import get_connection
    from db.schema import init_schema
    from services.shopee.captcha_events import list_events

    conn = get_connection()
    init_schema(conn)
    try:
        rows = list_events(conn, limit=limit)
    finally:
        conn.close()
    return CaptchaEventsListResponse(
        events=[_event_to_response(r) for r in rows],
    )


@router.get(
    "/shopee/captcha-events/{event_id}",
    response_model=CaptchaEventResponse,
)
async def get_captcha_event(event_id: int):
    """Fetch a single captcha event row."""
    from db.connection import get_connection
    from db.schema import init_schema
    from services.shopee.captcha_events import get_event

    conn = get_connection()
    init_schema(conn)
    try:
        ev = get_event(conn, event_id)
    finally:
        conn.close()
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_to_response(ev)


_ALLOWED_SNAPSHOT_FILES = {"meta.json", "page.html", "screenshot.png"}


@router.get("/shopee/captcha-events/{event_id}/snapshot/{file_name}")
async def get_captcha_snapshot_file(event_id: int, file_name: str):
    """Serve a file from the event's snapshot directory (sanitized)."""
    if file_name not in _ALLOWED_SNAPSHOT_FILES:
        raise HTTPException(status_code=400, detail="Invalid snapshot file")

    from db.connection import get_connection
    from db.schema import init_schema
    from services.shopee.captcha_detection import SNAPSHOT_DIR
    from services.shopee.captcha_events import get_event

    conn = get_connection()
    init_schema(conn)
    try:
        ev = get_event(conn, event_id)
    finally:
        conn.close()
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")

    snap_path = (SNAPSHOT_DIR / ev.snapshot_dir).resolve()
    # Security: snap_path MUST live under SNAPSHOT_DIR
    try:
        snap_path.relative_to(SNAPSHOT_DIR.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid snapshot path") from e

    target = snap_path / file_name
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"{file_name} not found")

    media_types = {
        "meta.json": "application/json",
        "page.html": "text/html; charset=utf-8",
        "screenshot.png": "image/png",
    }
    return FileResponse(str(target), media_type=media_types[file_name])


# ---------------------------------------------------------------------------
# Shopee captcha clearance routes
# ---------------------------------------------------------------------------


class ClearanceStatusResponse(BaseModel):
    valid: bool
    cleared_at: str | None = None
    expires_at: str | None = None
    remaining_seconds: int | None = None
    method: str | None = None


class SolveStatusResponse(BaseModel):
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    clearance_id: int | None = None
    captcha_detected: bool = False


@router.get(
    "/shopee/captcha-clearance/status",
    response_model=ClearanceStatusResponse,
)
async def get_clearance_status():
    """Check whether a valid captcha clearance exists."""
    from db.connection import get_connection
    from db.schema import init_schema
    from services.shopee.captcha_clearance import get_clearance_status as _get_status

    conn = get_connection()
    init_schema(conn)
    try:
        return _get_status(conn)
    finally:
        conn.close()


@router.post("/shopee/captcha-clearance/solve")
async def start_captcha_solve():
    """Launch a browser session for proactive captcha solving.

    Returns immediately.  The browser opens non-headless so the user can
    interact with any captcha challenge.  Poll /solve-status to track
    progress.
    """
    from services.shopee.captcha_solver import (
        SolverStatus,
        get_solver_state,
        reset_solver_state,
        start_solve_session,
    )

    state = get_solver_state()
    if state.status in (
        SolverStatus.LAUNCHING,
        SolverStatus.WAITING_FOR_USER,
        SolverStatus.VERIFYING,
    ):
        return {"status": state.status.value, "message": "Session already in progress"}

    # Reset from any previous completed/failed state
    if state.status in (SolverStatus.COMPLETED, SolverStatus.FAILED):
        reset_solver_state()

    task = asyncio.create_task(start_solve_session())
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return {"status": "launching", "message": "Browser session starting..."}


@router.get(
    "/shopee/captcha-clearance/solve-status",
    response_model=SolveStatusResponse,
)
async def get_solve_status():
    """Poll the captcha solver's current state."""
    from services.shopee.captcha_solver import get_solver_state

    state = get_solver_state()
    return SolveStatusResponse(
        status=state.status.value,
        started_at=state.started_at.isoformat() if state.started_at else None,
        completed_at=state.completed_at.isoformat() if state.completed_at else None,
        error=state.error,
        clearance_id=state.clearance_id,
        captcha_detected=state.captcha_detected,
    )
