"""Volatility penalty calculator.

Calculates context-aware volatility discount based on price stability.
"""

from bws.config.value_investing import (
    VOLATILITY_MAX_DISCOUNT,
    VOLATILITY_RISK_AVERSION,
)
from bws.types.models import MultiplierResult


def calculate_volatility_penalty(
    price_volatility: float | None,
    is_retired: bool = False,
    price_trend: float | None = None,
) -> MultiplierResult:
    """Calculate context-aware volatility discount.

    Context-aware logic:
    - Retired + rising prices: NO penalty (collector demand is positive)
    - Retired + falling prices: 0.85 multiplier (panic selling risk)
    - Active set: volatility * risk_aversion, capped at 12% discount

    Args:
        price_volatility: Coefficient of variation (std/mean), or None
        is_retired: Whether the set is retired
        price_trend: Price trend (positive = rising), or None

    Returns:
        MultiplierResult with volatility multiplier (penalty)
    """
    # No volatility data
    if price_volatility is None:
        return MultiplierResult(
            multiplier=1.0,
            explanation="No volatility data available",
            applied=False,
            data_used=(("price_volatility", None),),
        )

    # Context: Retired set with rising prices - no penalty
    if is_retired and price_trend is not None and price_trend > 0:
        return MultiplierResult(
            multiplier=1.0,
            explanation="Retired with rising prices (collector demand)",
            applied=True,
            data_used=(
                ("price_volatility", round(price_volatility, 3)),
                ("is_retired", is_retired),
                ("price_trend", round(price_trend, 3)),
            ),
        )

    # Context: Retired set with falling prices - panic selling risk
    if is_retired and price_trend is not None and price_trend < -0.1:
        return MultiplierResult(
            multiplier=0.85,
            explanation="Retired with falling prices (panic selling risk)",
            applied=True,
            data_used=(
                ("price_volatility", round(price_volatility, 3)),
                ("is_retired", is_retired),
                ("price_trend", round(price_trend, 3)),
            ),
        )

    # Standard volatility penalty
    # Calculate discount: volatility * risk_aversion, capped at max_discount
    raw_discount = price_volatility * VOLATILITY_RISK_AVERSION
    discount = min(raw_discount, VOLATILITY_MAX_DISCOUNT)
    multiplier = 1.0 - discount

    # Describe volatility level
    if price_volatility < 0.1:
        volatility_desc = "Low volatility"
    elif price_volatility < 0.25:
        volatility_desc = "Moderate volatility"
    elif price_volatility < 0.5:
        volatility_desc = "High volatility"
    else:
        volatility_desc = "Very high volatility"

    explanation = f"{volatility_desc}: {price_volatility:.1%} CV"
    if discount > 0:
        explanation += f" ({discount:.1%} discount)"

    return MultiplierResult(
        multiplier=round(multiplier, 3),
        explanation=explanation,
        applied=True,
        data_used=(
            ("price_volatility", round(price_volatility, 3)),
            ("is_retired", is_retired),
            ("price_trend", round(price_trend, 3) if price_trend else None),
            ("discount_applied", round(discount, 3)),
        ),
    )
