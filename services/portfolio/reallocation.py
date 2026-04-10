"""Hold vs. Sell opportunity cost analysis.

Computes per-holding opportunity cost against the hurdle rate (default 20%).
Pure calculation logic reusing forward return results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from config.runtime_settings import runtime_settings
from services.portfolio.forward_return import ForwardReturnResult
from services.portfolio.forward_return_query import get_holdings_forward_results
from services.portfolio.repository import get_holdings

logger = logging.getLogger("bws.reallocation")


@dataclass(frozen=True)
class HoldingAnalysis:
    """Per-holding opportunity cost breakdown."""

    set_number: str
    capital_cents: int
    market_value_cents: int
    forward_annual_return: float | None
    opportunity_cost_pct: float
    opportunity_cost_cents: int
    decision: str


@dataclass(frozen=True)
class ReallocationSummary:
    """Portfolio-level opportunity cost summary."""

    total_capital_cents: int
    total_opportunity_cost_cents: int
    weighted_forward_return: float
    holdings: list[HoldingAnalysis]
    sell_candidates: list[str]


def compute_reallocation(
    holdings: list[dict],
    results: list[ForwardReturnResult],
    min_return: float,
) -> ReallocationSummary:
    """Compute opportunity cost for each holding against the hurdle rate.

    Args:
        holdings: Output of get_holdings() -- list of holding dicts.
        results: ForwardReturnResult list from get_holdings_forward_results().
        min_return: Hurdle rate (e.g. 0.20 for 20%).

    Returns:
        ReallocationSummary with per-holding opportunity costs.
    """
    result_map: dict[str, ForwardReturnResult] = {r.set_number: r for r in results}

    # Aggregate holdings by set_number (a set may be held in both new/used condition)
    agg: dict[str, dict] = {}
    for h in holdings:
        sn = h["set_number"]
        if sn not in agg:
            agg[sn] = {"set_number": sn, "total_cost_cents": 0, "current_value_cents": 0}
        agg[sn]["total_cost_cents"] += h.get("total_cost_cents", 0)
        agg[sn]["current_value_cents"] += h.get("current_value_cents", 0)

    analyses: list[HoldingAnalysis] = []
    total_capital = 0
    total_opp_cost = 0
    weighted_return_sum = 0.0

    for h in agg.values():
        sn = h["set_number"]
        capital = h["total_cost_cents"]
        market = h["current_value_cents"]

        if capital <= 0:
            continue

        fr = result_map.get(sn)
        fwd_return = fr.forward_annual_return if fr else None
        decision = fr.decision if fr else "HOLD"

        # No data = no penalty; only penalize holdings with known underperformance
        if fwd_return is None:
            opp_cost_pct = 0.0
            opp_cost_cents = 0
            effective_return = 0.0
        else:
            effective_return = fwd_return
            opp_cost_pct = max(0.0, min_return - effective_return)
            opp_cost_cents = round(opp_cost_pct * capital)

        analyses.append(
            HoldingAnalysis(
                set_number=sn,
                capital_cents=capital,
                market_value_cents=market,
                forward_annual_return=fwd_return,
                opportunity_cost_pct=round(opp_cost_pct, 4),
                opportunity_cost_cents=opp_cost_cents,
                decision=decision,
            )
        )

        total_capital += capital
        total_opp_cost += opp_cost_cents
        weighted_return_sum += effective_return * capital

    weighted_return = (
        round(weighted_return_sum / total_capital, 4) if total_capital > 0 else 0.0
    )

    sell_candidates = [
        a.set_number
        for a in sorted(analyses, key=lambda a: a.opportunity_cost_cents, reverse=True)
        if a.opportunity_cost_cents > 0
    ]

    return ReallocationSummary(
        total_capital_cents=total_capital,
        total_opportunity_cost_cents=total_opp_cost,
        weighted_forward_return=weighted_return,
        holdings=analyses,
        sell_candidates=sell_candidates,
    )


def get_reallocation_analysis(conn: Any) -> dict:
    """Compute reallocation analysis for all holdings.

    Reuses get_holdings() and get_holdings_forward_results() to avoid
    redundant DB queries.
    """
    holdings = get_holdings(conn)
    _, results = get_holdings_forward_results(conn)
    fr_settings = runtime_settings.get_section("forward_return")
    min_return = fr_settings.get("min_return", 0.20)

    summary = compute_reallocation(holdings, results, min_return)
    return _summary_to_dict(summary)


def _summary_to_dict(s: ReallocationSummary) -> dict:
    """Convert ReallocationSummary to a JSON-serializable dict."""
    return {
        "total_capital_cents": s.total_capital_cents,
        "total_opportunity_cost_cents": s.total_opportunity_cost_cents,
        "weighted_forward_return": s.weighted_forward_return,
        "sell_candidates": s.sell_candidates,
        "holdings": [
            {
                "set_number": a.set_number,
                "capital_cents": a.capital_cents,
                "market_value_cents": a.market_value_cents,
                "forward_annual_return": a.forward_annual_return,
                "opportunity_cost_pct": a.opportunity_cost_pct,
                "opportunity_cost_cents": a.opportunity_cost_cents,
                "decision": a.decision,
            }
            for a in s.holdings
        ],
    }
