"""BWS API -- FastAPI application with background worker."""


import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import enrichment, items, scrape
from api.worker import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger("bws.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background worker on app startup, stop on shutdown."""
    logger.info("Starting BWS API...")
    worker_task = asyncio.create_task(run_worker())
    logger.info("Background worker started")
    yield
    worker_task.cancel()
    try:
        await worker_task
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
