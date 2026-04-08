"""Types for Shopee competition tracking."""

from dataclasses import dataclass
from datetime import datetime

from services.shopee.saturation_types import SaturationLevel


@dataclass(frozen=True)
class CompetitionListing:
    """A single competitor listing snapshot."""

    product_url: str
    shop_id: str
    title: str
    price_cents: int | None
    price_display: str
    sold_count_raw: str | None
    sold_count_numeric: int | None
    rating: str | None
    image_url: str | None
    is_sold_out: bool = False
    is_delisted: bool = False
    discovery_method: str = "search"


@dataclass(frozen=True)
class CompetitionSnapshot:
    """Point-in-time competition measurement for a LEGO set on Shopee."""

    set_number: str
    listings_count: int
    unique_sellers: int
    total_sold_count: int | None
    min_price_cents: int | None
    max_price_cents: int | None
    avg_price_cents: int | None
    median_price_cents: int | None
    saturation_score: float
    saturation_level: SaturationLevel
    scraped_at: datetime
    listings: tuple[CompetitionListing, ...]


@dataclass(frozen=True)
class CompetitionBatchResult:
    """Result of a batch competition check across multiple sets."""

    total_items: int
    successful: int
    failed: int
    skipped: int
    errors: tuple[tuple[str, str], ...]
