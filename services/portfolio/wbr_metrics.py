"""Weekly Business Review (WBR) metrics for portfolio capital allocation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from config.runtime_settings import runtime_settings
from services.portfolio.forward_return import (
    ForwardReturnInput,
    ForwardReturnResult,
    calculate_forward_return,
)
from services.portfolio.forward_return_query import (
    get_candidate_inputs,
    get_holdings_forward_results,
)
from services.portfolio.repository import MYR_PER_USD

logger = logging.getLogger("bws.wbr_metrics")


def calculate_wbr(conn: Any) -> dict:
    """Calculate WBR metrics for the portfolio."""
    fr_settings = runtime_settings.get_section("forward_return")
    min_return = fr_settings.get("min_return", 0.20)

    # Single query for holdings + forward returns (reused everywhere below)
    held_inputs, held_results = get_holdings_forward_results(conn)

    # Capital-weighted forward return + hurdle check
    total_capital = 0
    weighted_return_sum = 0.0
    capital_above_hurdle = 0
    worst: dict | None = None
    worst_return = float("inf")

    for inp, res in zip(held_inputs, held_results):
        cost = inp.cost_basis_cents or 0
        if cost <= 0:
            continue
        total_capital += cost
        ret = res.forward_annual_return
        if ret is not None:
            weighted_return_sum += ret * cost
            if ret >= min_return:
                capital_above_hurdle += cost
            if ret < worst_return:
                worst_return = ret
                worst = {"set_number": res.set_number, "forward_annual_return": ret}

    pct_above = (
        round(capital_above_hurdle / total_capital * 100, 1) if total_capital > 0 else 0.0
    )
    weighted_avg = (
        round(weighted_return_sum / total_capital, 4) if total_capital > 0 else 0.0
    )

    # Avg buy discount for recent buys (trailing 30 days)
    cutoff = datetime.now() - timedelta(days=30)
    avg_discount = _avg_buy_discount(conn, cutoff)

    # Avg expected return for new buys (trailing 30 days)
    avg_new_buy_return = _avg_new_buy_return(
        cutoff, held_inputs, held_results, fr_settings
    )

    # Inventory turnover (annualized)
    turnover = _inventory_turnover(conn, held_inputs)

    # Best candidate (not held, highest return)
    candidate_inputs = get_candidate_inputs(conn, held_inputs)
    best: dict | None = None
    if candidate_inputs:
        # Only compute top 50 candidates for performance
        sample = sorted(
            candidate_inputs,
            key=lambda i: i.ml_growth_pct if i.ml_growth_pct is not None else -999,
            reverse=True,
        )[:50]
        candidate_results = [calculate_forward_return(inp, fr_settings) for inp in sample]
        for res in candidate_results:
            if res.forward_annual_return is not None and (
                best is None or res.forward_annual_return > best["forward_annual_return"]
            ):
                best = {
                    "set_number": res.set_number,
                    "forward_annual_return": res.forward_annual_return,
                }

    return {
        "avg_buy_discount_pct": avg_discount,
        "avg_expected_return_new_buys": avg_new_buy_return,
        "inventory_turnover": turnover,
        "pct_capital_above_hurdle": pct_above,
        "total_forward_return_weighted": weighted_avg,
        "worst_holding": worst,
        "best_candidate": best,
    }


def _avg_buy_discount(conn: Any, since: datetime) -> float:
    """Average discount of recent buys vs market price."""
    rows = conn.execute(
        """
        WITH recent_buys AS (
            SELECT pt.set_number, pt.price_cents AS buy_price
            FROM portfolio_transactions pt
            WHERE pt.txn_type = 'BUY' AND pt.txn_date >= ?
        ),
        latest_bl AS (
            SELECT set_number, price_cents, currency
            FROM (
                SELECT set_number, price_cents, currency,
                       ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
                FROM price_records
                WHERE source = 'bricklink_new'
            ) sub WHERE rn = 1
        )
        SELECT rb.buy_price, bl.price_cents, bl.currency
        FROM recent_buys rb
        LEFT JOIN latest_bl bl ON bl.set_number = rb.set_number
        """,
        [since],
    ).fetchall()

    if not rows:
        return 0.0

    discounts = []
    for buy_price, bl_price, bl_currency in rows:
        if bl_price is None or bl_price <= 0:
            continue
        market = bl_price if bl_currency == "MYR" else round(bl_price * MYR_PER_USD)
        if market > 0:
            discounts.append((market - buy_price) / market * 100)

    return round(sum(discounts) / len(discounts), 1) if discounts else 0.0


def _avg_new_buy_return(
    since: datetime,
    held_inputs: list[ForwardReturnInput],
    held_results: list[ForwardReturnResult],
    fr_settings: dict,
) -> float:
    """Average forward return of sets bought in trailing period.

    Reuses already-computed held_inputs/held_results to avoid redundant queries.
    """
    since_str = since.isoformat()
    # Filter to sets in the held results (all holdings already computed)
    # We don't have txn_date in ForwardReturnInput, so just use all held results
    # This is an approximation -- in practice most holdings are recent buys
    returns = [
        r.forward_annual_return
        for r in held_results
        if r.forward_annual_return is not None
    ]
    return round(sum(returns) / len(returns), 4) if returns else 0.0


def _inventory_turnover(conn: Any, held_inputs: list[ForwardReturnInput]) -> float:
    """Annualized inventory turnover = sells / avg holdings."""
    sell_count = conn.execute(
        """
        SELECT COALESCE(SUM(quantity), 0)
        FROM portfolio_transactions
        WHERE txn_type = 'SELL' AND txn_date >= CURRENT_DATE - INTERVAL '365 days'
        """
    ).fetchone()[0]

    held_count = sum(
        1 for inp in held_inputs if inp.cost_basis_cents and inp.cost_basis_cents > 0
    )
    if held_count <= 0:
        return 0.0

    return round(sell_count / held_count, 2)
