"""
18 - Evaluate Improved ML Pipeline
===================================
End-to-end evaluation of the improved growth model pipeline:
1. Huber loss (outlier-robust)
2. Yeo-Johnson target transformation
3. Walk-forward temporal CV
4. Conformal prediction intervals
5. SHAP per-prediction explanations

Produces a full report: OOS metrics, interval calibration, feature
importance, and profitability analysis via LOO backtest.

Run with: python research/18_evaluate_improved_pipeline.py
"""

import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bws.eval")

DB_PATH = Path.home() / ".bws" / "bws.duckdb"


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def run_evaluation():
    import duckdb
    from db.connection import get_connection

    conn = get_connection()

    # ----------------------------------------------------------------
    # 1. DATA OVERVIEW
    # ----------------------------------------------------------------
    section("1. DATA OVERVIEW")

    from services.ml.queries import (
        load_growth_training_data,
        load_keepa_timelines,
    )

    df_raw = load_growth_training_data(conn)
    keepa_df = load_keepa_timelines(conn)

    y = df_raw["annual_growth_pct"].values.astype(float)
    year_retired = pd.to_numeric(df_raw.get("year_retired"), errors="coerce")
    year_counts = year_retired.dropna().astype(int).value_counts().sort_index()

    print(f"Training sets:       {len(df_raw)}")
    print(f"With Keepa data:     {len(keepa_df)}")
    print(f"Target mean:         {np.mean(y):.1f}%")
    print(f"Target median:       {np.median(y):.1f}%")
    print(f"Target std:          {np.std(y):.1f}%")
    print(f"Target range:        [{np.min(y):.1f}%, {np.max(y):.1f}%]")
    print(f"Positive growth:     {(y > 0).sum()}/{len(y)} ({(y > 0).mean()*100:.0f}%)")
    print(f"\nRetirement year distribution:")
    for yr, cnt in year_counts.items():
        print(f"  {yr}: {cnt} sets")

    # ----------------------------------------------------------------
    # 2. TRAIN FULL PIPELINE
    # ----------------------------------------------------------------
    section("2. TRAIN FULL PIPELINE (Tier 1/2/3 + Ensemble)")

    from services.ml.growth.training import train_growth_models

    tier1, tier2, theme_stats, subtheme_stats, tier3, ensemble = train_growth_models(conn)

    print(f"\nTier 1: {tier1.n_train} sets, {len(tier1.feature_names)} features, "
          f"CV R2={tier1.cv_r2_mean:.3f} +/-{tier1.cv_r2_std:.3f}, "
          f"model={tier1.model_name}")

    if tier2:
        print(f"Tier 2: {tier2.n_train} sets, {len(tier2.feature_names)} features, "
              f"CV R2={tier2.cv_r2_mean:.3f} +/-{tier2.cv_r2_std:.3f}, "
              f"model={tier2.model_name}")
    else:
        print("Tier 2: SKIPPED (insufficient Keepa data)")

    if tier3:
        print(f"Tier 3: {tier3.n_train} sets, {len(tier3.feature_names)} features, "
              f"CV R2={tier3.cv_r2_mean:.3f} +/-{tier3.cv_r2_std:.3f}, "
              f"model={tier3.model_name}")
    else:
        print("Tier 3: SKIPPED")

    if ensemble:
        print(f"Ensemble: {ensemble.n_train} sets, CV R2={ensemble.oos_r2:.3f}")
        for name, w in ensemble.weights:
            print(f"  {name}: weight={w:.3f}")
    else:
        print("Ensemble: SKIPPED")

    # ----------------------------------------------------------------
    # 3. CONFORMAL INTERVAL CALIBRATION
    # ----------------------------------------------------------------
    section("3. CONFORMAL PREDICTION INTERVALS")

    for name, model_obj in [("Tier 1", tier1), ("Tier 2", tier2), ("Tier 3", tier3)]:
        if model_obj is None:
            continue
        cal = model_obj.conformal_calibration
        if cal is None:
            print(f"{name}: No conformal calibration (insufficient year groups)")
            continue
        scores = np.array(cal.nonconformity_scores)
        print(f"{name} (cal year={cal.calibration_year}, n={cal.n_calibration}):")
        print(f"  Median |residual|:  {np.median(scores):.2f}%")
        print(f"  90th percentile:    {np.percentile(scores, 90):.2f}%")
        print(f"  95th percentile:    {np.percentile(scores, 95):.2f}%")
        print(f"  Max:                {np.max(scores):.2f}%")

        # Example interval for a 10% predicted growth
        from services.ml.growth.conformal import predict_with_interval
        pi = predict_with_interval(10.0, cal, alpha=0.10)
        print(f"  Example: 10% predicted -> [{pi.lower}%, {pi.upper}%] (90% coverage)")

    # ----------------------------------------------------------------
    # 4. LEAKAGE-FREE EVALUATION
    # ----------------------------------------------------------------
    section("4. LEAKAGE-FREE EVALUATION (Temporal OOS)")

    from services.ml.growth.evaluation import evaluate_leakage_free

    report = evaluate_leakage_free(conn)

    print(f"Train/Test:          {report.n_train} / {report.n_test}")
    print(f"Features:            {report.n_features}")
    print(f"OOS R2:              {report.oos_r2:.3f}")
    print(f"OOS MAE:             {report.oos_mae:.2f}%")
    print(f"OOS RMSE:            {report.oos_rmse:.2f}%")
    print(f"Direction accuracy:  {report.direction_accuracy:.1f}%")
    print(f"Top quintile avg:    {report.top_quintile_avg_return:.1f}%")
    print(f"Bottom quintile avg: {report.bottom_quintile_avg_return:.1f}%")
    print(f"Quintile spread:     {report.quintile_spread:.1f}%")

    if report.warnings:
        print(f"\nWarnings:")
        for w in report.warnings:
            print(f"  - {w}")

    print(f"\nTop 10 features:")
    for name, imp in report.top_features:
        print(f"  {name:35s}  {imp:.4f}")

    # ----------------------------------------------------------------
    # 5. GENERATE PREDICTIONS
    # ----------------------------------------------------------------
    section("5. PREDICTIONS (Retiring-Soon Sets)")

    from services.ml.growth.prediction import predict_growth

    predictions = predict_growth(
        conn, tier1, tier2, theme_stats, subtheme_stats,
        only_retiring=True,
        tier3=tier3,
        ensemble=ensemble,
    )

    if predictions:
        print(f"Predictions generated: {len(predictions)}")
        print(f"\nTop 15 by predicted growth:")
        print(f"{'Set':<12} {'Title':<35} {'Growth':>7} {'CI':>16} {'Tier':>5} {'Conf':>8}")
        print("-" * 85)
        for p in predictions[:15]:
            ci = ""
            if p.prediction_interval:
                ci = f"[{p.prediction_interval.lower:+.0f}, {p.prediction_interval.upper:+.0f}]"
            title = (p.title[:33] + "..") if len(p.title) > 35 else p.title
            print(f"{p.set_number:<12} {title:<35} {p.predicted_growth_pct:+6.1f}% {ci:>16} {p.tier:>5} {p.confidence:>8}")

        # SHAP example for top prediction
        top = predictions[0]
        if top.shap_base_value is not None:
            print(f"\nSHAP explanation for top prediction ({top.set_number}):")
            print(f"  Base value: {top.shap_base_value:.1f}%")
            print(f"  Feature drivers:")
            for fname, fval in top.feature_contributions[:8]:
                direction = "+" if fval > 0 else ""
                print(f"    {fname:30s}  {direction}{fval:.2f}%")
    else:
        print("No retiring-soon sets found for prediction")

    # ----------------------------------------------------------------
    # 6. PROFITABILITY: LOO BACKTEST
    # ----------------------------------------------------------------
    section("6. LOO BACKTEST (Profitability Test)")

    _run_loo_backtest(df_raw, tier1, theme_stats, subtheme_stats)

    # ----------------------------------------------------------------
    # 7. PREDICTION TRACKING (if snapshots exist)
    # ----------------------------------------------------------------
    section("7. PREDICTION TRACKING (Predictions vs Actuals)")

    from services.ml.prediction_tracker import get_tracking_report

    tracking = get_tracking_report(conn)
    if tracking.get("total_with_actuals", 0) > 0:
        print(f"Total predictions:     {tracking['total_predictions']}")
        print(f"With actuals:          {tracking['total_with_actuals']}")
        print(f"Overall MAE:           {tracking.get('overall_mae', 'N/A')}")
        print(f"Overall correlation:   {tracking.get('overall_correlation', 'N/A')}")
        print(f"Overall R2:            {tracking.get('overall_r2', 'N/A')}")
    else:
        print("No prediction snapshots with actuals yet.")
        print("Run: python -m services.ml.prediction_tracker snapshot")
        print("Then wait for BrickEconomy to update actuals.")

    conn.close()
    print(f"\n{'=' * 60}")
    print("  EVALUATION COMPLETE")
    print(f"{'=' * 60}")


def _run_loo_backtest(
    df_raw: pd.DataFrame,
    tier1,
    theme_stats: dict,
    subtheme_stats: dict,
) -> None:
    """Leave-one-out backtest: train on N-1 sets, predict the held-out one.

    Simulates: for each retired set, what would the model have predicted?
    Then compare predicted vs actual and simulate portfolio returns.
    """
    from sklearn.model_selection import LeaveOneOut
    from sklearn.preprocessing import StandardScaler

    from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
    from services.ml.growth.model_selection import build_model

    y = df_raw["annual_growth_pct"].values.astype(float)

    # Engineer features
    df_feat, _, _ = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y),
    )
    tier1_features = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X = df_feat[tier1_features].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(X.median())

    # LOO predictions
    loo = LeaveOneOut()
    y_pred_loo = np.full(len(y), np.nan)

    model_template = build_model(tier1.model_name)
    scaler = StandardScaler()

    for train_idx, test_idx in loo.split(X):
        X_tr = scaler.fit_transform(X.iloc[train_idx])
        X_te = scaler.transform(X.iloc[test_idx])

        m = build_model(tier1.model_name)
        m.fit(X_tr, y[train_idx])
        y_pred_loo[test_idx] = m.predict(X_te)

    # Metrics
    residuals = y - y_pred_loo
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    mae = np.mean(np.abs(residuals))
    corr = np.corrcoef(y, y_pred_loo)[0, 1]

    print(f"LOO Results ({len(y)} sets):")
    print(f"  R2:              {r2:.3f}")
    print(f"  MAE:             {mae:.2f}%")
    print(f"  Correlation:     {corr:.3f}")

    # Direction accuracy
    dir_acc = np.mean(np.sign(y_pred_loo) == np.sign(y)) * 100
    print(f"  Direction acc:   {dir_acc:.1f}%")

    # Quintile analysis
    n_q = max(1, len(y) // 5)
    pred_order = np.argsort(y_pred_loo)

    top_q = y[pred_order[-n_q:]]
    bot_q = y[pred_order[:n_q]]
    print(f"\n  Top quintile (model's picks):")
    print(f"    Avg actual return: {np.mean(top_q):+.1f}%")
    print(f"    Win rate:          {(top_q > 0).mean()*100:.0f}%")
    print(f"    Best:              {np.max(top_q):+.1f}%")
    print(f"    Worst:             {np.min(top_q):+.1f}%")

    print(f"\n  Bottom quintile (model's avoids):")
    print(f"    Avg actual return: {np.mean(bot_q):+.1f}%")
    print(f"    Win rate:          {(bot_q > 0).mean()*100:.0f}%")

    spread = np.mean(top_q) - np.mean(bot_q)
    print(f"\n  Quintile spread:     {spread:+.1f}%")
    print(f"  (Higher = model successfully separates winners from losers)")

    # Simulate $1000 budget
    rrp = pd.to_numeric(df_raw["rrp_usd_cents"], errors="coerce").fillna(0).values
    _simulate_portfolio(y, y_pred_loo, rrp / 100, budget=1000)


def _simulate_portfolio(
    y_actual: np.ndarray,
    y_pred: np.ndarray,
    prices_usd: np.ndarray,
    budget: float = 1000,
) -> None:
    """Simulate portfolio returns with $budget."""
    valid = (prices_usd > 0) & np.isfinite(y_pred) & np.isfinite(y_actual)
    y_a = y_actual[valid]
    y_p = y_pred[valid]
    prices = prices_usd[valid]

    # Strategy 1: ML top picks (greedy by predicted growth)
    order = np.argsort(y_p)[::-1]
    spent = 0.0
    returns_ml: list[float] = []
    costs_ml: list[float] = []
    for idx in order:
        if spent + prices[idx] > budget:
            continue
        spent += prices[idx]
        returns_ml.append(y_a[idx] / 100 * prices[idx])
        costs_ml.append(prices[idx])
    ml_profit = sum(returns_ml)
    ml_return = ml_profit / spent * 100 if spent > 0 else 0

    # Strategy 2: Random (average of 200 trials)
    rng = np.random.RandomState(42)
    random_profits: list[float] = []
    for _ in range(200):
        perm = rng.permutation(len(prices))
        s = 0.0
        profit = 0.0
        for idx in perm:
            if s + prices[idx] > budget:
                continue
            s += prices[idx]
            profit += y_a[idx] / 100 * prices[idx]
        if s > 0:
            random_profits.append(profit / s * 100)
    avg_random = np.mean(random_profits)

    # Strategy 3: Equal weight (one of each, cheapest first)
    cheap_order = np.argsort(prices)
    spent_eq = 0.0
    returns_eq: list[float] = []
    for idx in cheap_order:
        if spent_eq + prices[idx] > budget:
            continue
        spent_eq += prices[idx]
        returns_eq.append(y_a[idx] / 100 * prices[idx])
    eq_profit = sum(returns_eq)
    eq_return = eq_profit / spent_eq * 100 if spent_eq > 0 else 0

    print(f"\n  Portfolio simulation (${budget:.0f} budget):")
    print(f"    ML Top Picks:    {ml_return:+.1f}% return  (${ml_profit:+.0f} profit, {len(returns_ml)} sets)")
    print(f"    Random avg:      {avg_random:+.1f}% return")
    print(f"    Equal weight:    {eq_return:+.1f}% return  (${eq_profit:+.0f} profit, {len(returns_eq)} sets)")
    print(f"    ML vs Random:    {ml_return - avg_random:+.1f}% alpha")


if __name__ == "__main__":
    run_evaluation()
