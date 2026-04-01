"""Google Trends data structures."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TrendsDataPoint:
    """A single interest observation at a point in time."""

    date: str  # ISO "YYYY-MM-DD"
    value: int  # 0-100 interest index


@dataclass(frozen=True)
class TrendsData:
    """Interest-over-time data for a single LEGO set."""

    set_number: str
    keyword: str  # e.g. "LEGO 31113"
    search_property: str  # "youtube"
    geo: str  # "" = worldwide
    timeframe_start: str  # "2021-01-01"
    timeframe_end: str  # "2026-04-01"
    interest_over_time: tuple[TrendsDataPoint, ...]
    peak_value: int | None
    peak_date: str | None
    average_value: float | None
    scraped_at: datetime


@dataclass(frozen=True)
class TrendsScrapeResult:
    """Result of a Google Trends scrape operation."""

    success: bool
    set_number: str
    data: TrendsData | None = None
    error: str | None = None
