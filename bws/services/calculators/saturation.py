"""Saturation multiplier calculator.

Calculates market saturation multiplier based on months of inventory.
"""

from bws.config.value_investing import (
    SATURATION_MONTHS_DISCOUNT,
    SATURATION_MONTHS_NEUTRAL,
    SATURATION_MONTHS_PREMIUM,
    SATURATION_MULTIPLIER_MAX,
    SATURATION_MULTIPLIER_MIN,
)
from bws.types.models import MultiplierResult


def _interpolate(value: float, low: float, high: float, low_mult: float, high_mult: float) -> float:
    """Linear interpolation between two points."""
    if high == low:
        return low_mult
    ratio = (value - low) / (high - low)
    return low_mult + ratio * (high_mult - low_mult)


def calculate_saturation_multiplier(
    available_qty: int | None = None,
    available_lots: int | None = None,
    monthly_sales_velocity: float | None = None,
) -> MultiplierResult:
    """Calculate market saturation multiplier.

    Primary method: Months of inventory = qty / monthly_velocity
    - <3 months: 1.05 (premium - limited supply)
    - 3-12 months: 1.00 (neutral)
    - 12-24 months: interpolate to 0.50
    - >24 months: 0.50 (heavy discount - oversaturated)

    Fallback: qty + lots scoring if no velocity data.

    Args:
        available_qty: Total quantity available for sale
        available_lots: Number of sellers with this item
        monthly_sales_velocity: Sales per month

    Returns:
        MultiplierResult with saturation multiplier
    """
    # Try primary method: months of inventory
    if (
        available_qty is not None
        and monthly_sales_velocity is not None
        and monthly_sales_velocity > 0
    ):
        months_inventory = available_qty / monthly_sales_velocity

        if months_inventory < SATURATION_MONTHS_PREMIUM:
            multiplier = SATURATION_MULTIPLIER_MAX
            category = "Limited supply"
        elif months_inventory < SATURATION_MONTHS_NEUTRAL:
            multiplier = _interpolate(
                months_inventory,
                SATURATION_MONTHS_PREMIUM,
                SATURATION_MONTHS_NEUTRAL,
                SATURATION_MULTIPLIER_MAX,
                1.0,
            )
            category = "Normal supply"
        elif months_inventory < SATURATION_MONTHS_DISCOUNT:
            multiplier = _interpolate(
                months_inventory,
                SATURATION_MONTHS_NEUTRAL,
                SATURATION_MONTHS_DISCOUNT,
                1.0,
                SATURATION_MULTIPLIER_MIN,
            )
            category = "Elevated supply"
        else:
            multiplier = SATURATION_MULTIPLIER_MIN
            category = "Oversaturated"

        explanation = f"{category}: {months_inventory:.1f} months inventory"

        return MultiplierResult(
            multiplier=round(multiplier, 3),
            explanation=explanation,
            applied=True,
            data_used=(
                ("available_qty", available_qty),
                ("monthly_velocity", round(monthly_sales_velocity, 2)),
                ("months_inventory", round(months_inventory, 1)),
            ),
        )

    # Fallback: qty + lots scoring
    if available_qty is not None or available_lots is not None:
        qty = available_qty or 0
        lots = available_lots or 0

        # Simple heuristic based on qty and lots
        if qty < 10 and lots < 5:
            multiplier = SATURATION_MULTIPLIER_MAX
            category = "Very limited"
        elif qty < 50 and lots < 20:
            multiplier = 1.0
            category = "Normal availability"
        elif qty < 200 and lots < 50:
            multiplier = 0.90
            category = "Good availability"
        elif qty < 500:
            multiplier = 0.75
            category = "High availability"
        else:
            multiplier = SATURATION_MULTIPLIER_MIN
            category = "Oversaturated"

        explanation = f"{category}: {qty} qty, {lots} lots (no velocity data)"

        return MultiplierResult(
            multiplier=multiplier,
            explanation=explanation,
            applied=True,
            data_used=(
                ("available_qty", qty),
                ("available_lots", lots),
            ),
        )

    # No data available
    return MultiplierResult(
        multiplier=1.0,
        explanation="No saturation data available",
        applied=False,
        data_used=(),
    )
