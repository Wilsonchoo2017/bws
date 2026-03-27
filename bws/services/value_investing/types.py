"""Value investing type definitions.

Dataclasses for value calculation inputs and outputs.
"""

from dataclasses import dataclass

from bws.types.models import MultiplierResult
from bws.types.price import Cents


@dataclass(frozen=True)
class ValueInputs:
    """All inputs for intrinsic value calculation."""

    # Pricing (in cents)
    msrp: Cents | None = None
    current_retail_price: Cents | None = None
    bricklink_avg_price: Cents | None = None
    bricklink_max_price: Cents | None = None

    # Market data
    sales_velocity: float | None = None
    times_sold: int | None = None
    total_qty_sold: int | None = None
    available_qty: int | None = None
    available_lots: int | None = None

    # Scores
    quality_score: int | None = None
    demand_score: int | None = None

    # Metadata
    theme: str | None = None
    parts_count: int | None = None
    years_post_retirement: int | None = None

    # Market dynamics
    price_volatility: float | None = None
    price_trend: float | None = None


@dataclass(frozen=True)
class ValueBreakdown:
    """Complete breakdown of intrinsic value calculation."""

    # Base value
    base_value: Cents
    base_value_source: str  # "msrp", "retail", "bricklink"

    # Quality multipliers
    retirement_mult: MultiplierResult
    theme_mult: MultiplierResult
    ppd_mult: MultiplierResult

    # Score-based multipliers
    quality_mult: MultiplierResult
    demand_mult: MultiplierResult

    # Supply multipliers
    scarcity_mult: MultiplierResult

    # Risk discounts
    liquidity_mult: MultiplierResult
    volatility_mult: MultiplierResult
    saturation_mult: MultiplierResult

    # Final values
    intrinsic_value: Cents
    total_multiplier: float
    recommended_buy_price: Cents
    margin_of_safety: float

    # Rejection info
    rejected: bool = False
    rejection_reason: str | None = None
