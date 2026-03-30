"""Types for Shopee market saturation analysis."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SaturationLevel(Enum):
    """Market saturation classification based on Shopee listing count."""

    VERY_LOW = "very_low"    # <10 listings -- good opportunity
    LOW = "low"              # 10-19 listings
    MODERATE = "moderate"    # 20-47 listings
    HIGH = "high"            # 48+ listings -- highly saturated


@dataclass(frozen=True)
class SaturationSnapshot:
    """Point-in-time saturation measurement for a LEGO set on Shopee."""

    set_number: str
    listings_count: int
    unique_sellers: int
    min_price_cents: int | None
    max_price_cents: int | None
    avg_price_cents: int | None
    median_price_cents: int | None
    price_spread_pct: float | None
    saturation_score: float
    saturation_level: SaturationLevel
    search_query: str
    scraped_at: datetime


@dataclass(frozen=True)
class SaturationBatchResult:
    """Result of a batch saturation check across multiple sets."""

    total_items: int
    successful: int
    failed: int
    skipped: int
    snapshots: tuple[SaturationSnapshot, ...]
    errors: tuple[tuple[str, str], ...]  # (set_number, error_msg)
