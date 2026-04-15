"""Types for Carousell competition tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.marketplace_competition.types import SaturationLevel


@dataclass(frozen=True)
class CarousellCompetitionListing:
    """A single Carousell listing captured in a competition snapshot."""

    listing_id: str
    listing_url: str
    shop_id: str | None
    seller_name: str | None
    title: str
    price_cents: int | None
    price_display: str
    condition: str | None
    image_url: str | None
    time_ago: str | None
    is_sold: bool = False
    is_reserved: bool = False
    is_delisted: bool = False


@dataclass(frozen=True)
class CarousellCompetitionSnapshot:
    """Point-in-time Carousell competition snapshot for a LEGO set.

    Note: Carousell has no per-listing sold counter, so velocity is
    derived from `flipped_to_sold_count` \u2014 the number of listings
    that transitioned from active -> sold between the previous and
    current snapshots. This is computed at save time.
    """

    set_number: str
    listings_count: int
    unique_sellers: int
    flipped_to_sold_count: int | None
    min_price_cents: int | None
    max_price_cents: int | None
    avg_price_cents: int | None
    median_price_cents: int | None
    saturation_score: float
    saturation_level: SaturationLevel
    scraped_at: datetime
    listings: tuple[CarousellCompetitionListing, ...]
