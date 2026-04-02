"""BWS API -- FastAPI application with background worker."""


import asyncio
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import enrichment, images, items, ml, portfolio, scrape
from api.worker import run_worker
from services.enrichment.scheduler import run_enrichment_sweep
from services.images.sweep import run_image_download_sweep
from services.scrape_queue.dispatcher import recover_scrape_queue, run_scrape_dispatcher, shutdown_scrape_dispatcher
from services.shopee.saturation_scheduler import run_saturation_sweep

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
)

# Persist logs to rotating file (10 MB per file, keep 5 backups)
_file_handler = RotatingFileHandler(
    _LOG_DIR / "bws.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setLevel(logging.WARNING)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
logging.getLogger().addHandler(_file_handler)

# Bricklink and scrape-queue logs at INFO level to file (track success/failure)
_scrape_file_handler = RotatingFileHandler(
    _LOG_DIR / "bws.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_scrape_file_handler.setLevel(logging.INFO)
_scrape_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
for _logger_name in ("bws.bricklink", "bws.scrape_queue.dispatcher", "bws.scrape_queue.executor"):
    logging.getLogger(_logger_name).addHandler(_scrape_file_handler)

logger = logging.getLogger("bws.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background worker and enrichment sweep on app startup."""
    from api.jobs import job_manager

    logger.info("Starting BWS API...")

    # Crash recovery: reclaim stale scrape tasks before starting dispatcher
    await recover_scrape_queue()

    worker_task = asyncio.create_task(run_worker())
    sweep_task = asyncio.create_task(run_enrichment_sweep(job_manager))
    saturation_task = asyncio.create_task(run_saturation_sweep(job_manager))
    image_task = asyncio.create_task(run_image_download_sweep())
    scrape_dispatcher_task = asyncio.create_task(run_scrape_dispatcher())
    logger.info("Background worker, enrichment/saturation/image sweeps + scrape dispatcher started")
    yield
    logger.info("BWS API shutting down...")
    # Signal dispatcher workers to finish current task and stop
    shutdown_scrape_dispatcher()
    # Cancel all background tasks
    tasks = [worker_task, sweep_task, saturation_task, image_task, scrape_dispatcher_task]
    for task in tasks:
        task.cancel()
    # Wait for all tasks to finish with a timeout
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for task, result in zip(tasks, results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            logger.warning("Task %s raised during shutdown: %s", task.get_name(), result)
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
app.include_router(ml.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
