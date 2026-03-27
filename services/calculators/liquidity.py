"""Liquidity multiplier calculator.

Calculates liquidity multiplier based on sales velocity.
"""

from config.value_investing import (
    LIQUIDITY_MULTIPLIER_MAX,
    LIQUIDITY_MULTIPLIER_MIN,
    LIQUIDITY_VELOCITY_DEAD,
    LIQUIDITY_VELOCITY_HIGH,
    LIQUIDITY_VELOCITY_LOW,
    LIQUIDITY_VELOCITY_MEDIUM,
)
from types.models import MultiplierResult


def _interpolate(value: float, low: float, high: float, low_mult: float, high_mult: float) -> float:
    """Linear interpolation between two points."""
    if high == low:
        return low_mult
    ratio = (value - low) / (high - low)
    return low_mult + ratio * (high_mult - low_mult)


def calculate_liquidity_multiplier(
    sales_velocity: float | None = None,
    avg_days_between_sales: float | None = None,
) -> MultiplierResult:
    """Calculate liquidity multiplier based on sales velocity.

    Sales velocity thresholds (sales per day):
    - HIGH (0.5/day = 15+/month): 1.10
    - MEDIUM (0.1/day = 3+/month): 1.00
    - LOW (0.033/day = 1/month): 0.80
    - DEAD (0.01/day = <1/3 months): 0.60

    Linear interpolation between thresholds.

    Args:
        sales_velocity: Sales per day, or None
        avg_days_between_sales: Average days between sales (alternative input)

    Returns:
        MultiplierResult with liquidity multiplier
    """
    # Convert avg_days_between_sales to velocity if provided
    if sales_velocity is None and avg_days_between_sales is not None:
        if avg_days_between_sales > 0:
            sales_velocity = 1.0 / avg_days_between_sales
        else:
            sales_velocity = LIQUIDITY_VELOCITY_HIGH  # Instant sales

    # No data available
    if sales_velocity is None:
        return MultiplierResult(
            multiplier=1.0,
            explanation="No liquidity data available",
            applied=False,
            data_used=(("sales_velocity", None),),
        )

    # Calculate multiplier based on velocity thresholds
    if sales_velocity >= LIQUIDITY_VELOCITY_HIGH:
        multiplier = LIQUIDITY_MULTIPLIER_MAX
        category = "High liquidity"
    elif sales_velocity >= LIQUIDITY_VELOCITY_MEDIUM:
        multiplier = _interpolate(
            sales_velocity,
            LIQUIDITY_VELOCITY_MEDIUM,
            LIQUIDITY_VELOCITY_HIGH,
            1.0,
            LIQUIDITY_MULTIPLIER_MAX,
        )
        category = "Medium-high liquidity"
    elif sales_velocity >= LIQUIDITY_VELOCITY_LOW:
        multiplier = _interpolate(
            sales_velocity,
            LIQUIDITY_VELOCITY_LOW,
            LIQUIDITY_VELOCITY_MEDIUM,
            0.80,
            1.0,
        )
        category = "Low-medium liquidity"
    elif sales_velocity >= LIQUIDITY_VELOCITY_DEAD:
        multiplier = _interpolate(
            sales_velocity,
            LIQUIDITY_VELOCITY_DEAD,
            LIQUIDITY_VELOCITY_LOW,
            LIQUIDITY_MULTIPLIER_MIN,
            0.80,
        )
        category = "Low liquidity"
    else:
        multiplier = LIQUIDITY_MULTIPLIER_MIN
        category = "Dead market"

    # Format velocity for display
    sales_per_month = sales_velocity * 30
    explanation = f"{category}: {sales_per_month:.1f} sales/month"

    return MultiplierResult(
        multiplier=round(multiplier, 3),
        explanation=explanation,
        applied=True,
        data_used=(
            ("sales_velocity", round(sales_velocity, 4)),
            ("sales_per_month", round(sales_per_month, 1)),
        ),
    )
