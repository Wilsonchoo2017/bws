"""Parts-per-dollar (PPD) multiplier calculator.

Calculates quality multiplier based on parts value ratio.
"""

from config.value_investing import (
    PPD_EXCELLENT,
    PPD_FAIR,
    PPD_GOOD,
    PPD_MULTIPLIER_EXCELLENT,
    PPD_MULTIPLIER_FAIR,
    PPD_MULTIPLIER_GOOD,
    PPD_MULTIPLIER_POOR,
)
from types.models import MultiplierResult
from types.price import Cents, cents_to_dollars


def calculate_ppd_multiplier(
    parts_count: int | None,
    msrp_cents: Cents | None,
) -> MultiplierResult:
    """Calculate parts-per-dollar quality multiplier.

    PPD thresholds:
    - Excellent (>10 PPD): 1.10
    - Good (8-10 PPD): 1.05
    - Fair (6-8 PPD): 1.00
    - Poor (<6 PPD): 0.95

    Args:
        parts_count: Number of parts in the set
        msrp_cents: MSRP in cents

    Returns:
        MultiplierResult with PPD multiplier
    """
    # Missing data
    if parts_count is None or msrp_cents is None:
        return MultiplierResult(
            multiplier=1.0,
            explanation="Missing parts count or MSRP",
            applied=False,
            data_used=(
                ("parts_count", parts_count),
                ("msrp_cents", msrp_cents),
            ),
        )

    # Avoid division by zero
    if msrp_cents <= 0:
        return MultiplierResult(
            multiplier=1.0,
            explanation="Invalid MSRP (zero or negative)",
            applied=False,
            data_used=(
                ("parts_count", parts_count),
                ("msrp_cents", msrp_cents),
            ),
        )

    # Calculate PPD
    msrp_dollars = cents_to_dollars(msrp_cents)
    ppd = parts_count / msrp_dollars

    # Determine multiplier and category
    if ppd >= PPD_EXCELLENT:
        multiplier = PPD_MULTIPLIER_EXCELLENT
        category = "Excellent"
    elif ppd >= PPD_GOOD:
        multiplier = PPD_MULTIPLIER_GOOD
        category = "Good"
    elif ppd >= PPD_FAIR:
        multiplier = PPD_MULTIPLIER_FAIR
        category = "Fair"
    else:
        multiplier = PPD_MULTIPLIER_POOR
        category = "Poor"

    explanation = f"{category} parts value: {ppd:.1f} PPD"

    return MultiplierResult(
        multiplier=multiplier,
        explanation=explanation,
        applied=True,
        data_used=(
            ("parts_count", parts_count),
            ("msrp_dollars", round(msrp_dollars, 2)),
            ("ppd", round(ppd, 2)),
        ),
    )
