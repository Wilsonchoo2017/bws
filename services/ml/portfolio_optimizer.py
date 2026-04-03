"""Mean-Variance portfolio optimizer for LEGO set investment.

Solves: Given a budget, which sets to buy and how many of each
to maximize risk-adjusted returns?

Uses ML growth predictions from growth_model.py and estimates
portfolio risk from theme-level return correlations.

API: GET /ml/portfolio?budget=100000&risk=balanced&max_units=3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# Correlation parameters (estimated from 223 sets, see research/14)
WITHIN_THEME_CORR: float = 0.194
CROSS_THEME_CORR: float = 0.05
PREDICTION_STD: float = 5.67  # From LOO calibration


@dataclass(frozen=True)
class PortfolioItem:
    """A single holding in the optimized portfolio."""

    set_number: str
    title: str
    theme: str
    units: int
    price_usd: float
    total_cost_usd: float
    predicted_growth_pct: float
    expected_profit_usd: float
    confidence: str
    ml_tier: int


@dataclass(frozen=True)
class PortfolioResult:
    """Complete optimized portfolio with metrics."""

    holdings: tuple[PortfolioItem, ...]
    total_cost_usd: float
    budget_usd: float
    expected_return_pct: float
    portfolio_std_pct: float
    sharpe_ratio: float
    var_95_pct: float
    n_sets: int
    n_units: int
    n_themes: int
    max_theme_pct: float
    risk_profile: str


def _estimate_covariance(
    themes: np.ndarray,
    theme_stds: np.ndarray,
) -> np.ndarray:
    """Build covariance matrix from theme structure + prediction error."""
    n = len(themes)
    set_stds = np.sqrt(theme_stds**2 + PREDICTION_STD**2)

    cov = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            if i == j:
                cov[i, j] = set_stds[i] ** 2
            elif themes[i] == themes[j]:
                cov[i, j] = WITHIN_THEME_CORR * set_stds[i] * set_stds[j]
                cov[j, i] = cov[i, j]
            else:
                cov[i, j] = CROSS_THEME_CORR * set_stds[i] * set_stds[j]
                cov[j, i] = cov[i, j]

    return cov


def _solve_knapsack(
    scores: np.ndarray,
    prices: np.ndarray,
    budget: float,
    max_units: int,
) -> np.ndarray:
    """Solve integer knapsack: maximize sum(score * x) s.t. sum(price * x) <= budget."""
    n = len(scores)
    result = milp(
        c=-scores,  # milp minimizes, so negate
        constraints=LinearConstraint(prices.reshape(1, -1), lb=0, ub=budget),
        integrality=np.ones(n),
        bounds=Bounds(lb=0, ub=max_units),
    )

    if result.success:
        return np.round(result.x).astype(int)

    # Fallback: greedy by score
    logger.warning("MILP failed (%s), using greedy fallback", result.message)
    order = np.argsort(-scores)
    allocs = np.zeros(n, dtype=int)
    remaining = budget
    for idx in order:
        if prices[idx] <= 0:
            continue
        units = min(max_units, int(remaining / prices[idx]))
        if units > 0:
            allocs[idx] = units
            remaining -= units * prices[idx]
    return allocs


def optimize_portfolio(
    conn: DuckDBPyConnection,
    budget_usd: float = 1000.0,
    risk_profile: str = "balanced",
    max_units_per_set: int = 3,
) -> PortfolioResult:
    """Build an optimized LEGO investment portfolio.

    Args:
        conn: DuckDB connection
        budget_usd: Total budget in USD
        risk_profile: "aggressive" (0.1), "balanced" (0.5), or "conservative" (1.0)
        max_units_per_set: Maximum copies of any single set

    Returns:
        PortfolioResult with optimized holdings and metrics.
    """
    from services.ml.growth_model import predict_growth, train_growth_models

    risk_lambda = {"aggressive": 0.1, "balanced": 0.5, "conservative": 1.0}.get(
        risk_profile, 0.5
    )

    # Get ML predictions
    tier1, tier2, ts, ss, tier3, ensemble = train_growth_models(conn)
    predictions = predict_growth(conn, tier1, tier2, ts, ss, tier3=tier3, ensemble=ensemble)

    if not predictions:
        return PortfolioResult(
            holdings=(), total_cost_usd=0, budget_usd=budget_usd,
            expected_return_pct=0, portfolio_std_pct=0, sharpe_ratio=0,
            var_95_pct=0, n_sets=0, n_units=0, n_themes=0,
            max_theme_pct=0, risk_profile=risk_profile,
        )

    # Build arrays
    pred_map = {p.set_number: p for p in predictions}

    # Load prices
    db_data = conn.execute("""
        SELECT li.set_number, li.theme,
               be.rrp_usd_cents, be.annual_growth_pct
        FROM lego_items li
        JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0
    """).fetchdf()

    for c in ["rrp_usd_cents", "annual_growth_pct"]:
        db_data[c] = pd.to_numeric(db_data[c], errors="coerce")

    # Merge predictions with price data
    records = []
    for _, row in db_data.iterrows():
        sn = row["set_number"]
        pred = pred_map.get(sn)
        if pred is None:
            continue
        records.append({
            "set_number": sn,
            "title": pred.title,
            "theme": row["theme"],
            "price_usd": row["rrp_usd_cents"] / 100.0,
            "predicted_growth": pred.predicted_growth_pct,
            "confidence": pred.confidence,
            "ml_tier": pred.tier,
        })

    df = pd.DataFrame(records)
    if df.empty:
        return PortfolioResult(
            holdings=(), total_cost_usd=0, budget_usd=budget_usd,
            expected_return_pct=0, portfolio_std_pct=0, sharpe_ratio=0,
            var_95_pct=0, n_sets=0, n_units=0, n_themes=0,
            max_theme_pct=0, risk_profile=risk_profile,
        )

    n = len(df)
    prices = df["price_usd"].values
    returns = df["predicted_growth"].values
    themes = df["theme"].values

    # Theme-level stds for covariance
    theme_std_map = db_data.groupby("theme")["annual_growth_pct"].std().fillna(PREDICTION_STD)
    theme_stds = df["theme"].map(theme_std_map).fillna(PREDICTION_STD).values

    # Covariance matrix
    cov = _estimate_covariance(themes, theme_stds)
    variances = np.diag(cov)

    # Risk-adjusted score per unit
    avg_corr = np.array([
        np.mean([cov[i, j] for j in range(n) if j != i]) / variances[i]
        if variances[i] > 0 else 0
        for i in range(n)
    ])
    effective_risk = variances * (1 + risk_lambda * avg_corr)
    risk_adjusted = returns - risk_lambda * np.sqrt(effective_risk)
    scores = np.where(prices > 0, risk_adjusted / prices, 0)

    # Solve
    allocations = _solve_knapsack(scores, prices, budget_usd, max_units_per_set)

    # Build holdings
    holdings = []
    for i in range(n):
        if allocations[i] <= 0:
            continue
        units = int(allocations[i])
        cost = units * prices[i]
        profit = cost * returns[i] / 100
        holdings.append(PortfolioItem(
            set_number=df.iloc[i]["set_number"],
            title=df.iloc[i]["title"],
            theme=df.iloc[i]["theme"],
            units=units,
            price_usd=round(prices[i], 2),
            total_cost_usd=round(cost, 2),
            predicted_growth_pct=round(returns[i], 1),
            expected_profit_usd=round(profit, 2),
            confidence=df.iloc[i]["confidence"],
            ml_tier=int(df.iloc[i]["ml_tier"]),
        ))

    holdings.sort(key=lambda h: h.expected_profit_usd, reverse=True)

    # Portfolio metrics
    total_cost = sum(h.total_cost_usd for h in holdings)
    total_profit = sum(h.expected_profit_usd for h in holdings)
    port_return = total_profit / total_cost * 100 if total_cost > 0 else 0

    # Portfolio variance
    alloc_idx = [i for i in range(n) if allocations[i] > 0]
    if alloc_idx and total_cost > 0:
        weights = np.array([allocations[i] * prices[i] / total_cost for i in alloc_idx])
        sub_cov = cov[np.ix_(alloc_idx, alloc_idx)]
        port_var = float(weights @ sub_cov @ weights)
        port_std = float(np.sqrt(port_var))
    else:
        port_std = 0

    sharpe = port_return / port_std if port_std > 0 else 0
    var_95 = port_return - 1.645 * port_std

    n_themes = len({h.theme for h in holdings})
    theme_costs = {}
    for h in holdings:
        theme_costs[h.theme] = theme_costs.get(h.theme, 0) + h.total_cost_usd
    max_theme_pct = max(theme_costs.values()) / total_cost * 100 if total_cost > 0 and theme_costs else 0

    return PortfolioResult(
        holdings=tuple(holdings),
        total_cost_usd=round(total_cost, 2),
        budget_usd=budget_usd,
        expected_return_pct=round(port_return, 1),
        portfolio_std_pct=round(port_std, 1),
        sharpe_ratio=round(sharpe, 2),
        var_95_pct=round(var_95, 1),
        n_sets=len(holdings),
        n_units=sum(h.units for h in holdings),
        n_themes=n_themes,
        max_theme_pct=round(max_theme_pct, 1),
        risk_profile=risk_profile,
    )
