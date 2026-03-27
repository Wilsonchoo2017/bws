"""Scarcity multiplier calculator.

Calculates supply scarcity premium based on inventory levels.
"""

from config.value_investing import (
    SCARCITY_LIMITED_MONTHS,
    SCARCITY_MULTIPLIER_COMMON,
    SCARCITY_MULTIPLIER_LIMITED,
    SCARCITY_MULTIPLIER_RARE,
    SCARCITY_MULTIPLIER_ULTRA_RARE,
    SCARCITY_RARE_MONTHS,
    SCARCITY_ULTRA_RARE_MONTHS,
)
from types.models import MultiplierResult


def calculate_scarcity_multiplier(
    available_lots: int | None = None,
    available_qty: int | None = None,
    monthly_sales_velocity: float | None = None,
) -> MultiplierResult:
    """Calculate supply scarcity premium.

    Scarcity levels (0.95-1.10 range):
    - Ultra rare (<1 month inventory): 1.10
    - Rare (1-3 months): 1.05
    - Limited (3-6 months): 1.00
    - Common (>6 months): 0.95

    Args:
        available_lots: Number of sellers with this item
        available_qty: Total quantity available for sale
        monthly_sales_velocity: Sales per month

    Returns:
        MultiplierResult with scarcity multiplier
    """
    # Try primary method: months of inventory
    if (
        available_qty is not None
        and monthly_sales_velocity is not None
        and monthly_sales_velocity > 0
    ):
        months_inventory = available_qty / monthly_sales_velocity

        if months_inventory < SCARCITY_ULTRA_RARE_MONTHS:
            multiplier = SCARCITY_MULTIPLIER_ULTRA_RARE
            category = "Ultra rare"
        elif months_inventory < SCARCITY_RARE_MONTHS:
            multiplier = SCARCITY_MULTIPLIER_RARE
            category = "Rare"
        elif months_inventory < SCARCITY_LIMITED_MONTHS:
            multiplier = SCARCITY_MULTIPLIER_LIMITED
            category = "Limited"
        else:
            multiplier = SCARCITY_MULTIPLIER_COMMON
            category = "Common"

        explanation = f"{category}: {months_inventory:.1f} months supply"

        return MultiplierResult(
            multiplier=multiplier,
            explanation=explanation,
            applied=True,
            data_used=(
                ("available_qty", available_qty),
                ("monthly_velocity", round(monthly_sales_velocity, 2)),
                ("months_inventory", round(months_inventory, 1)),
            ),
        )

    # Fallback: lots-based scoring
    if available_lots is not None:
        if available_lots < 3:
            multiplier = SCARCITY_MULTIPLIER_ULTRA_RARE
            category = "Ultra rare"
        elif available_lots < 10:
            multiplier = SCARCITY_MULTIPLIER_RARE
            category = "Rare"
        elif available_lots < 30:
            multiplier = SCARCITY_MULTIPLIER_LIMITED
            category = "Limited"
        else:
            multiplier = SCARCITY_MULTIPLIER_COMMON
            category = "Common"

        explanation = f"{category}: {available_lots} sellers (no velocity data)"

        return MultiplierResult(
            multiplier=multiplier,
            explanation=explanation,
            applied=True,
            data_used=(("available_lots", available_lots),),
        )

    # Fallback: qty-based scoring
    if available_qty is not None:
        if available_qty < 5:
            multiplier = SCARCITY_MULTIPLIER_ULTRA_RARE
            category = "Ultra rare"
        elif available_qty < 20:
            multiplier = SCARCITY_MULTIPLIER_RARE
            category = "Rare"
        elif available_qty < 100:
            multiplier = SCARCITY_MULTIPLIER_LIMITED
            category = "Limited"
        else:
            multiplier = SCARCITY_MULTIPLIER_COMMON
            category = "Common"

        explanation = f"{category}: {available_qty} available (no velocity data)"

        return MultiplierResult(
            multiplier=multiplier,
            explanation=explanation,
            applied=True,
            data_used=(("available_qty", available_qty),),
        )

    # No data available
    return MultiplierResult(
        multiplier=1.0,
        explanation="No scarcity data available",
        applied=False,
        data_used=(),
    )
