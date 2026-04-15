#!/usr/bin/env python3
"""Walk-forward backtest of the Keepa+BL classifier against effective APR.

Trains per test year on all prior years, predicts on the held-out year,
then aggregates per-category realized APR (out-of-fold), plus a running
portfolio with year-by-year drawdown. This is the honest version of the
evaluate_signal.py scorecard — the scorecard is in-sample, this is OOF.

Why it matters: the classifier's CV AUC can be near-perfect on the
training universe while still failing on genuinely unseen sets. The
walk-forward tells you how much of the in-sample return is real.

Fixed LightGBM hyperparams (no Optuna) — speed over absolute fit. The
relative signal (year over year, category over category) is what we
care about here.
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path
from statistics import mean, median

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("bws.walk_forward")


# Category thresholds — match production prediction.py
AVOID_THR = 0.15        # classifier tuned threshold
GREAT_THR = 0.20        # great-buy tuned threshold
GOOD_BUY_MIN = 0.30     # p_good must exceed this to be GOOD
APR_AVOID = 10.0        # effective APR below which avoid=1
APR_GREAT = 20.0        # effective APR at/above which great=1

TOP_N = 10


def _build_feature_df() -> tuple[pd.DataFrame, list[str], dict[str, float]]:
    """Reproduce keepa_training.py feature engineering end-to-end.

    Returns the feature DataFrame, the classifier feature name list, and
    the effective-APR target dict.
    """
    from db.pg.engine import get_engine
    from services.ml.growth.keepa_features import (
        CLASSIFIER_FEATURES,
        GT_FEATURES,
        compute_theme_keepa_stats,
        encode_theme_keepa_features,
        engineer_gt_features,
        engineer_keepa_bl_features,
    )
    from services.ml.growth.minifig_value_features import (
        MINIFIG_VALUE_FEATURE_NAMES,
        NO_MINIFIG_SENTINEL,
        load_minifig_value_features,
        merge_minifig_value,
    )
    from services.ml.growth.sales_velocity_features import (
        NO_SALES_SENTINEL,
        SALES_VELOCITY_FEATURE_NAMES,
        load_sales_velocity_features,
        merge_sales_velocity,
    )
    from services.ml.growth.seasonality_features import (
        Q4_FEATURE_NAMES,
        engineer_q4_seasonal_features,
    )
    from services.ml.pg_queries import (
        load_bl_ground_truth,
        load_google_trends_data,
        load_keepa_bl_training_data,
    )

    engine = get_engine()

    logger.info("Loading base + Keepa + GT + effective-APR ground truth...")
    base_df, keepa_df, _ = load_keepa_bl_training_data(engine)
    gt_df = load_google_trends_data(engine)
    eff_apr = load_bl_ground_truth(engine)
    logger.info("  base=%d, keepa=%d, gt=%d, effective_apr=%d",
                len(base_df), len(keepa_df), len(gt_df), len(eff_apr))

    logger.info("Engineering Keepa+BL features...")
    df_feat = engineer_keepa_bl_features(base_df, keepa_df)

    # Q4 — drop pre-filled zeros then merge the real values
    df_feat = df_feat.drop(columns=[c for c in Q4_FEATURE_NAMES if c in df_feat.columns])
    q4_in = base_df[["set_number", "rrp_usd_cents"]].copy()
    q4_out = engineer_q4_seasonal_features(q4_in, keepa_df, cutoff_dates=None)
    q4_cols = ["set_number", *[c for c in Q4_FEATURE_NAMES if c in q4_out.columns]]
    df_feat = df_feat.merge(q4_out[q4_cols], on="set_number", how="left")

    # Velocity
    df_feat = df_feat.drop(columns=[c for c in SALES_VELOCITY_FEATURE_NAMES if c in df_feat.columns])
    df_feat = merge_sales_velocity(df_feat, load_sales_velocity_features(engine))

    # Minifig value
    df_feat = df_feat.drop(columns=[c for c in MINIFIG_VALUE_FEATURE_NAMES if c in df_feat.columns])
    df_feat = merge_minifig_value(df_feat, load_minifig_value_features(engine))

    # Theme encoding (computed on full set — leakage-safe because it's
    # grouped-by-theme aggregates, not per-set)
    theme_stats = compute_theme_keepa_stats(df_feat)
    df_feat = encode_theme_keepa_features(df_feat, theme_stats=theme_stats, training=False)

    # GT
    if gt_df is not None and not gt_df.empty:
        gt_feat = engineer_gt_features(gt_df, base_df)
        df_feat = df_feat.merge(gt_feat, on="set_number", how="left")
    for col in GT_FEATURES:
        if col not in df_feat.columns:
            df_feat[col] = 0.0
        else:
            df_feat[col] = df_feat[col].fillna(0.0)

    # Attach effective-APR target and year_retired
    df_feat["eff_apr"] = df_feat["set_number"].astype(str).map(eff_apr)
    df_feat = df_feat.dropna(subset=["eff_apr"]).reset_index(drop=True)

    year_retired_map = {
        str(r["set_number"]): r.get("year_retired")
        for _, r in base_df.iterrows()
    }
    df_feat["yr"] = (
        df_feat["set_number"].astype(str).map(year_retired_map)
    )
    df_feat["yr"] = pd.to_numeric(df_feat["yr"], errors="coerce")
    df_feat = df_feat.dropna(subset=["yr"]).reset_index(drop=True)
    df_feat["yr"] = df_feat["yr"].astype(int)

    feature_names = [f for f in CLASSIFIER_FEATURES if f in df_feat.columns]

    # Fill sentinels for coverage-gated features, median for the rest
    q4_set = set(Q4_FEATURE_NAMES)
    velocity_set = set(SALES_VELOCITY_FEATURE_NAMES)
    minifig_set = set(MINIFIG_VALUE_FEATURE_NAMES)
    gated = q4_set | velocity_set | minifig_set

    fillable = [c for c in feature_names if c not in gated]
    base_med = df_feat[fillable].median()
    df_feat[fillable] = df_feat[fillable].fillna(base_med)

    for c in feature_names:
        if c in q4_set:
            df_feat[c] = df_feat[c].fillna(-999.0)
        elif c in velocity_set:
            df_feat[c] = df_feat[c].fillna(NO_SALES_SENTINEL)
        elif c in minifig_set:
            df_feat[c] = df_feat[c].fillna(NO_MINIFIG_SENTINEL)

    logger.info("  %d sets × %d features, year range %d-%d",
                len(df_feat), len(feature_names),
                df_feat["yr"].min(), df_feat["yr"].max())
    return df_feat, feature_names, eff_apr


def _fit_predict(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_te: np.ndarray,
) -> np.ndarray:
    """Fit a LightGBM classifier and return P(class=1) on X_te."""
    import lightgbm as lgb

    pos = int(y_tr.sum())
    neg = int(len(y_tr) - pos)
    if pos < 3 or neg < 3:
        return np.full(len(X_te), pos / max(1, len(y_tr)))

    spw = neg / pos if pos > 0 else 1.0
    clf = lgb.LGBMClassifier(
        n_estimators=250,
        max_depth=5,
        num_leaves=20,
        min_child_samples=10,
        learning_rate=0.05,
        reg_alpha=0.1,
        reg_lambda=0.1,
        scale_pos_weight=spw,
        verbose=-1,
    )
    clf.fit(X_tr, y_tr)
    return clf.predict_proba(X_te)[:, 1]


def _categorize(p_avoid: float, p_great: float) -> str:
    p_good = max(0.0, min(1.0, (1.0 - p_avoid) - p_great))
    if p_great >= GREAT_THR and p_great > p_avoid:
        return "GREAT"
    if p_avoid >= AVOID_THR:
        return "WORST"
    if p_good >= GOOD_BUY_MIN:
        return "GOOD"
    return "SKIP"


def _run_walk_forward(df: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    """Walk year by year; each test year trained on strictly prior years."""
    X = df[feature_names].values.astype(float)
    y_apr = df["eff_apr"].values.astype(float)
    years = df["yr"].values.astype(int)
    unique_years = sorted(set(years.tolist()))

    rows: list[dict] = []
    for test_year in unique_years:
        train_mask = years < test_year
        test_mask = years == test_year
        if train_mask.sum() < 100 or test_mask.sum() < 5:
            logger.info("  skip year %d (train=%d test=%d)",
                        test_year, train_mask.sum(), test_mask.sum())
            continue

        X_tr, X_te = X[train_mask], X[test_mask]
        y_tr, y_te = y_apr[train_mask], y_apr[test_mask]

        y_avoid_tr = (y_tr < APR_AVOID).astype(int)
        y_great_tr = (y_tr >= APR_GREAT).astype(int)

        p_avoid = _fit_predict(X_tr, y_avoid_tr, X_te)
        p_great = _fit_predict(X_tr, y_great_tr, X_te)

        logger.info("  year=%d  train=%d  test=%d  "
                    "(avoid pos=%d  great pos=%d)",
                    test_year, train_mask.sum(), test_mask.sum(),
                    y_avoid_tr.sum(), y_great_tr.sum())

        test_sets = df.loc[test_mask, "set_number"].values
        for i in range(len(X_te)):
            rows.append({
                "year": test_year,
                "set_number": test_sets[i],
                "apr": y_te[i],
                "p_avoid": p_avoid[i],
                "p_great": p_great[i],
                "category": _categorize(p_avoid[i], p_great[i]),
            })

    return pd.DataFrame(rows)


def _scorecard(df: pd.DataFrame, label: str) -> None:
    print(f"\n{label}")
    print("-" * 80)
    for cat in ("GREAT", "GOOD", "SKIP", "WORST"):
        sub = df[df["category"] == cat]
        if len(sub) == 0:
            print(f"  {cat:6} n=   0  (empty)")
            continue
        aprs = sub["apr"].values
        mean_apr = aprs.mean()
        med_apr = float(pd.Series(aprs).median())
        win10 = (aprs >= 10).mean() * 100
        win20 = (aprs >= 20).mean() * 100
        neg = (aprs < 0).mean() * 100
        print(
            f"  {cat:6} n={len(sub):4d}  mean={mean_apr:6.2f}%  "
            f"median={med_apr:6.2f}%  ≥10%={win10:5.1f}%  ≥20%={win20:5.1f}%  "
            f"neg={neg:5.1f}%"
        )


def _portfolio_sim(df: pd.DataFrame) -> None:
    """Equal-weight top-N GREAT picks per year, track running return & drawdown."""
    print("\nPORTFOLIO SIMULATOR (top-N GREAT per year, equal weight)")
    print("-" * 80)

    portfolio_value = 1.0
    running_peak = 1.0
    max_drawdown = 0.0
    year_rows: list[dict] = []

    for year in sorted(df["year"].unique()):
        picks = df[(df["year"] == year) & (df["category"] == "GREAT")].copy()
        picks = picks.sort_values("p_great", ascending=False).head(TOP_N)
        if picks.empty:
            year_rows.append({"year": year, "n": 0})
            continue

        aprs = picks["apr"].values
        year_return = float(aprs.mean()) / 100.0
        portfolio_value *= (1.0 + year_return)
        running_peak = max(running_peak, portfolio_value)
        dd = (running_peak - portfolio_value) / running_peak
        max_drawdown = max(max_drawdown, dd)

        year_rows.append({
            "year": year,
            "n": len(picks),
            "mean_apr": float(aprs.mean()),
            "worst": float(aprs.min()),
            "best": float(aprs.max()),
            "losers": int((aprs < 0).sum()),
            "pv": portfolio_value,
            "dd": dd * 100,
        })

    print(f"  {'year':<6} {'n':>4} {'mean_apr':>10} {'worst':>10} "
          f"{'best':>10} {'losers':>7} {'portf.val':>10} {'dd%':>7}")
    for r in year_rows:
        if r.get("n", 0) == 0:
            print(f"  {r['year']:<6} (no GREAT picks)")
            continue
        print(
            f"  {r['year']:<6} {r['n']:>4} {r['mean_apr']:>9.2f}% "
            f"{r['worst']:>9.2f}% {r['best']:>9.2f}% {r['losers']:>7} "
            f"{r['pv']:>10.3f} {r['dd']:>6.1f}%"
        )

    total_years = sum(1 for r in year_rows if r.get("n", 0) > 0)
    if total_years:
        cagr = (portfolio_value ** (1.0 / total_years) - 1.0) * 100
        print()
        print(f"  Final portfolio value:  {portfolio_value:.3f} "
              f"({(portfolio_value - 1) * 100:+.2f}% over {total_years} years)")
        print(f"  Compound annual return: {cagr:.2f}%")
        print(f"  Max drawdown:           {max_drawdown * 100:.1f}%")


def _per_year_breakdown(df: pd.DataFrame) -> None:
    print("\nPER-YEAR BREAKDOWN (all categories)")
    print("-" * 80)
    print(f"  {'year':<6} {'n_test':>7} {'GREAT':>7} {'GOOD':>7} "
          f"{'WORST':>7} {'mean':>8} {'median':>8} {'% neg':>7}")
    for year in sorted(df["year"].unique()):
        sub = df[df["year"] == year]
        cats = sub["category"].value_counts()
        apr = sub["apr"].values
        print(
            f"  {year:<6} {len(sub):>7} "
            f"{cats.get('GREAT', 0):>7} {cats.get('GOOD', 0):>7} "
            f"{cats.get('WORST', 0):>7} "
            f"{apr.mean():>7.2f}% {float(pd.Series(apr).median()):>7.2f}% "
            f"{(apr < 0).mean() * 100:>6.1f}%"
        )


def _threshold_sweep(results: pd.DataFrame) -> None:
    """Sweep great-buy threshold to find a ship-gate calibration.

    For each candidate threshold, re-classify GREAT = (p_great >= thr AND
    p_great > p_avoid) and report n, mean APR, win ≥10%, and worst loser.
    The sweep is read-only — it does not retrain, only re-labels the
    already-computed OOF probabilities.
    """
    print("\n" + "=" * 80)
    print("GREAT-THRESHOLD SWEEP  (re-classify OOF without retraining)")
    print("=" * 80)
    print(f"  {'thr':>5} {'n':>4} {'mean_apr':>10} {'median':>9} "
          f"{'≥10%':>7} {'≥20%':>7} {'neg%':>7} {'worst':>10}")
    thresholds = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 0.80]
    best_ship: tuple[float, float, float, int] | None = None
    for thr in thresholds:
        mask = (results["p_great"] >= thr) & (results["p_great"] > results["p_avoid"])
        picks = results[mask]
        n = len(picks)
        if n == 0:
            print(f"  {thr:>5.2f}    0  (empty)")
            continue
        aprs = picks["apr"].values
        mean_apr = float(aprs.mean())
        med = float(pd.Series(aprs).median())
        w10 = (aprs >= 10).mean() * 100
        w20 = (aprs >= 20).mean() * 100
        neg = (aprs < 0).mean() * 100
        worst = float(aprs.min())
        star = ""
        ships = mean_apr >= 15 and w10 >= 80
        if ships and (best_ship is None or mean_apr > best_ship[1]):
            best_ship = (thr, mean_apr, w10, n)
            star = "  ← SHIP"
        print(f"  {thr:>5.2f} {n:>4d} {mean_apr:>9.2f}% {med:>8.2f}% "
              f"{w10:>6.1f}% {w20:>6.1f}% {neg:>6.1f}% {worst:>9.2f}%{star}")

    if best_ship is not None:
        thr, mean_apr, w10, n = best_ship
        print(f"\n  First threshold clearing the ship gate: "
              f"p_great ≥ {thr:.2f}  (n={n}, mean={mean_apr:.1f}%, win={w10:.1f}%)")
    else:
        print("\n  No threshold cleared the ship gate (mean ≥15% AND win ≥80%).")


def main() -> None:
    df_feat, feature_names, _ = _build_feature_df()

    logger.info("Starting walk-forward...")
    results = _run_walk_forward(df_feat, feature_names)

    print("\n" + "=" * 80)
    print("WALK-FORWARD BACKTEST — effective APR target")
    print("=" * 80)
    print(f"Features: {len(feature_names)}   OOF predictions: {len(results)}")

    _scorecard(results, "OOF CATEGORY SCORECARD")
    _per_year_breakdown(results)
    _portfolio_sim(results)
    _threshold_sweep(results)

    print("\n" + "=" * 80)
    print("DECISION SIGNAL (OOF)")
    print("=" * 80)
    great = results[results["category"] == "GREAT"]["apr"]
    if len(great):
        print(f"  GREAT bucket mean APR:   {great.mean():.2f}%   (ship gate ≥15%)")
        print(f"  GREAT bucket win ≥10%:   {(great >= 10).mean() * 100:.1f}%    (ship gate ≥80%)")
        verdict = "SHIP" if great.mean() >= 15 and (great >= 10).mean() >= 0.80 else "CALIBRATE"
        print(f"  Verdict:                 {verdict}")
    else:
        print("  No GREAT picks across walk-forward — CALIBRATE")


if __name__ == "__main__":
    main()
