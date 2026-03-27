"""Demand scoring service.

5-component weighted scoring system for demand analysis.
"""

from config.value_investing import DEMAND_SCORE_WEIGHTS
from bws_types.models import DemandScoreBreakdown
from bws_types.price import Cents


def _calculate_velocity_score(
    times_sold: int | None,
    total_qty_sold: int | None,
    days_in_period: int = 180,
) -> int:
    """Calculate velocity component score (0-100).

    Based on sales frequency and volume.
    """
    if times_sold is None or times_sold == 0:
        return 0

    # Sales per month
    months = days_in_period / 30
    sales_per_month = times_sold / months if months > 0 else 0

    # Volume bonus: high quantity sold adds to score
    volume_bonus = 0
    if total_qty_sold is not None:
        qty_per_month = total_qty_sold / months if months > 0 else 0
        if qty_per_month >= 100:
            volume_bonus = 10
        elif qty_per_month >= 50:
            volume_bonus = 5

    # Score based on sales frequency
    if sales_per_month >= 50:
        base = 100
    elif sales_per_month >= 20:
        base = 85
    elif sales_per_month >= 10:
        base = 70
    elif sales_per_month >= 5:
        base = 55
    elif sales_per_month >= 2:
        base = 40
    elif sales_per_month >= 1:
        base = 25
    else:
        base = 10

    return min(100, base + volume_bonus)


def _calculate_momentum_score(
    price_history: list[Cents] | None,
) -> int:
    """Calculate momentum component score (0-100).

    Based on price trend direction and strength.
    """
    if not price_history or len(price_history) < 3:
        return 50  # Neutral when insufficient data

    # Calculate trend: compare recent prices to older prices
    mid = len(price_history) // 2
    older_avg = sum(price_history[:mid]) / mid if mid > 0 else 0
    recent_avg = sum(price_history[mid:]) / (len(price_history) - mid)

    if older_avg == 0:
        return 50

    change_pct = (recent_avg - older_avg) / older_avg

    # Score based on trend
    if change_pct >= 0.20:
        return 95  # Strong upward trend
    if change_pct >= 0.10:
        return 80  # Moderate upward
    if change_pct >= 0.0:
        return 60  # Slight upward / stable
    if change_pct >= -0.10:
        return 40  # Slight downward
    if change_pct >= -0.20:
        return 25  # Moderate downward
    return 10  # Strong downward


def _calculate_market_depth_score(
    times_sold: int | None,
    total_qty_sold: int | None,
) -> int:
    """Calculate market depth component score (0-100).

    Based on total transaction count and volume.
    """
    times = times_sold or 0
    qty = total_qty_sold or 0

    # Combined depth score
    if times >= 100 and qty >= 200:
        return 95
    if times >= 50 and qty >= 100:
        return 80
    if times >= 25 and qty >= 50:
        return 65
    if times >= 10 and qty >= 20:
        return 50
    if times >= 5:
        return 35
    if times >= 1:
        return 20
    return 5


def _calculate_supply_demand_ratio_score(
    total_qty_sold: int | None,
    available_qty: int | None,
    available_lots: int | None,
) -> int:
    """Calculate supply/demand ratio component score (0-100).

    Based on ratio of sold quantity to available quantity,
    with seller concentration as a secondary factor.
    """
    sold = total_qty_sold or 0
    available = available_qty or 0
    lots = available_lots or 0

    if sold == 0:
        return 25  # No demand signal

    if available == 0:
        return 95  # All sold out

    ratio = sold / available

    # Seller concentration bonus: fewer sellers = tighter supply
    concentration_bonus = 0
    if lots > 0 and lots < 5:
        concentration_bonus = 5
    elif lots > 0 and lots < 10:
        concentration_bonus = 2

    # Higher ratio = more demand relative to supply
    if ratio >= 5.0:
        base = 95
    elif ratio >= 2.0:
        base = 80
    elif ratio >= 1.0:
        base = 65
    elif ratio >= 0.5:
        base = 50
    elif ratio >= 0.2:
        base = 35
    else:
        base = 20

    return min(100, base + concentration_bonus)


def _calculate_consistency_score(
    days_between_sales: list[float] | None,
) -> int:
    """Calculate consistency component score (0-100).

    Based on regularity of sales (low variance = high consistency).
    """
    if not days_between_sales or len(days_between_sales) < 2:
        return 50  # Neutral when insufficient data

    avg = sum(days_between_sales) / len(days_between_sales)
    if avg == 0:
        return 95  # Instant sales

    # Calculate coefficient of variation
    variance = sum((d - avg) ** 2 for d in days_between_sales) / len(days_between_sales)
    std = variance**0.5
    cv = std / avg if avg > 0 else 0

    # Lower CV = more consistent
    if cv < 0.3:
        return 90
    if cv < 0.5:
        return 75
    if cv < 0.8:
        return 60
    if cv < 1.2:
        return 45
    return 30


def calculate_demand_score(
    times_sold: int | None = None,
    total_qty_sold: int | None = None,
    available_qty: int | None = None,
    available_lots: int | None = None,
    price_history: list[Cents] | None = None,
    days_between_sales: list[float] | None = None,
) -> DemandScoreBreakdown:
    """Calculate 5-component demand score with breakdown.

    Components and weights:
    - Velocity: 30% - Sales frequency
    - Momentum: 25% - Price trend
    - Market depth: 20% - Transaction volume
    - Supply/demand ratio: 15% - Demand vs supply
    - Consistency: 10% - Sales regularity

    Args:
        times_sold: Number of sales transactions
        total_qty_sold: Total quantity sold
        available_qty: Current quantity available
        available_lots: Number of sellers
        price_history: List of historical prices (oldest first)
        days_between_sales: List of days between consecutive sales

    Returns:
        DemandScoreBreakdown with component scores and final score
    """
    # Calculate component scores
    velocity_score = _calculate_velocity_score(times_sold, total_qty_sold)
    momentum_score = _calculate_momentum_score(price_history)
    market_depth_score = _calculate_market_depth_score(times_sold, total_qty_sold)
    supply_demand_score = _calculate_supply_demand_ratio_score(
        total_qty_sold, available_qty, available_lots
    )
    consistency_score = _calculate_consistency_score(days_between_sales)

    # Calculate weighted final score
    weights = DEMAND_SCORE_WEIGHTS
    final_score = int(
        velocity_score * weights.velocity
        + momentum_score * weights.momentum
        + market_depth_score * weights.market_depth
        + supply_demand_score * weights.supply_demand_ratio
        + consistency_score * weights.consistency
    )

    # Calculate confidence based on data availability
    data_points = sum(
        [
            times_sold is not None,
            total_qty_sold is not None,
            available_qty is not None,
            price_history is not None and len(price_history) >= 3,
            days_between_sales is not None and len(days_between_sales) >= 2,
        ]
    )
    confidence = min(1.0, data_points / 5)

    return DemandScoreBreakdown(
        velocity_score=velocity_score,
        momentum_score=momentum_score,
        market_depth_score=market_depth_score,
        supply_demand_ratio_score=supply_demand_score,
        consistency_score=consistency_score,
        final_score=final_score,
        confidence=confidence,
    )
