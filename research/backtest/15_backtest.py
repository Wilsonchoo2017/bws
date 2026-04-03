"""
15 - Backtest: Would the optimizer have made money?
=====================================================
Simulate buying sets at release/RRP, measure actual returns
from candlestick data at 12m and 24m horizons.

Compare strategies:
1. ML optimizer (train on N-1 sets, predict the held-out one) -- LOO backtest
2. Naive: buy top N by growth prediction
3. Random: buy N random sets
4. Equal weight: buy one of everything
5. Cheapest high-growth: maximize units of cheap predicted-good sets

Run with: .venv/bin/python research/15_backtest.py
"""

import json
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import LeaveOneOut
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

DB_PATH = Path.home() / ".bws" / "bws.duckdb"


def load_data():
    db = duckdb.connect(str(DB_PATH), read_only=True)

    # All sets with intrinsics + candlestick
    rows = db.execute("""
        SELECT li.set_number, li.title, li.theme,
               li.parts_count, li.minifig_count,
               be.annual_growth_pct, be.rrp_usd_cents,
               be.rating_value, be.review_count,
               be.pieces, be.minifigs, be.rrp_gbp_cents,
               be.subtheme, be.candlestick_json
        FROM lego_items li
        JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0
    """).fetchdf()

    db.close()
    return rows


def parse_returns(df):
    """Extract actual 12m and 24m returns from candlestick data."""
    ret_12m = []
    ret_24m = []
    for cs_json in df["candlestick_json"]:
        cs = json.loads(cs_json) if isinstance(cs_json, str) else cs_json
        if not isinstance(cs, list) or len(cs) < 12:
            ret_12m.append(np.nan)
            ret_24m.append(np.nan)
            continue
        closes = [c[4] for c in cs if len(c) >= 5 and c[4]]
        base = closes[0] if closes else 0
        ret_12m.append((closes[11] - base) / base * 100 if len(closes) > 11 and base > 0 else np.nan)
        ret_24m.append((closes[23] - base) / base * 100 if len(closes) > 23 and base > 0 else np.nan)
    return np.array(ret_12m), np.array(ret_24m)


def engineer_features(df):
    """Build the 14 intrinsic features (same as growth_model.py)."""
    result = df.copy()
    for col in ["parts_count", "minifig_count", "rrp_usd_cents", "rrp_gbp_cents",
                "review_count", "pieces", "minifigs", "rating_value"]:
        result[col] = pd.to_numeric(result[col], errors="coerce")

    parts = result["parts_count"].fillna(result["pieces"]).fillna(0)
    rrp = result["rrp_usd_cents"].fillna(0)
    mfigs = result["minifig_count"].fillna(result["minifigs"]).fillna(0)

    result["log_rrp"] = np.log1p(rrp)
    result["log_parts"] = np.log1p(parts)
    result["price_per_part"] = np.where(parts > 0, rrp / parts, np.nan)
    result["mfigs"] = mfigs
    result["minifig_density"] = np.where(parts > 0, mfigs / parts * 100, np.nan)
    result["price_tier"] = pd.cut(rrp / 100, bins=[0, 15, 30, 50, 80, 120, 200, 500, 9999],
                                   labels=range(1, 9)).astype(float)
    result["price_usd"] = rrp / 100.0

    LICENSED = {"Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
                "Avatar", "The LEGO Movie 2", "Disney", "Minecraft", "BrickHeadz"}
    result["is_licensed"] = result["theme"].isin(LICENSED).astype(int)

    gbp = result["rrp_gbp_cents"].fillna(0)
    result["usd_gbp_ratio"] = np.where(gbp > 0, rrp / gbp, np.nan)

    return result


FEATURE_COLS = [
    "log_rrp", "log_parts", "price_per_part", "mfigs", "minifig_density",
    "price_tier", "rating_value", "review_count",
    "theme_size", "is_licensed", "usd_gbp_ratio",
]


def loo_backtest(df, actual_returns, budget=500, max_units=3, horizon_label="12m"):
    """Leave-one-out backtest: for each set, train on all others, predict it.

    Then simulate portfolio strategies using the predictions.
    """
    has_return = ~np.isnan(actual_returns)
    df_bt = df[has_return].copy().reset_index(drop=True)
    y_actual = actual_returns[has_return]
    n = len(df_bt)

    # Prepare features
    y_train_target = df_bt["annual_growth_pct"].values.astype(float)

    # Theme encoding (LOO Bayesian)
    gm = y_train_target.mean()
    alpha = 20

    # Compute theme stats
    theme_sum = df_bt.groupby("theme")["annual_growth_pct"].transform("sum")
    theme_cnt = df_bt.groupby("theme")["annual_growth_pct"].transform("count")
    df_bt["theme_bayes"] = np.where(
        theme_cnt > 1,
        ((theme_sum - y_train_target) + alpha * gm) / (theme_cnt - 1 + alpha),
        gm,
    )
    df_bt["theme_size"] = df_bt["theme"].map(df_bt["theme"].value_counts())

    # Subtheme LOO
    sub_sum = df_bt.groupby("subtheme")["annual_growth_pct"].transform("sum")
    sub_cnt = df_bt.groupby("subtheme")["annual_growth_pct"].transform("count")
    df_bt["subtheme_loo"] = np.where(
        sub_cnt >= 3,
        (sub_sum - y_train_target) / (sub_cnt - 1),
        gm,
    )
    df_bt["sub_size"] = df_bt["subtheme"].map(df_bt["subtheme"].value_counts()).fillna(0)

    all_feats = FEATURE_COLS + ["theme_bayes", "subtheme_loo", "sub_size"]
    valid = [f for f in all_feats if f in df_bt.columns]

    X = df_bt[valid].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(X.median())

    # LOO predictions using BE growth as training target
    scaler = StandardScaler()
    Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)
    model = GradientBoostingRegressor(
        n_estimators=250, max_depth=4, min_samples_leaf=6,
        learning_rate=0.02, random_state=42,
    )

    from sklearn.model_selection import cross_val_predict
    predicted = cross_val_predict(model, Xs, y_train_target, cv=LeaveOneOut())

    prices = df_bt["price_usd"].values
    themes = df_bt["theme"].values

    print(f"\n{'='*80}")
    print(f"BACKTEST: {horizon_label} returns, budget=${budget}, {n} sets")
    print(f"{'='*80}")
    print(f"Actual returns: mean={y_actual.mean():.1f}%, median={np.median(y_actual):.1f}%")
    print(f"Predicted (LOO): mean={predicted.mean():.1f}%, corr={np.corrcoef(y_actual, predicted)[0,1]:.3f}")

    # === STRATEGY 1: ML Optimizer (mean-variance knapsack) ===
    def run_optimizer(preds, prices, themes, budget, max_u, risk_lambda=0.5):
        n_s = len(preds)
        std_est = 5.67
        variances = np.full(n_s, std_est**2 + 7.0**2)  # prediction + theme noise
        risk_adj = preds - risk_lambda * np.sqrt(variances)
        scores = np.where(prices > 0, risk_adj / prices, 0)

        result = milp(
            c=-scores,
            constraints=LinearConstraint(prices.reshape(1, -1), lb=0, ub=budget),
            integrality=np.ones(n_s),
            bounds=Bounds(lb=0, ub=max_u),
        )
        if result.success:
            return np.round(result.x).astype(int)
        # Greedy fallback
        order = np.argsort(-scores)
        allocs = np.zeros(n_s, dtype=int)
        rem = budget
        for idx in order:
            if prices[idx] > 0:
                u = min(max_u, int(rem / prices[idx]))
                if u > 0:
                    allocs[idx] = u
                    rem -= u * prices[idx]
        return allocs

    def eval_portfolio(allocs, prices, actual_rets, label):
        mask = allocs > 0
        if mask.sum() == 0:
            print(f"  {label:35s} NO ALLOCATION")
            return 0
        costs = allocs * prices
        total_cost = costs.sum()
        profits = costs * actual_rets / 100
        total_profit = profits.sum()
        port_return = total_profit / total_cost * 100 if total_cost > 0 else 0
        n_sets = mask.sum()
        n_units = allocs.sum()
        n_th = len(set(themes[mask]))
        # Per-set returns
        set_returns = actual_rets[mask]
        win_rate = (set_returns > 0).mean() * 100
        worst = set_returns.min()
        best = set_returns.max()
        print(f"  {label:35s} return={port_return:>+6.1f}%  profit=${total_profit:>6.0f}  "
              f"sets={n_sets:>2d} units={n_units:>2d} themes={n_th:>2d}  "
              f"win={win_rate:.0f}%  worst={worst:>+.0f}%  best={best:>+.0f}%")
        return port_return

    # Strategy 1a: Optimizer aggressive
    alloc_agg = run_optimizer(predicted, prices, themes, budget, max_units, risk_lambda=0.1)
    eval_portfolio(alloc_agg, prices, y_actual, "ML Optimizer (aggressive)")

    # Strategy 1b: Optimizer balanced
    alloc_bal = run_optimizer(predicted, prices, themes, budget, max_units, risk_lambda=0.5)
    eval_portfolio(alloc_bal, prices, y_actual, "ML Optimizer (balanced)")

    # Strategy 1c: Optimizer conservative
    alloc_con = run_optimizer(predicted, prices, themes, budget, max_units, risk_lambda=1.0)
    eval_portfolio(alloc_con, prices, y_actual, "ML Optimizer (conservative)")

    # === STRATEGY 2: Naive top N by predicted growth ===
    top_idx = np.argsort(-predicted)
    alloc_top = np.zeros(n, dtype=int)
    rem = budget
    for idx in top_idx:
        if prices[idx] > 0:
            u = min(max_units, int(rem / prices[idx]))
            if u > 0:
                alloc_top[idx] = u
                rem -= u * prices[idx]
    eval_portfolio(alloc_top, prices, y_actual, "Top Predicted Growth (greedy)")

    # === STRATEGY 3: Cheapest high-growth (growth/$ ratio) ===
    growth_per_dollar = np.where(prices > 0, predicted / prices, 0)
    gpd_idx = np.argsort(-growth_per_dollar)
    alloc_gpd = np.zeros(n, dtype=int)
    rem = budget
    for idx in gpd_idx:
        if prices[idx] > 0:
            u = min(max_units, int(rem / prices[idx]))
            if u > 0:
                alloc_gpd[idx] = u
                rem -= u * prices[idx]
    eval_portfolio(alloc_gpd, prices, y_actual, "Best Growth/Dollar (greedy)")

    # === STRATEGY 4: Equal weight (1 of everything affordable) ===
    alloc_eq = np.zeros(n, dtype=int)
    order_eq = np.argsort(prices)  # cheapest first
    rem = budget
    for idx in order_eq:
        if prices[idx] > 0 and rem >= prices[idx]:
            alloc_eq[idx] = 1
            rem -= prices[idx]
    eval_portfolio(alloc_eq, prices, y_actual, "Equal Weight (1 of each, cheap first)")

    # === STRATEGY 5: Random (average of 100 random portfolios) ===
    rng = np.random.default_rng(42)
    random_returns = []
    for _ in range(100):
        perm = rng.permutation(n)
        alloc_r = np.zeros(n, dtype=int)
        rem = budget
        for idx in perm:
            if prices[idx] > 0:
                u = min(max_units, int(rem / prices[idx]))
                if u > 0:
                    alloc_r[idx] = u
                    rem -= u * prices[idx]
        costs = alloc_r * prices
        total_cost = costs.sum()
        if total_cost > 0:
            port_ret = (costs * y_actual).sum() / total_cost * 100
            random_returns.append(port_ret)
    avg_rand = np.mean(random_returns)
    std_rand = np.std(random_returns)
    print(f"  {'Random (avg of 100 portfolios)':35s} return={avg_rand:>+6.1f}% +/- {std_rand:.1f}%")

    # === STRATEGY 6: Oracle (perfect foresight) ===
    alloc_oracle = run_optimizer(y_actual, prices, themes, budget, max_units, risk_lambda=0.1)
    eval_portfolio(alloc_oracle, prices, y_actual, "ORACLE (perfect foresight)")


def main():
    df_raw = load_data()
    df = engineer_features(df_raw)

    ret_12m, ret_24m = parse_returns(df)

    print(f"Total sets: {len(df)}")
    print(f"Sets with 12m returns: {(~np.isnan(ret_12m)).sum()}")
    print(f"Sets with 24m returns: {(~np.isnan(ret_24m)).sum()}")

    # Backtest at different budgets
    for budget in [200, 500, 1000]:
        loo_backtest(df, ret_12m, budget=budget, horizon_label="12m")

    # Also 24m horizon
    loo_backtest(df, ret_24m, budget=500, horizon_label="24m")


if __name__ == "__main__":
    main()
