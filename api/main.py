"""BWS API -- FastAPI application with background worker."""


import asyncio
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorlog
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

# Colored console handler
_color_handler = colorlog.StreamHandler()
_color_handler.setFormatter(colorlog.ColoredFormatter(
    "%(asctime)s %(log_color)s[%(name)s] %(levelname)s%(reset)s: %(message)s",
    log_colors={
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    },
))
_color_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_color_handler],
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
    _lg = logging.getLogger(_logger_name)
    _lg.addHandler(_scrape_file_handler)
    _lg.addHandler(_color_handler)
    _lg.propagate = False

logger = logging.getLogger("bws.api")


async def _run_daily_prediction_snapshot() -> None:
    """Save ML prediction snapshot once per day on startup, then every 24h."""
    await asyncio.sleep(30)  # Wait for DB to settle after startup
    while True:
        try:
            from db.connection import get_connection
            from services.ml.prediction_tracker import backfill_actuals, save_prediction_snapshot

            conn = get_connection()
            try:
                n = save_prediction_snapshot(conn)
                backfill_actuals(conn)
                if n > 0:
                    logger.info("Daily prediction snapshot: saved %d predictions", n)
            finally:
                conn.close()
        except Exception:
            logger.warning("Prediction snapshot failed", exc_info=True)

        await asyncio.sleep(86400)  # 24 hours


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background worker and enrichment sweep on app startup."""
    from api.jobs import job_manager

    logger.info("Starting BWS API...")

    # Restore cooldown state from previous run (before dispatcher starts)
    from config.settings import restore_cooldowns
    restore_cooldowns()

    # Register scoring providers
    from services.scoring.growth_provider import growth_provider
    from services.scoring.provider import register_provider
    register_provider(growth_provider)

    # Crash recovery: reclaim stale scrape tasks before starting dispatcher
    await recover_scrape_queue()

    worker_task = asyncio.create_task(run_worker())
    sweep_task = asyncio.create_task(run_enrichment_sweep(job_manager))
    saturation_task = asyncio.create_task(run_saturation_sweep(job_manager))
    image_task = asyncio.create_task(run_image_download_sweep())
    scrape_dispatcher_task = asyncio.create_task(run_scrape_dispatcher())
    prediction_task = asyncio.create_task(_run_daily_prediction_snapshot())
    logger.info("Background worker, enrichment/saturation/image sweeps + scrape dispatcher + prediction tracker started")
    yield
    logger.info("BWS API shutting down...")
    # Persist cooldown state before tearing down workers
    from config.settings import save_cooldowns
    try:
        save_cooldowns()
    except Exception:
        logger.warning("Failed to save cooldown state", exc_info=True)
    # Everything inside _shutdown has a hard 10s ceiling
    all_tasks = [worker_task, sweep_task, saturation_task, image_task, scrape_dispatcher_task]
    try:
        await asyncio.wait_for(_shutdown(all_tasks), timeout=10)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.warning("Shutdown timed out -- force-cancelling all tasks")
        for task in all_tasks:
            task.cancel()
    # Always checkpoint, no matter what happened above
    from db.connection import get_connection
    conn = get_connection()
    try:
        conn.execute("FORCE CHECKPOINT")
        logger.info("Shutdown checkpoint completed -- WAL flushed")
    except Exception:
        logger.warning("Shutdown checkpoint FAILED -- WAL data may be at risk", exc_info=True)
    finally:
        conn.close()
    logger.info("BWS API shut down")


async def _shutdown(tasks: list[asyncio.Task]) -> None:
    """Graceful shutdown sequence with no unbounded waits."""
    # Signal dispatcher to stop after current task
    shutdown_scrape_dispatcher()
    # Force-close all persistent browsers (including OS processes)
    from services.browser import close_all_browsers
    close_all_browsers()
    # Cancel all tasks and wait for them to finish
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


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
