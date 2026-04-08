"""BWS API -- FastAPI application with background worker."""


import asyncio
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import enrichment, images, items, listing, ml, portfolio, scrape, settings, stats
from api.worker import run_worker
from services.brickeconomy.analysis_scheduler import run_analysis_sweep
from services.enrichment.scheduler import run_enrichment_sweep, run_priority_rescrape_sweep, run_retiring_soon_sweep
from services.images.sweep import run_image_download_sweep
from services.keepa.scheduler import run_keepa_sweep
from services.scrape_queue.dispatcher import recover_scrape_queue, run_scrape_dispatcher, shutdown_scrape_dispatcher
from services.shopee.competition_scheduler import run_competition_sweep
from services.shopee.saturation_scheduler import run_saturation_sweep

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Colored console handler (safe at import time -- console only)
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

logger = logging.getLogger("bws.api")

_file_logging_configured = False


def _setup_file_logging() -> None:
    """Attach file handlers for production logging.

    Called once during app lifespan startup so that ``import api.main``
    in tests never writes to the production log file.
    """
    global _file_logging_configured
    if _file_logging_configured:
        return
    _file_logging_configured = True

    _LOG_DIR.mkdir(exist_ok=True)

    # Persist logs to rotating file (10 MB per file, keep 5 backups)
    file_handler = RotatingFileHandler(
        _LOG_DIR / "bws.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)

    # Bricklink and scrape-queue logs at INFO level to file (track success/failure)
    scrape_file_handler = RotatingFileHandler(
        _LOG_DIR / "bws.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    scrape_file_handler.setLevel(logging.INFO)
    scrape_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    for logger_name in ("bws.bricklink", "bws.scrape_queue.dispatcher", "bws.scrape_queue.executor"):
        lg = logging.getLogger(logger_name)
        lg.addHandler(scrape_file_handler)
        lg.addHandler(_color_handler)
        lg.propagate = False


def _sync_warm_growth_models() -> None:
    """Load models and pre-compute predictions -- runs in background thread."""
    from services.scoring.growth_provider import growth_provider

    growth_provider.warm_cache()

    # Pre-warm signals cache so first /items load is fast
    try:
        from db.connection import get_connection
        from services.backtesting.screener import compute_all_signals_with_cohort
        from services.scoring.provider import enrich_signals
        from api.routes.items import _signals_cache, _SIGNALS_TTL
        import time

        conn = get_connection()
        try:
            signals = compute_all_signals_with_cohort(conn, condition="new")
            signals = enrich_signals(signals, conn)
            from api.serialization import sanitize_nan
            _signals_cache["new"] = {
                "data": sanitize_nan(signals),
                "expires": time.time() + _SIGNALS_TTL,
            }
            logger.info("Signals cache warmed (%d items)", len(signals))
        finally:
            conn.close()
    except Exception:
        logger.warning("Signals cache warmup failed", exc_info=True)


def _sync_prediction_snapshot() -> int | None:
    """Run prediction snapshot (CPU-heavy) -- called from executor."""
    from db.connection import get_connection
    from services.ml.prediction_tracker import backfill_actuals, save_prediction_snapshot

    conn = get_connection()
    try:
        n = save_prediction_snapshot(conn)
        backfill_actuals(conn)
        return n
    finally:
        conn.close()


async def _run_daily_prediction_snapshot() -> None:
    """Save ML prediction snapshot once per day on startup, then every 24h."""
    await asyncio.sleep(30)  # Wait for DB to settle after startup
    loop = asyncio.get_running_loop()
    while True:
        try:
            n = await loop.run_in_executor(None, _sync_prediction_snapshot)
            if n and n > 0:
                logger.info("Daily prediction snapshot: saved %d predictions", n)
        except Exception:
            logger.warning("Prediction snapshot failed", exc_info=True)

        await asyncio.sleep(86400)  # 24 hours


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background worker and enrichment sweep on app startup."""
    _setup_file_logging()

    from api.jobs import job_manager

    logger.info("Starting BWS API...")

    # Restore cooldown state from previous run (before dispatcher starts)
    from config.settings import restore_cooldowns
    restore_cooldowns()

    # Load runtime settings (applies saved overrides to live objects)
    from config.runtime_settings import runtime_settings
    runtime_settings.load()

    # Register scoring providers
    from services.scoring.growth_provider import growth_provider
    from services.scoring.provider import register_provider
    register_provider(growth_provider)

    # Crash recovery: reclaim stale scrape tasks before starting dispatcher
    await recover_scrape_queue()

    worker_task = asyncio.create_task(run_worker())
    sweep_task = asyncio.create_task(run_enrichment_sweep(job_manager))
    saturation_task = asyncio.create_task(run_saturation_sweep(job_manager))
    competition_task = asyncio.create_task(run_competition_sweep(job_manager))
    image_task = asyncio.create_task(run_image_download_sweep())
    scrape_dispatcher_task = asyncio.create_task(run_scrape_dispatcher())
    prediction_task = asyncio.create_task(_run_daily_prediction_snapshot())
    keepa_task = asyncio.create_task(run_keepa_sweep(job_manager))
    rescrape_task = asyncio.create_task(run_priority_rescrape_sweep())
    retiring_soon_task = asyncio.create_task(run_retiring_soon_sweep())
    analysis_sweep_task = asyncio.create_task(run_analysis_sweep())

    # Eagerly warm growth models in a background thread so scraping isn't
    # blocked when the first score_all() call arrives.
    async def _warm_models() -> None:
        try:
            await asyncio.to_thread(_sync_warm_growth_models)
            logger.info("Growth model cache warmed")
        except Exception:
            logger.warning("Growth model warmup failed (will retry on first use)", exc_info=True)

    asyncio.create_task(_warm_models())

    logger.info("Background worker, enrichment/saturation/image/keepa sweeps + scrape dispatcher + prediction tracker started")
    yield
    logger.info("BWS API shutting down...")
    # Persist cooldown state before tearing down workers
    from config.settings import save_cooldowns
    try:
        save_cooldowns()
    except Exception:
        logger.warning("Failed to save cooldown state", exc_info=True)
    # Everything inside _shutdown has a hard 10s ceiling
    all_tasks = [worker_task, sweep_task, saturation_task, image_task, scrape_dispatcher_task, keepa_task, rescrape_task, prediction_task, retiring_soon_task, analysis_sweep_task]
    try:
        await asyncio.wait_for(_shutdown(all_tasks), timeout=10)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.warning("Shutdown timed out -- force-cancelling all tasks")
        for task in all_tasks:
            task.cancel()
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
app.include_router(stats.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(listing.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
