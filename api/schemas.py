"""Pydantic models for API request/response."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScrapeRequest(BaseModel):
    scraper_id: str
    url: str


class ScrapeJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    scraper_id: str
    url: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    items_found: int = 0
    error: str | None = None
    progress: str | None = None
    worker_no: int | None = None


class ScrapeItemResponse(BaseModel):
    title: str
    price_display: str
    sold_count: str | None = None
    rating: str | None = None
    shop_name: str | None = None
    product_url: str | None = None
    image_url: str | None = None


class ScrapeJobDetailResponse(ScrapeJobResponse):
    items: list[ScrapeItemResponse] = []


class ScraperInfo(BaseModel):
    id: str
    name: str
    description: str
    targets: list["ScrapeTargetInfo"]


class ScrapeTargetInfo(BaseModel):
    id: str
    label: str
    url: str
    description: str
