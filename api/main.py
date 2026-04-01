"""BWS API -- FastAPI application with background worker."""


import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import enrichment, images, items, portfolio, scrape
from api.worker import run_worker
from services.enrichment.scheduler import run_enrichment_sweep
from services.images.sweep import run_image_download_sweep
from services.keepa.scheduler import run_keepa_sweep
from services.shopee.saturation_scheduler import run_saturation_sweep

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger("bws.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background worker and enrichment sweep on app startup."""
    from api.jobs import job_manager

    logger.info("Starting BWS API...")
    worker_task = asyncio.create_task(run_worker())
    sweep_task = asyncio.create_task(run_enrichment_sweep(job_manager))
    saturation_task = asyncio.create_task(run_saturation_sweep(job_manager))
    image_task = asyncio.create_task(run_image_download_sweep())
    keepa_task = asyncio.create_task(run_keepa_sweep(job_manager))
    logger.info("Background worker, enrichment/saturation/image/keepa sweeps started")
    yield
    keepa_task.cancel()
    image_task.cancel()
    saturation_task.cancel()
    sweep_task.cancel()
    worker_task.cancel()
    for task in (worker_task, sweep_task, saturation_task, image_task, keepa_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("BWS API shut down")


app = FastAPI(
    title="BWS API",
    description="Brick Watch System -- LEGO market scraping and analysis",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scrape.router, prefix="/api")
app.include_router(items.router, prefix="/api")
app.include_router(enrichment.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(images.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
