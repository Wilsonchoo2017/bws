"""Retirement multiplier calculator.

Calculates J-curve retirement premium based on years since retirement.
"""

from config.value_investing import (
    GATE_MIN_DEMAND_SCORE,
    RETIREMENT_MULTIPLIERS,
)
from bws_types.models import MultiplierResult


def calculate_retirement_multiplier(
    years_post_retirement: int | None,
    demand_score: int | None = None,
) -> MultiplierResult:
    """Calculate J-curve retirement premium.

    Demand-gated: requires score >= 40 for full premium.

    Retirement multiplier curve:
    - 0-1 years: 0.95 (initial discount - market oversupply)
    - 1-2 years: 1.00 (baseline)
    - 2-5 years: 1.15 (growth phase)
    - 5-10 years: 1.40 (maturity)
    - 10+ years: 2.00 (collector premium)

    Args:
        years_post_retirement: Years since set retired, or None if still active
        demand_score: Optional demand score (0-100) to gate premium

    Returns:
        MultiplierResult with retirement multiplier
    """
    # Active set - no retirement premium
    if years_post_retirement is None:
        return MultiplierResult(
            multiplier=1.0,
            explanation="Active set (no retirement premium)",
            applied=False,
            data_used=(("years_post_retirement", None),),
        )

    # Determine base multiplier from J-curve
    if years_post_retirement < 1:
        multiplier = RETIREMENT_MULTIPLIERS.year_0_1
        phase = "Initial discount (0-1 years)"
    elif years_post_retirement < 2:
        multiplier = RETIREMENT_MULTIPLIERS.year_1_2
        phase = "Baseline (1-2 years)"
    elif years_post_retirement < 5:
        multiplier = RETIREMENT_MULTIPLIERS.year_2_5
        phase = "Growth phase (2-5 years)"
    elif years_post_retirement < 10:
        multiplier = RETIREMENT_MULTIPLIERS.year_5_10
        phase = "Maturity (5-10 years)"
    else:
        multiplier = RETIREMENT_MULTIPLIERS.year_10_plus
        phase = "Collector premium (10+ years)"

    # Gate premium by demand score - reduce premium if demand is weak
    if demand_score is not None and demand_score < GATE_MIN_DEMAND_SCORE and multiplier > 1.0:
        reduction = (multiplier - 1.0) * 0.5
        multiplier = 1.0 + reduction
        phase = f"{phase} (reduced: weak demand)"

    explanation = f"Retired {years_post_retirement}yr - {phase}"

    return MultiplierResult(
        multiplier=multiplier,
        explanation=explanation,
        applied=True,
        data_used=(
            ("years_post_retirement", years_post_retirement),
            ("demand_score", demand_score),
        ),
    )
