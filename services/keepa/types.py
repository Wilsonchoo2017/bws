"""Keepa data structures."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class KeepaDataPoint:
    """A single price/rank observation at a point in time."""

    date: str  # ISO "YYYY-MM-DD"
    value: int  # price in US cents, or sales rank


@dataclass(frozen=True)
class KeepaProductData:
    """All price history data for a single product."""

    set_number: str
    asin: str | None
    title: str | None
    keepa_url: str | None
    scraped_at: datetime
    # Price series
    amazon_price: tuple[KeepaDataPoint, ...] = ()
    new_price: tuple[KeepaDataPoint, ...] = ()
    new_3p_fba: tuple[KeepaDataPoint, ...] = ()
    new_3p_fbm: tuple[KeepaDataPoint, ...] = ()
    used_price: tuple[KeepaDataPoint, ...] = ()
    used_like_new: tuple[KeepaDataPoint, ...] = ()
    buy_box: tuple[KeepaDataPoint, ...] = ()
    list_price: tuple[KeepaDataPoint, ...] = ()
    warehouse_deals: tuple[KeepaDataPoint, ...] = ()
    collectible: tuple[KeepaDataPoint, ...] = ()
    sales_rank: tuple[KeepaDataPoint, ...] = ()
    # Summary stats (cents)
    current_buy_box_cents: int | None = None
    current_amazon_cents: int | None = None
    current_new_cents: int | None = None
    lowest_ever_cents: int | None = None
    highest_ever_cents: int | None = None
    # Product metadata
    rating: float | None = None
    review_count: int | None = None
    tracking_users: int | None = None
    # Chart screenshot (local file path)
    chart_screenshot_path: str | None = None


@dataclass(frozen=True)
class KeepaScrapeResult:
    """Result of a Keepa scrape operation."""

    success: bool
    set_number: str
    product_data: KeepaProductData | None = None
    error: str | None = None
