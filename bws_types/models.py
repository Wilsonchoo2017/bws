"""Data models for BWS.

All models are frozen dataclasses for immutability (pure functional style).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from bws_types.price import Cents


class WatchStatus(Enum):
    """Watch status for items being tracked."""

    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ARCHIVED = "archived"


class Condition(Enum):
    """Item condition (new vs used)."""

    NEW = "new"
    USED = "used"


class Action(Enum):
    """Investment recommendation action."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SKIP = "skip"  # Don't invest in this item


class Urgency(Enum):
    """Urgency level for investment recommendations."""

    URGENT = "urgent"
    MODERATE = "moderate"
    LOW = "low"
    NO_RUSH = "no_rush"


@dataclass(frozen=True)
class PriceData:
    """Price with currency information."""

    currency: str
    amount: Cents


@dataclass(frozen=True)
class PricingBox:
    """Pricing box data from Bricklink price guide.

    Represents one of the 4 boxes: 6-month new, 6-month used, current new, current used.
    """

    times_sold: int | None = None
    total_lots: int | None = None
    total_qty: int | None = None
    min_price: PriceData | None = None
    avg_price: PriceData | None = None
    qty_avg_price: PriceData | None = None
    max_price: PriceData | None = None


@dataclass(frozen=True)
class MinifigureInfo:
    """A minifigure found in a set's inventory."""

    minifig_id: str  # e.g., "sc139"
    name: str | None = None
    image_url: str | None = None
    quantity: int = 1


@dataclass(frozen=True)
class MinifigureData:
    """Complete minifigure with prices."""

    minifig_id: str
    name: str | None = None
    image_url: str | None = None
    year_released: int | None = None
    six_month_new: PricingBox | None = None
    six_month_used: PricingBox | None = None
    current_new: PricingBox | None = None
    current_used: PricingBox | None = None


@dataclass(frozen=True)
class BricklinkData:
    """Complete Bricklink item data from scraping."""

    item_id: str
    item_type: str
    title: str | None = None
    weight: str | None = None
    year_released: int | None = None
    image_url: str | None = None
    parts_count: int | None = None
    theme: str | None = None
    minifig_count: int | None = None
    dimensions: str | None = None
    has_instructions: bool | None = None
    six_month_new: PricingBox | None = None
    six_month_used: PricingBox | None = None
    current_new: PricingBox | None = None
    current_used: PricingBox | None = None


@dataclass(frozen=True)
class BricklinkItem:
    """Bricklink item stored in database."""

    id: int
    item_id: str
    item_type: str
    title: str | None = None
    weight: str | None = None
    year_released: int | None = None
    image_url: str | None = None
    watch_status: WatchStatus = WatchStatus.ACTIVE
    scrape_interval_days: int = 7
    next_scrape_at: datetime | None = None
    last_scraped_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class MonthlySale:
    """Monthly sales summary for an item."""

    item_id: str
    year: int
    month: int
    condition: Condition
    times_sold: int
    total_quantity: int
    min_price: PriceData | None = None
    max_price: PriceData | None = None
    avg_price: PriceData | None = None
    currency: str = "USD"


@dataclass(frozen=True)
class AnalysisScore:
    """Analysis score for a dimension."""

    value: int  # 0-100
    confidence: float  # 0-1
    reasoning: str


@dataclass(frozen=True)
class ProductRecommendation:
    """Complete product recommendation."""

    item_id: str
    overall: AnalysisScore
    action: Action
    urgency: Urgency
    risks: tuple[str, ...]
    opportunities: tuple[str, ...]
    demand_score: AnalysisScore | None = None
    availability_score: AnalysisScore | None = None
    analyzed_at: datetime | None = None


@dataclass(frozen=True)
class MultiplierResult:
    """Result from a multiplier calculator.

    Provides the multiplier value along with explanation and metadata.
    """

    multiplier: float
    explanation: str
    applied: bool = True
    data_used: tuple[tuple[str, str | int | float | None], ...] = ()


@dataclass(frozen=True)
class DemandScoreBreakdown:
    """Detailed breakdown of demand score components."""

    velocity_score: int
    momentum_score: int
    market_depth_score: int
    supply_demand_ratio_score: int
    consistency_score: int
    final_score: int
    confidence: float


@dataclass(frozen=True)
class QualityScoreBreakdown:
    """Detailed breakdown of quality score components."""

    ppd_score: int
    complexity_score: int
    theme_score: int
    scarcity_score: int
    final_score: int
    confidence: float
