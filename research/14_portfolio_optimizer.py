"""
14 - Mean-Variance Portfolio Optimizer with Budget Constraints
==============================================================
Solves: Given a budget, which LEGO sets to buy and how many of each
to maximize risk-adjusted returns?

Model: Mean-Variance Knapsack
- Maximize: expected_return - lambda * portfolio_variance
- Subject to: budget, integer units, max per set, min diversification

Uses ML growth predictions + estimated covariance matrix.

Run with: .venv/bin/python research/14_portfolio_optimizer.py
"""

import logging
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import milp, Bounds, LinearConstraint

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".bws" / "bws.duckdb"

# ---------------------------------------------------------------------------
# 1. Load data and get ML predictions
# ---------------------------------------------------------------------------


def load_prediction_data():
    """Load sets with ML predictions, prices, and theme info."""
    db = duckdb.connect(str(DB_PATH), read_only=True)
    df = db.execute("""
        SELECT li.set_number, li.title, li.theme,
               be.annual_growth_pct, be.rrp_usd_cents, be.subtheme
        FROM lego_items li
        JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0 AND be.annual_growth_pct IS NOT NULL
    """).fetchdf()
    db.close()

    for c in ["annual_growth_pct", "rrp_usd_cents"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["price_usd"] = df["rrp_usd_cents"] / 100.0
    return df


# ---------------------------------------------------------------------------
# 2. Estimate covariance matrix
# ---------------------------------------------------------------------------

# From our analysis:
# ICC (within-theme correlation) = 0.194
# Within-theme std varies by theme but averages ~7%
# Between-theme variance accounts for 19% of total

WITHIN_THEME_CORR = 0.194  # Two sets in same theme correlate this much
CROSS_THEME_CORR = 0.05    # Weak market-wide factor (LEGO market moves together)


def estimate_covariance_matrix(
    df: pd.DataFrame,
    prediction_std: float = 5.67,
) -> np.ndarray:
    """Build covariance matrix from theme structure + prediction error.

    For sets i, j:
    - Same theme: cov = within_theme_corr * sigma_i * sigma_j
    - Different theme: cov = cross_theme_corr * sigma_i * sigma_j
    - Diagonal: var = sigma_i^2

    sigma_i = sqrt(theme_variance + prediction_error_variance)
    """
    n = len(df)
    themes = df["theme"].values

    # Per-theme standard deviation
    theme_stds = df.groupby("theme")["annual_growth_pct"].transform("std").fillna(prediction_std).values

    # Total per-set std: theme variance + prediction noise
    set_stds = np.sqrt(theme_stds**2 + prediction_std**2)

    cov = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                cov[i, j] = set_stds[i] ** 2
            elif themes[i] == themes[j]:
                cov[i, j] = WITHIN_THEME_CORR * set_stds[i] * set_stds[j]
            else:
                cov[i, j] = CROSS_THEME_CORR * set_stds[i] * set_stds[j]

    return cov


# ---------------------------------------------------------------------------
# 3. Portfolio optimizer
# ---------------------------------------------------------------------------


def optimize_portfolio(
    df: pd.DataFrame,
    predicted_returns: np.ndarray,
    cov_matrix: np.ndarray,
    budget_usd: float = 1000.0,
    risk_aversion: float = 0.5,
    max_units_per_set: int = 3,
    min_sets: int = 5,
    max_sets: int = 30,
) -> pd.DataFrame:
    """Solve the mean-variance knapsack problem.

    Since scipy.optimize.milp only handles linear objectives, we use a
    two-phase approach:
    1. Score each set by risk-adjusted return per dollar
    2. Solve integer knapsack with these scores as values

    The risk adjustment penalizes:
    - High variance sets (prediction uncertainty)
    - Concentration in one theme (correlation penalty)

    Returns DataFrame with allocation decisions.
    """
    n = len(df)
    prices = df["price_usd"].values
    themes = df["theme"].values
    variances = np.diag(cov_matrix)

    # Phase 1: Compute risk-adjusted score per unit for each set
    # Score = (expected_return - risk_aversion * marginal_variance) / price
    # This is a per-dollar "efficiency" score

    # Marginal variance = set's own variance + correlation contribution
    # For simplicity, use: var_i + avg_correlation_with_portfolio * var_i
    avg_corr_contribution = np.array([
        np.mean([cov_matrix[i, j] for j in range(n) if j != i]) / variances[i]
        if variances[i] > 0 else 0
        for i in range(n)
    ])

    effective_risk = variances * (1 + risk_aversion * avg_corr_contribution)
    risk_adjusted_return = predicted_returns - risk_aversion * np.sqrt(effective_risk)

    # Score per dollar (value density for knapsack)
    scores = np.where(prices > 0, risk_adjusted_return / prices, 0)

    # Phase 2: Integer knapsack using MILP
    # Maximize: sum(scores[i] * x[i])
    # Subject to: sum(prices[i] * x[i]) <= budget
    #             x[i] in {0, 1, ..., max_units}

    # scipy.milp minimizes, so negate scores
    c = -scores

    # Budget constraint: sum(price * x) <= budget
    A_budget = prices.reshape(1, -1)
    budget_constraint = LinearConstraint(A_budget, lb=0, ub=budget_usd)

    # Variable bounds: 0 <= x[i] <= max_units (integer)
    bounds = Bounds(lb=0, ub=max_units_per_set)
    integrality = np.ones(n)  # All integer

    # Solve
    result = milp(
        c=c,
        constraints=budget_constraint,
        integrality=integrality,
        bounds=bounds,
    )

    if not result.success:
        logger.warning("Optimization failed: %s", result.message)
        # Fallback: greedy by score
        return _greedy_allocation(df, scores, prices, budget_usd, max_units_per_set)

    allocations = np.round(result.x).astype(int)

    # Build result DataFrame
    result_df = df.copy()
    result_df["units"] = allocations
    result_df["predicted_growth"] = predicted_returns
    result_df["risk_adjusted_score"] = risk_adjusted_return
    result_df["score_per_dollar"] = scores
    result_df["total_cost"] = allocations * prices
    result_df["expected_profit_usd"] = allocations * prices * predicted_returns / 100

    # Filter to allocated sets
    allocated = result_df[result_df["units"] > 0].copy()
    allocated = allocated.sort_values("expected_profit_usd", ascending=False)

    # Check diversification
    n_sets = len(allocated)
    if n_sets < min_sets:
        logger.info(
            "Only %d sets allocated (min %d). Consider lowering budget or risk_aversion.",
            n_sets, min_sets,
        )

    return allocated


def _greedy_allocation(
    df: pd.DataFrame,
    scores: np.ndarray,
    prices: np.ndarray,
    budget: float,
    max_units: int,
) -> pd.DataFrame:
    """Greedy fallback: allocate by score per dollar until budget exhausted."""
    order = np.argsort(-scores)
    allocations = np.zeros(len(df), dtype=int)
    remaining = budget

    for idx in order:
        if prices[idx] <= 0:
            continue
        units = min(max_units, int(remaining / prices[idx]))
        if units > 0:
            allocations[idx] = units
            remaining -= units * prices[idx]

    result_df = df.copy()
    result_df["units"] = allocations
    result_df["predicted_growth"] = scores * prices  # approx
    result_df["total_cost"] = allocations * prices

    allocated = result_df[result_df["units"] > 0].copy()
    return allocated.sort_values("total_cost", ascending=False)


# ---------------------------------------------------------------------------
# 4. Portfolio analysis
# ---------------------------------------------------------------------------


def analyze_portfolio(
    portfolio: pd.DataFrame,
    cov_matrix: np.ndarray,
    all_df: pd.DataFrame,
) -> dict:
    """Compute portfolio-level metrics."""
    if portfolio.empty:
        return {}

    total_cost = portfolio["total_cost"].sum()
    total_profit = portfolio["expected_profit_usd"].sum()
    portfolio_return = total_profit / total_cost * 100 if total_cost > 0 else 0

    # Portfolio variance (weighted)
    idx_map = {sn: i for i, sn in enumerate(all_df["set_number"])}
    weights = []
    indices = []
    for _, row in portfolio.iterrows():
        i = idx_map.get(row["set_number"])
        if i is not None:
            w = row["total_cost"] / total_cost if total_cost > 0 else 0
            weights.append(w)
            indices.append(i)

    if weights:
        w = np.array(weights)
        sub_cov = cov_matrix[np.ix_(indices, indices)]
        port_var = w @ sub_cov @ w
        port_std = np.sqrt(port_var)
        sharpe = portfolio_return / port_std if port_std > 0 else 0
    else:
        port_std = 0
        sharpe = 0

    # Diversification
    n_sets = len(portfolio)
    n_themes = portfolio["theme"].nunique()
    max_theme_pct = portfolio.groupby("theme")["total_cost"].sum().max() / total_cost * 100 if total_cost > 0 else 0

    # Drawdown estimate (95% VaR using normal approximation)
    var_95 = portfolio_return - 1.645 * port_std

    return {
        "total_cost_usd": round(total_cost, 2),
        "expected_return_pct": round(portfolio_return, 1),
        "portfolio_std_pct": round(port_std, 1),
        "sharpe_ratio": round(sharpe, 2),
        "var_95_pct": round(var_95, 1),
        "n_sets": n_sets,
        "total_units": int(portfolio["units"].sum()),
        "n_themes": n_themes,
        "max_theme_concentration_pct": round(max_theme_pct, 1),
    }


# ---------------------------------------------------------------------------
# 5. Run experiments
# ---------------------------------------------------------------------------


def main():
    df = load_prediction_data()
    predicted_returns = df["annual_growth_pct"].values
    print(f"Loaded {len(df)} sets\n")

    # Estimate covariance
    cov = estimate_covariance_matrix(df)
    print(f"Covariance matrix: {cov.shape}")

    # Test different budgets and risk levels
    budgets = [500, 1000, 2000, 5000]
    risk_levels = [
        ("aggressive", 0.1),
        ("balanced", 0.5),
        ("conservative", 1.0),
    ]

    for budget in budgets:
        print(f"\n{'='*80}")
        print(f"BUDGET: ${budget}")
        print(f"{'='*80}")

        for risk_name, risk_lambda in risk_levels:
            portfolio = optimize_portfolio(
                df, predicted_returns, cov,
                budget_usd=budget,
                risk_aversion=risk_lambda,
                max_units_per_set=3,
            )

            metrics = analyze_portfolio(portfolio, cov, df)

            print(f"\n  --- {risk_name.upper()} (lambda={risk_lambda}) ---")
            if not metrics:
                print("    No allocation possible")
                continue

            print(f"    Sets: {metrics['n_sets']} ({metrics['total_units']} units) across {metrics['n_themes']} themes")
            print(f"    Cost: ${metrics['total_cost_usd']:.0f} / ${budget}")
            print(f"    Expected return: {metrics['expected_return_pct']:.1f}%")
            print(f"    Portfolio std: {metrics['portfolio_std_pct']:.1f}%")
            print(f"    Sharpe ratio: {metrics['sharpe_ratio']:.2f}")
            print(f"    95% VaR: {metrics['var_95_pct']:.1f}%")
            print(f"    Max theme concentration: {metrics['max_theme_concentration_pct']:.0f}%")

            # Show top allocations
            print(f"    Top holdings:")
            for _, row in portfolio.head(10).iterrows():
                print(
                    f"      {row['set_number']:>6s} {str(row['title'])[:22]:22s} "
                    f"{str(row['theme'])[:12]:12s} "
                    f"x{row['units']} @ ${row['price_usd']:.0f} "
                    f"= ${row['total_cost']:.0f}  "
                    f"growth={row['predicted_growth']:.1f}%"
                )

    # Compare strategies
    print(f"\n{'='*80}")
    print("STRATEGY COMPARISON ($1000 budget)")
    print(f"{'='*80}")

    strategies = {}

    # Strategy 1: Optimizer (balanced)
    p1 = optimize_portfolio(df, predicted_returns, cov, budget_usd=1000, risk_aversion=0.5)
    strategies["MV Optimizer"] = analyze_portfolio(p1, cov, df)

    # Strategy 2: Top N by growth (naive)
    top_growth = df.nlargest(20, "annual_growth_pct").copy()
    top_growth["units"] = 0
    remaining = 1000
    for idx in top_growth.index:
        price = top_growth.loc[idx, "price_usd"]
        if price > 0 and remaining >= price:
            units = min(3, int(remaining / price))
            top_growth.loc[idx, "units"] = units
            remaining -= units * price
    top_growth["total_cost"] = top_growth["units"] * top_growth["price_usd"]
    top_growth["predicted_growth"] = top_growth["annual_growth_pct"]
    top_growth["expected_profit_usd"] = top_growth["units"] * top_growth["price_usd"] * top_growth["annual_growth_pct"] / 100
    top_growth = top_growth[top_growth["units"] > 0]
    strategies["Top Growth (naive)"] = analyze_portfolio(top_growth, cov, df)

    # Strategy 3: Best value (growth per dollar)
    df_v = df.copy()
    df_v["growth_per_dollar"] = df_v["annual_growth_pct"] / df_v["price_usd"]
    top_value = df_v.nlargest(30, "growth_per_dollar").copy()
    top_value["units"] = 0
    remaining = 1000
    for idx in top_value.index:
        price = top_value.loc[idx, "price_usd"]
        if price > 0 and remaining >= price:
            units = min(3, int(remaining / price))
            top_value.loc[idx, "units"] = units
            remaining -= units * price
    top_value["total_cost"] = top_value["units"] * top_value["price_usd"]
    top_value["predicted_growth"] = top_value["annual_growth_pct"]
    top_value["expected_profit_usd"] = top_value["units"] * top_value["price_usd"] * top_value["annual_growth_pct"] / 100
    top_value = top_value[top_value["units"] > 0]
    strategies["Best Value ($/growth)"] = analyze_portfolio(top_value, cov, df)

    # Strategy 4: Equal weight top themes
    top_themes = df.groupby("theme")["annual_growth_pct"].mean().nlargest(5).index
    theme_picks = df[df["theme"].isin(top_themes)].copy()
    theme_picks["units"] = 0
    remaining = 1000
    per_theme_budget = 200
    for theme in top_themes:
        t_sets = theme_picks[theme_picks["theme"] == theme].nlargest(3, "annual_growth_pct")
        t_remaining = per_theme_budget
        for idx in t_sets.index:
            price = theme_picks.loc[idx, "price_usd"]
            if price > 0 and t_remaining >= price:
                units = min(2, int(t_remaining / price))
                theme_picks.loc[idx, "units"] = units
                t_remaining -= units * price
    theme_picks["total_cost"] = theme_picks["units"] * theme_picks["price_usd"]
    theme_picks["predicted_growth"] = theme_picks["annual_growth_pct"]
    theme_picks["expected_profit_usd"] = theme_picks["units"] * theme_picks["price_usd"] * theme_picks["annual_growth_pct"] / 100
    theme_picks = theme_picks[theme_picks["units"] > 0]
    strategies["Theme Diversified"] = analyze_portfolio(theme_picks, cov, df)

    print(f"\n{'Strategy':<25s} {'Return':>8s} {'Std':>6s} {'Sharpe':>8s} {'VaR95':>7s} {'Sets':>5s} {'Themes':>7s}")
    print("-" * 75)
    for name, m in strategies.items():
        if m:
            print(
                f"  {name:<23s} {m['expected_return_pct']:>6.1f}% "
                f"{m['portfolio_std_pct']:>5.1f}% "
                f"{m['sharpe_ratio']:>7.2f} "
                f"{m['var_95_pct']:>5.1f}% "
                f"{m['n_sets']:>5d} "
                f"{m['n_themes']:>7d}"
            )


if __name__ == "__main__":
    main()
