"""Buy signal calculator for LEGO set investment.

Given a set's predicted growth (from RRP) and a purchase price,
determines whether the set is worth buying at that price.

The model predicts growth from RRP. When you buy below RRP (discount),
your effective return is higher. When you buy above RRP (secondary market
premium), your effective return is lower.

Hurdle rate: minimum acceptable return to justify capital lockup,
storage costs, and effort of reselling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Minimum annual return to justify buying (opportunity cost)
# 8% = roughly stock market average + storage/effort premium
HURDLE_RATE_12M: float = 8.0
HURDLE_RATE_24M: float = 20.0  # ~10% annualized over 2 years

# Signal thresholds (effective return above hurdle)
STRONG_BUY_MARGIN: float = 10.0  # 10%+ above hurdle = strong buy
BUY_MARGIN: float = 0.0  # At or above hurdle = buy
HOLD_MARGIN: float = -5.0  # Within 5% below hurdle = hold (if you already own)

MYR_PER_USD: float = 4.50


@dataclass(frozen=True)
class BuySignal:
    """Buy/sell signal for a specific set at a specific price."""

    set_number: str
    title: str
    theme: str

    # Prices
    rrp_myr: float
    buy_price_myr: float
    discount_pct: float  # negative = premium over RRP

    # Predicted values (from RRP growth model)
    predicted_growth_from_rrp_pct: float
    expected_value_12m_myr: float
    expected_value_24m_myr: float

    # Effective returns (from YOUR buy price)
    effective_return_12m_pct: float
    effective_return_24m_pct: float
    effective_profit_12m_myr: float
    effective_profit_24m_myr: float

    # Signal
    signal: str  # "STRONG BUY", "BUY", "HOLD", "PASS"
    signal_reason: str

    # Break-even
    max_buy_price_myr: float  # Highest price that still beats hurdle rate
    break_even_discount_pct: float  # Minimum discount needed


@dataclass(frozen=True)
class DiscountScenario:
    """What-if analysis at different discount levels."""

    discount_pct: float
    buy_price_myr: float
    effective_return_12m_pct: float
    effective_return_24m_pct: float
    effective_profit_12m_myr: float
    signal: str


def compute_buy_signal(
    set_number: str,
    title: str,
    theme: str,
    rrp_usd_cents: int,
    predicted_growth_pct: float,
    buy_price_myr: float | None = None,
    discount_pct: float = 0.0,
) -> BuySignal:
    """Compute buy signal for a set at a given price.

    Args:
        rrp_usd_cents: Original RRP in USD cents
        predicted_growth_pct: Model's predicted annual growth from RRP
        buy_price_myr: Actual purchase price in MYR (if known)
        discount_pct: Discount off RRP (0-100). Used if buy_price_myr not provided.

    Returns:
        BuySignal with effective returns and recommendation.
    """
    rrp_myr = rrp_usd_cents / 100.0 * MYR_PER_USD

    if buy_price_myr is None:
        buy_price_myr = rrp_myr * (1 - discount_pct / 100.0)

    actual_discount = (1 - buy_price_myr / rrp_myr) * 100 if rrp_myr > 0 else 0

    # Expected future values (model predicts growth from RRP)
    expected_12m = rrp_myr * (1 + predicted_growth_pct / 100.0)
    # 24m: compound at 80% of annual rate (conservative decay)
    annual_rate = predicted_growth_pct / 100.0
    expected_24m = rrp_myr * (1 + annual_rate * 0.8) ** 2

    # Effective returns from YOUR buy price
    eff_return_12m = (expected_12m - buy_price_myr) / buy_price_myr * 100 if buy_price_myr > 0 else 0
    eff_return_24m = (expected_24m - buy_price_myr) / buy_price_myr * 100 if buy_price_myr > 0 else 0
    eff_profit_12m = expected_12m - buy_price_myr
    eff_profit_24m = expected_24m - buy_price_myr

    # Signal based on 12m effective return vs hurdle
    margin = eff_return_12m - HURDLE_RATE_12M

    if margin >= STRONG_BUY_MARGIN:
        signal = "STRONG BUY"
        reason = f"+{eff_return_12m:.0f}% effective return, {margin:.0f}% above hurdle"
    elif margin >= BUY_MARGIN:
        signal = "BUY"
        reason = f"+{eff_return_12m:.0f}% effective return, meets {HURDLE_RATE_12M:.0f}% hurdle"
    elif margin >= HOLD_MARGIN:
        signal = "HOLD"
        reason = f"+{eff_return_12m:.0f}% return, {abs(margin):.0f}% below hurdle -- hold if owned, don't buy new"
    else:
        signal = "PASS"
        reason = f"+{eff_return_12m:.0f}% return, too far below {HURDLE_RATE_12M:.0f}% hurdle"

    # Break-even: max price where 12m return >= hurdle rate
    max_buy = expected_12m / (1 + HURDLE_RATE_12M / 100)
    break_even_discount = (1 - max_buy / rrp_myr) * 100 if rrp_myr > 0 else 0

    return BuySignal(
        set_number=set_number,
        title=title,
        theme=theme,
        rrp_myr=round(rrp_myr, 2),
        buy_price_myr=round(buy_price_myr, 2),
        discount_pct=round(actual_discount, 1),
        predicted_growth_from_rrp_pct=round(predicted_growth_pct, 1),
        expected_value_12m_myr=round(expected_12m, 2),
        expected_value_24m_myr=round(expected_24m, 2),
        effective_return_12m_pct=round(eff_return_12m, 1),
        effective_return_24m_pct=round(eff_return_24m, 1),
        effective_profit_12m_myr=round(eff_profit_12m, 2),
        effective_profit_24m_myr=round(eff_profit_24m, 2),
        signal=signal,
        signal_reason=reason,
        max_buy_price_myr=round(max_buy, 2),
        break_even_discount_pct=round(break_even_discount, 1),
    )


def compute_discount_scenarios(
    set_number: str,
    title: str,
    theme: str,
    rrp_usd_cents: int,
    predicted_growth_pct: float,
    discounts: tuple[float, ...] = (0, 5, 10, 15, 20, 25, 30),
) -> list[DiscountScenario]:
    """What-if analysis: signal at each discount level.

    Returns a table showing how the buy signal changes at different discounts.
    """
    rrp_myr = rrp_usd_cents / 100.0 * MYR_PER_USD
    expected_12m = rrp_myr * (1 + predicted_growth_pct / 100.0)
    annual_rate = predicted_growth_pct / 100.0
    expected_24m = rrp_myr * (1 + annual_rate * 0.8) ** 2

    scenarios = []
    for disc in discounts:
        buy_price = rrp_myr * (1 - disc / 100.0)
        if buy_price <= 0:
            continue

        eff_12m = (expected_12m - buy_price) / buy_price * 100
        eff_24m = (expected_24m - buy_price) / buy_price * 100
        profit_12m = expected_12m - buy_price

        margin = eff_12m - HURDLE_RATE_12M
        if margin >= STRONG_BUY_MARGIN:
            sig = "STRONG BUY"
        elif margin >= BUY_MARGIN:
            sig = "BUY"
        elif margin >= HOLD_MARGIN:
            sig = "HOLD"
        else:
            sig = "PASS"

        scenarios.append(DiscountScenario(
            discount_pct=disc,
            buy_price_myr=round(buy_price, 2),
            effective_return_12m_pct=round(eff_12m, 1),
            effective_return_24m_pct=round(eff_24m, 1),
            effective_profit_12m_myr=round(profit_12m, 2),
            signal=sig,
        ))

    return scenarios


def compute_market_price_signal(
    set_number: str,
    title: str,
    theme: str,
    rrp_usd_cents: int,
    predicted_growth_pct: float,
    market_price_myr: float,
) -> BuySignal:
    """Compute buy signal at a specific market price (e.g., Shopee, Carousell).

    Use this when the set is available at a price different from RRP --
    could be discounted (below RRP) or at a premium (above RRP, secondary market).
    """
    return compute_buy_signal(
        set_number=set_number,
        title=title,
        theme=theme,
        rrp_usd_cents=rrp_usd_cents,
        predicted_growth_pct=predicted_growth_pct,
        buy_price_myr=market_price_myr,
    )
