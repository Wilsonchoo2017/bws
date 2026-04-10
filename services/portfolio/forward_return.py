"""Forward annual return calculation and decision engine.

Pure calculation logic with no database dependencies.
Uses the formula: forward_return = (expected_future / current)^(1/years) - 1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

logger = logging.getLogger("bws.forward_return")


@dataclass(frozen=True)
class ForwardReturnInput:
    """All data needed to calculate forward return for a single set."""

    set_number: str
    cost_basis_cents: int | None  # FIFO cost basis (for holdings)
    acquisition_price_cents: int | None  # best retail price (for candidates)
    market_price_cents: int  # current BL new market price
    bricklink_new_cents: int | None  # BL secondary market exit price
    be_future_estimate_cents: int | None
    be_future_estimate_date: str | None  # ISO date or "YYYY-MM"
    be_annual_growth_pct: float | None
    be_value_new_cents: int | None
    ml_growth_pct: float | None
    ml_confidence: str | None
    ml_avoid_probability: float | None
    year_retired: int | None
    retiring_soon: bool
    is_held: bool
    # BrickLink 6-month trend data
    bl_6mo_avg_price_cents: int | None  # qty_avg_price from six_month_new
    bl_current_avg_price_cents: int | None  # qty_avg_price from current_new
    bl_6mo_times_sold: int | None  # liquidity: number of sales in 6 months


@dataclass(frozen=True)
class ForwardReturnResult:
    """Result of forward return calculation with decision."""

    set_number: str
    forward_annual_return: float | None
    expected_future_price_cents: int | None
    current_price_cents: int
    expected_time_years: float
    price_source: str  # "bricklink" | "be_estimate" | "ml_growth" | "none"
    decision: str  # "BUY" | "SELL" | "HOLD" | "SKIP"
    exceeds_target: bool
    exceeds_hurdle: bool


def calculate_forward_return(
    inp: ForwardReturnInput,
    settings: dict[str, Any],
    today: date | None = None,
) -> ForwardReturnResult:
    """Calculate annualized forward return and produce a decision.

    Formula: r = (expected_future / current)^(1/t) - 1
    """
    if today is None:
        today = date.today()

    min_return = settings.get("min_return", 0.20)
    target_return = settings.get("target_return", 0.50)

    current_price = _resolve_current_price(inp)
    gross_future_cents, time_years, source = _resolve_future_price(inp, settings, today)

    # Apply friction discounts to get net realizable value
    future_cents = _apply_exit_discounts(gross_future_cents, time_years, settings)

    if future_cents is None or current_price <= 0:
        return ForwardReturnResult(
            set_number=inp.set_number,
            forward_annual_return=None,
            expected_future_price_cents=future_cents,
            current_price_cents=current_price,
            expected_time_years=time_years,
            price_source=source,
            decision="SKIP" if not inp.is_held else "HOLD",
            exceeds_target=False,
            exceeds_hurdle=False,
        )

    if future_cents <= 0:
        return ForwardReturnResult(
            set_number=inp.set_number,
            forward_annual_return=-1.0,
            expected_future_price_cents=future_cents,
            current_price_cents=current_price,
            expected_time_years=time_years,
            price_source=source,
            decision="SELL" if inp.is_held else "SKIP",
            exceeds_target=False,
            exceeds_hurdle=False,
        )

    ratio = future_cents / current_price
    if ratio <= 0:
        annual_return = -1.0
    else:
        annual_return = ratio ** (1.0 / time_years) - 1.0

    decision = _decide(annual_return, inp.is_held, min_return)

    return ForwardReturnResult(
        set_number=inp.set_number,
        forward_annual_return=round(annual_return, 4),
        expected_future_price_cents=future_cents,
        current_price_cents=current_price,
        expected_time_years=round(time_years, 2),
        price_source=source,
        decision=decision,
        exceeds_target=annual_return >= target_return,
        exceeds_hurdle=annual_return >= min_return,
    )


def _resolve_current_price(inp: ForwardReturnInput) -> int:
    """Determine entry/cost price for the formula denominator.

    Holdings use FIFO cost basis; candidates use best retail price.
    Returns 0 if no meaningful price exists (caller should handle as skip).
    """
    if inp.is_held and inp.cost_basis_cents is not None and inp.cost_basis_cents > 0:
        return inp.cost_basis_cents
    if inp.acquisition_price_cents is not None and inp.acquisition_price_cents > 0:
        return inp.acquisition_price_cents
    if not inp.is_held:
        return inp.market_price_cents
    # Held position without cost basis -- return 0 to signal skip
    # (avoids BL price / BL price = 0% false result)
    return 0


def _resolve_future_price(
    inp: ForwardReturnInput,
    settings: dict[str, Any],
    today: date,
) -> tuple[int | None, float, str]:
    """Determine expected future price (cents), time horizon, and source.

    Tiered approach:
    1. BrickLink current new price (real secondary market exit price)
    2. BrickEconomy future estimate with explicit date
    3. ML predicted growth applied to market price (1-year horizon)
    """
    min_years = settings.get("min_time_years", 0.25)
    default_horizon = settings.get("default_horizon_years", 2.0)
    retired_horizon = settings.get("retired_horizon_years", 1.0)
    post_retirement_bonus = settings.get("post_retirement_bonus_years", 1.5)

    time_years = _estimate_time_horizon(
        inp, settings, today, default_horizon, retired_horizon, post_retirement_bonus
    )
    time_years = max(time_years, min_years)

    liquidity_factor = _liquidity_factor(inp.bl_6mo_times_sold, settings)

    # Tier 1: BrickLink 6-month trend projection
    # Use the annualized growth rate from 6mo sold avg -> current listing avg
    # to project current BL price forward, then discount by liquidity.
    if (
        inp.bl_6mo_avg_price_cents is not None
        and inp.bl_6mo_avg_price_cents > 0
        and inp.bl_current_avg_price_cents is not None
        and inp.bl_current_avg_price_cents > 0
        and inp.bricklink_new_cents is not None
        and inp.bricklink_new_cents > 0
    ):
        ratio_6mo = inp.bl_current_avg_price_cents / inp.bl_6mo_avg_price_cents
        # Annualize: 6 months of growth -> 1 year, clamped to [-50%, +200%]
        annual_growth = max(-0.50, min(2.0, ratio_6mo ** 2.0 - 1.0))
        # Project forward from current BL price
        projected = inp.bricklink_new_cents * (1.0 + annual_growth) ** time_years
        adjusted = round(projected * liquidity_factor)
        return adjusted, time_years, "bl_trend"

    # Tier 2: BrickLink current new price (static, no trend)
    if inp.bricklink_new_cents is not None and inp.bricklink_new_cents > 0:
        adjusted = round(inp.bricklink_new_cents * liquidity_factor)
        return adjusted, time_years, "bricklink"

    # Tier 3: BrickEconomy future estimate with date
    if (
        inp.be_future_estimate_cents is not None
        and inp.be_future_estimate_cents > 0
        and inp.be_future_estimate_date is not None
    ):
        be_years = _parse_date_horizon(inp.be_future_estimate_date, today)
        if be_years is not None:
            be_years = max(be_years, min_years)
            adjusted = round(inp.be_future_estimate_cents * liquidity_factor)
            return adjusted, be_years, "be_estimate"

    # Tier 4: ML predicted growth (1-year horizon)
    if inp.ml_growth_pct is not None and inp.market_price_cents > 0:
        future = round(inp.market_price_cents * (1.0 + inp.ml_growth_pct / 100.0))
        adjusted = round(future * liquidity_factor)
        return adjusted, 1.0, "ml_growth"

    return None, time_years, "none"


def _estimate_time_horizon(
    inp: ForwardReturnInput,
    settings: dict[str, Any],
    today: date,
    default_horizon: float,
    retired_horizon: float,
    post_retirement_bonus: float,
) -> float:
    """Estimate time horizon based on retirement status."""
    if inp.year_retired is not None and inp.year_retired > 0:
        if inp.year_retired <= today.year:
            # Already retired
            return retired_horizon
        # Not yet retired: years until retirement + post-retirement appreciation
        years_to_retire = inp.year_retired - today.year
        return years_to_retire + post_retirement_bonus

    if inp.retiring_soon:
        return 1.0 + post_retirement_bonus

    return default_horizon


def _parse_date_horizon(date_str: str, today: date) -> float | None:
    """Parse BE future_estimate_date and compute years from today.

    Supports ISO dates (YYYY-MM-DD) and year-month (YYYY-MM).
    """
    try:
        if len(date_str) == 7:
            # "YYYY-MM" format -> use first of month
            target = datetime.strptime(date_str, "%Y-%m").date()
        else:
            target = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        delta_days = (target - today).days
        if delta_days <= 0:
            return None
        return delta_days / 365.25
    except (ValueError, TypeError):
        return None


def _liquidity_factor(
    times_sold: int | None,
    settings: dict[str, Any],
) -> float:
    """Compute a 0..1 discount factor based on BrickLink 6-month sales volume.

    High liquidity (many sales) -> factor ~1.0 (no discount).
    Low liquidity (few/no sales) -> factor as low as min_liquidity_factor.

    Uses a simple ramp: factor = min(1.0, times_sold / liquidity_threshold).
    """
    if times_sold is None:
        return 1.0  # No data, assume no discount

    threshold = max(settings.get("liquidity_threshold", 10), 1)
    floor = max(0.0, min(1.0, settings.get("min_liquidity_factor", 0.70)))

    if times_sold >= threshold:
        return 1.0
    if times_sold <= 0:
        return floor

    # Linear ramp from floor to 1.0
    return floor + (1.0 - floor) * (times_sold / threshold)


def _apply_exit_discounts(
    gross_cents: int | None,
    time_years: float,
    settings: dict[str, Any],
) -> int | None:
    """Apply friction discounts to get net realizable exit price.

    Discounts:
    - selling_fee_pct: one-time platform/transaction cost at exit (default 5%)
    - currency_buffer_pct: one-time MYR/USD volatility buffer (default 3%)
    - condition_decay_pct: annual deterioration of sealed condition (default 2%/yr)
    """
    if gross_cents is None or gross_cents <= 0:
        return gross_cents

    selling_fee = settings.get("selling_fee_pct", 0.05)
    currency_buffer = settings.get("currency_buffer_pct", 0.03)
    condition_decay = settings.get("condition_decay_pct", 0.02)

    net = gross_cents * (1.0 - selling_fee) * (1.0 - currency_buffer)
    if condition_decay > 0 and time_years > 0:
        net *= (1.0 - condition_decay) ** time_years

    return round(net)


def _decide(annual_return: float, is_held: bool, min_return: float) -> str:
    """Produce BUY/SELL/HOLD/SKIP decision based on hurdle rate."""
    if is_held:
        return "SELL" if annual_return < min_return else "HOLD"
    return "BUY" if annual_return >= min_return else "SKIP"
