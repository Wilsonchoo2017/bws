"""Core value calculation functions.

Implements intrinsic value calculation based on Pabrai's value investing principles.
"""

from config.value_investing import (
    BASE_PRICE_AVG_WEIGHT,
    BASE_PRICE_MAX_WEIGHT,
    GATE_DEAD_VELOCITY,
    GATE_MAX_INVENTORY_MONTHS,
    GATE_MIN_DEMAND_SCORE,
    GATE_MIN_QUALITY_SCORE,
    MARGIN_DEFAULT,
    MARGIN_HIGH_CONFIDENCE,
    MARGIN_LOW_CONFIDENCE,
    MAX_ONLY_DISCOUNT,
    MULTIPLIER_MAX_BOUND,
    MULTIPLIER_MIN_BOUND,
)
from services.calculators import (
    calculate_liquidity_multiplier,
    calculate_ppd_multiplier,
    calculate_retirement_multiplier,
    calculate_saturation_multiplier,
    calculate_scarcity_multiplier,
    calculate_theme_multiplier,
    calculate_volatility_penalty,
)
from services.value_investing.types import ValueBreakdown, ValueInputs
from bws_types.models import MultiplierResult
from bws_types.price import Cents


def calculate_base_value(inputs: ValueInputs) -> tuple[Cents, str]:
    """Determine base value from best available source.

    Priority:
    1. MSRP (most reliable)
    2. Current retail price
    3. Bricklink weighted avg/max

    Args:
        inputs: ValueInputs with pricing data

    Returns:
        Tuple of (base_value_cents, source_description)
    """
    # Priority 1: MSRP
    if inputs.msrp is not None and inputs.msrp > 0:
        return inputs.msrp, "msrp"

    # Priority 2: Current retail
    if inputs.current_retail_price is not None and inputs.current_retail_price > 0:
        return inputs.current_retail_price, "retail"

    # Priority 3: Bricklink prices
    if inputs.bricklink_avg_price is not None and inputs.bricklink_max_price is not None:
        # Weighted average of avg and max
        weighted = int(
            inputs.bricklink_avg_price * BASE_PRICE_AVG_WEIGHT
            + inputs.bricklink_max_price * BASE_PRICE_MAX_WEIGHT
        )
        return Cents(weighted), "bricklink_weighted"

    if inputs.bricklink_avg_price is not None:
        return inputs.bricklink_avg_price, "bricklink_avg"

    if inputs.bricklink_max_price is not None:
        # Apply discount when only max is available
        discounted = int(inputs.bricklink_max_price * MAX_ONLY_DISCOUNT)
        return Cents(discounted), "bricklink_max_discounted"

    # No price data available
    return Cents(0), "none"


def apply_sanity_bounds(value: Cents, base_value: Cents) -> Cents:
    """Clamp value to 0.30x - 3.50x of base.

    Prevents extreme valuations that are likely errors.

    Args:
        value: Calculated intrinsic value
        base_value: Base value used for calculation

    Returns:
        Clamped value
    """
    if base_value <= 0:
        return value

    min_value = int(base_value * MULTIPLIER_MIN_BOUND)
    max_value = int(base_value * MULTIPLIER_MAX_BOUND)

    return Cents(max(min_value, min(max_value, value)))


def check_hard_gates(inputs: ValueInputs) -> tuple[bool, str | None]:
    """Check Pabrai's "Too Hard Pile" gates.

    Reject sets that fail any gate:
    - Quality score < 40
    - Demand score < 40
    - Dead velocity (< 0.033 sales/day)
    - Over 24 months inventory

    Args:
        inputs: ValueInputs to check

    Returns:
        Tuple of (passed, rejection_reason)
    """
    # Gate 1: Quality score
    if inputs.quality_score is not None and inputs.quality_score < GATE_MIN_QUALITY_SCORE:
        return False, f"Quality score too low ({inputs.quality_score} < {GATE_MIN_QUALITY_SCORE})"

    # Gate 2: Demand score
    if inputs.demand_score is not None and inputs.demand_score < GATE_MIN_DEMAND_SCORE:
        return False, f"Demand score too low ({inputs.demand_score} < {GATE_MIN_DEMAND_SCORE})"

    # Gate 3: Dead velocity
    if inputs.sales_velocity is not None and inputs.sales_velocity < GATE_DEAD_VELOCITY:
        return False, f"Dead market (velocity {inputs.sales_velocity:.3f} < {GATE_DEAD_VELOCITY})"

    # Gate 4: Oversaturated inventory
    if (
        inputs.available_qty is not None
        and inputs.sales_velocity is not None
        and inputs.sales_velocity > 0
    ):
        monthly_velocity = inputs.sales_velocity * 30
        if monthly_velocity > 0:
            months_inventory = inputs.available_qty / monthly_velocity
            if months_inventory > GATE_MAX_INVENTORY_MONTHS:
                return (
                    False,
                    f"Oversaturated ({months_inventory:.0f} months > {GATE_MAX_INVENTORY_MONTHS})",
                )

    return True, None


def _score_to_multiplier(score: int | None, min_mult: float, max_mult: float) -> float:
    """Convert 0-100 score to multiplier range."""
    if score is None:
        return 1.0
    # Linear interpolation: 0 -> min_mult, 100 -> max_mult
    normalized = max(0, min(100, score)) / 100
    return min_mult + normalized * (max_mult - min_mult)


def _calculate_margin_of_safety(inputs: ValueInputs) -> float:
    """Calculate margin of safety based on data confidence."""
    # Count available data points
    data_points = sum(
        [
            inputs.msrp is not None,
            inputs.bricklink_avg_price is not None,
            inputs.times_sold is not None,
            inputs.quality_score is not None,
            inputs.demand_score is not None,
            inputs.theme is not None,
            inputs.parts_count is not None,
        ]
    )

    if data_points >= 6:
        return MARGIN_HIGH_CONFIDENCE
    if data_points >= 4:
        return MARGIN_DEFAULT
    return MARGIN_LOW_CONFIDENCE


def calculate_intrinsic_value(inputs: ValueInputs) -> ValueBreakdown:
    """Calculate intrinsic value with full breakdown.

    Formula:
    intrinsic_value = base_price
        * retirement_multiplier
        * theme_multiplier
        * ppd_multiplier
        * quality_multiplier (0.9-1.1 from 0-100 score)
        * demand_multiplier (0.85-1.15 from 0-100 score)
        * scarcity_multiplier
        * liquidity_multiplier
        * volatility_multiplier
        * saturation_multiplier

    Then apply sanity bounds (0.30x to 3.50x base).

    Args:
        inputs: ValueInputs with all calculation data

    Returns:
        ValueBreakdown with full calculation breakdown
    """
    # Step 1: Get base value
    base_value, base_source = calculate_base_value(inputs)

    # Step 2: Check hard gates
    passed, rejection_reason = check_hard_gates(inputs)

    # Step 3: Calculate all multipliers
    is_retired = inputs.years_post_retirement is not None

    retirement_mult = calculate_retirement_multiplier(
        inputs.years_post_retirement,
        inputs.demand_score,
    )

    theme_mult = calculate_theme_multiplier(inputs.theme)

    ppd_mult = calculate_ppd_multiplier(inputs.parts_count, inputs.msrp)

    # Score-based multipliers
    quality_mult_value = _score_to_multiplier(inputs.quality_score, 0.90, 1.10)
    quality_mult = MultiplierResult(
        multiplier=quality_mult_value,
        explanation=f"Quality score: {inputs.quality_score or 'N/A'}",
        applied=inputs.quality_score is not None,
        data_used=(("quality_score", inputs.quality_score),),
    )

    demand_mult_value = _score_to_multiplier(inputs.demand_score, 0.85, 1.15)
    demand_mult = MultiplierResult(
        multiplier=demand_mult_value,
        explanation=f"Demand score: {inputs.demand_score or 'N/A'}",
        applied=inputs.demand_score is not None,
        data_used=(("demand_score", inputs.demand_score),),
    )

    # Calculate monthly velocity for inventory-based multipliers
    monthly_velocity = None
    if inputs.sales_velocity is not None:
        monthly_velocity = inputs.sales_velocity * 30

    scarcity_mult = calculate_scarcity_multiplier(
        inputs.available_lots,
        inputs.available_qty,
        monthly_velocity,
    )

    liquidity_mult = calculate_liquidity_multiplier(inputs.sales_velocity)

    volatility_mult = calculate_volatility_penalty(
        inputs.price_volatility,
        is_retired,
        inputs.price_trend,
    )

    saturation_mult = calculate_saturation_multiplier(
        inputs.available_qty,
        inputs.available_lots,
        monthly_velocity,
    )

    # Step 4: Calculate total multiplier
    total_multiplier = (
        retirement_mult.multiplier
        * theme_mult.multiplier
        * ppd_mult.multiplier
        * quality_mult.multiplier
        * demand_mult.multiplier
        * scarcity_mult.multiplier
        * liquidity_mult.multiplier
        * volatility_mult.multiplier
        * saturation_mult.multiplier
    )

    # Step 5: Calculate intrinsic value
    if base_value > 0:
        raw_intrinsic = int(base_value * total_multiplier)
        intrinsic_value = apply_sanity_bounds(Cents(raw_intrinsic), base_value)
    else:
        intrinsic_value = Cents(0)

    # Step 6: Calculate margin and buy price
    margin = _calculate_margin_of_safety(inputs)
    recommended_buy = Cents(int(intrinsic_value * (1 - margin)))

    return ValueBreakdown(
        base_value=base_value,
        base_value_source=base_source,
        retirement_mult=retirement_mult,
        theme_mult=theme_mult,
        ppd_mult=ppd_mult,
        quality_mult=quality_mult,
        demand_mult=demand_mult,
        scarcity_mult=scarcity_mult,
        liquidity_mult=liquidity_mult,
        volatility_mult=volatility_mult,
        saturation_mult=saturation_mult,
        intrinsic_value=intrinsic_value,
        total_multiplier=round(total_multiplier, 3),
        recommended_buy_price=recommended_buy,
        margin_of_safety=margin,
        rejected=not passed,
        rejection_reason=rejection_reason,
    )
