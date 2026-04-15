"""Backtest: does adding Q4 seasonality features improve the classifier?

Trains the BL-APR avoid/great-buy classifier pair on two feature sets:
  1. Baseline: existing TIER2 features (pre-Q4)
  2. +Q4: TIER2 + all 15 new seasonality features

Evaluation: GroupKFold by retirement year (walk-forward safe), report:
  - AUC for P(avoid) at threshold 10%
  - AUC for P(great_buy) at threshold 20%
  - Precision / recall / F1 at each threshold
  - Trading outcome: top-N by (1-P(avoid))*(1+P(great_buy)), avg actual APR

Does not touch the regressor.
"""

from __future__ import annotations

import logging
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold

from db.pg.engine import get_engine
from services.ml.growth.features import (
    TIER2_FEATURES,
    engineer_intrinsic_features,
    engineer_keepa_features,
)
from services.ml.growth.seasonality_features import (
    Q4_FEATURE_NAMES,
    engineer_q4_seasonal_features,
)
from services.ml.pg_queries import (
    load_bl_ground_truth,
    load_growth_training_data,
    load_keepa_timelines,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


AVOID_THRESHOLD = 10.0   # APR < 10 → avoid class (Exp 36)
GREAT_THRESHOLD = 20.0   # APR >= 20 → great-buy class
TOP_N_PER_YEAR = 10      # How many sets to "buy" per test year for trading eval


def _load() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    engine = get_engine()
    logger.info("Loading training data...")
    df_raw = load_growth_training_data(engine)
    keepa_df = load_keepa_timelines(engine)
    bl_apr = load_bl_ground_truth(engine)
    logger.info(
        "  %d training sets, %d Keepa rows, %d BL APR ground-truth sets",
        len(df_raw), len(keepa_df), len(bl_apr),
    )
    return df_raw, keepa_df, bl_apr


def _build_features(
    df_raw: pd.DataFrame,
    keepa_df: pd.DataFrame,
) -> pd.DataFrame:
    """Engineer all features including Q4."""
    logger.info("Engineering features...")
    y_all = df_raw["annual_growth_pct"].values.astype(float)
    df_feat, _, _ = engineer_intrinsic_features(df_raw, training_target=pd.Series(y_all))

    cutoff_dates: dict[str, str] = {}
    df_kp = engineer_keepa_features(df_feat, keepa_df, cutoff_dates=cutoff_dates)
    df_full = engineer_q4_seasonal_features(df_kp, keepa_df, cutoff_dates=cutoff_dates)

    logger.info("  feature columns: %d", len(df_full.columns))
    return df_full


def _prepare_targets(
    df_feat: pd.DataFrame,
    bl_apr: dict[str, float],
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Filter to sets with BL APR ground truth, return (df, y_apr, year_retired)."""
    df_feat = df_feat.copy()
    df_feat["apr"] = df_feat["set_number"].astype(str).map(bl_apr)
    df_feat = df_feat.dropna(subset=["apr"]).reset_index(drop=True)

    yr = pd.to_numeric(df_feat.get("year_retired"), errors="coerce")
    df_feat = df_feat[yr.notna()].reset_index(drop=True)
    yr = pd.to_numeric(df_feat["year_retired"], errors="coerce").astype(int)

    y_apr = df_feat["apr"].values.astype(float)
    groups = yr.values

    logger.info("  ground-truth subset: %d sets across %d retire-years",
                len(df_feat), len(set(groups)))
    return df_feat, y_apr, groups


def _build_X(df: pd.DataFrame, feature_names: list[str]) -> np.ndarray:
    X = df[feature_names].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(X.median())
    # Any remaining NaN (column all-NaN) → 0
    X = X.fillna(0.0)
    return X.values.astype(float)


def _train_classifier(X_tr: np.ndarray, y_tr_bin: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    """Train a lightgbm classifier and return P(class=1) on X_te."""
    import lightgbm as lgb

    if y_tr_bin.sum() < 3 or (1 - y_tr_bin).sum() < 3:
        return np.full(len(X_te), y_tr_bin.mean())

    pos = float(y_tr_bin.sum())
    neg = float(len(y_tr_bin) - pos)
    spw = neg / pos if pos > 0 else 1.0

    clf = lgb.LGBMClassifier(
        n_estimators=200,
        max_depth=5,
        num_leaves=20,
        min_child_samples=10,
        learning_rate=0.05,
        reg_alpha=0.1,
        reg_lambda=0.1,
        scale_pos_weight=spw,
        verbose=-1,
    )
    clf.fit(X_tr, y_tr_bin)
    return clf.predict_proba(X_te)[:, 1]


def _walk_forward_eval(
    X: np.ndarray,
    y_apr: np.ndarray,
    groups: np.ndarray,
    label: str,
) -> dict:
    """GroupKFold by retirement year. Returns dict with AUCs and trading metrics."""
    unique_years = sorted(set(groups.tolist()))
    if len(unique_years) < 4:
        raise ValueError(f"Need ≥4 retire years, got {unique_years}")

    logger.info("  [%s] walk-forward over %s", label, unique_years)

    y_avoid = (y_apr < AVOID_THRESHOLD).astype(int)
    y_great = (y_apr >= GREAT_THRESHOLD).astype(int)

    avoid_oof = np.full(len(y_apr), np.nan)
    great_oof = np.full(len(y_apr), np.nan)
    trade_rows: list[dict] = []

    for i, test_year in enumerate(unique_years):
        if i < 2:  # need at least 2 years of training data
            continue
        test_mask = groups == test_year
        train_mask = groups < test_year

        if test_mask.sum() < 5 or train_mask.sum() < 50:
            continue

        X_tr, X_te = X[train_mask], X[test_mask]

        avoid_p_te = _train_classifier(X_tr, y_avoid[train_mask], X_te)
        great_p_te = _train_classifier(X_tr, y_great[train_mask], X_te)

        avoid_oof[test_mask] = avoid_p_te
        great_oof[test_mask] = great_p_te

        # Trading: top-N by score = (1 - P(avoid)) * (1 + P(great_buy))
        score = (1.0 - avoid_p_te) * (1.0 + great_p_te)
        n_buy = min(TOP_N_PER_YEAR, len(X_te))
        top_idx = np.argsort(score)[::-1][:n_buy]
        actuals = y_apr[test_mask]
        for k in top_idx:
            trade_rows.append({
                "year": test_year,
                "actual_apr": float(actuals[k]),
                "avoid_p": float(avoid_p_te[k]),
                "great_p": float(great_p_te[k]),
            })

    # Metrics (only on rows with OOF predictions)
    m = ~np.isnan(avoid_oof)
    metrics = {"label": label, "n_oof": int(m.sum())}

    if m.sum() >= 20 and len(set(y_avoid[m])) == 2:
        metrics["avoid_auc"] = float(roc_auc_score(y_avoid[m], avoid_oof[m]))
        metrics["avoid_ap"] = float(average_precision_score(y_avoid[m], avoid_oof[m]))
        yhat = (avoid_oof[m] >= 0.5).astype(int)
        metrics["avoid_prec"] = float(precision_score(y_avoid[m], yhat, zero_division=0))
        metrics["avoid_rec"] = float(recall_score(y_avoid[m], yhat, zero_division=0))
        metrics["avoid_f1"] = float(f1_score(y_avoid[m], yhat, zero_division=0))

    m2 = ~np.isnan(great_oof)
    if m2.sum() >= 20 and len(set(y_great[m2])) == 2:
        metrics["great_auc"] = float(roc_auc_score(y_great[m2], great_oof[m2]))
        metrics["great_ap"] = float(average_precision_score(y_great[m2], great_oof[m2]))
        yhat = (great_oof[m2] >= 0.5).astype(int)
        metrics["great_prec"] = float(precision_score(y_great[m2], yhat, zero_division=0))
        metrics["great_rec"] = float(recall_score(y_great[m2], yhat, zero_division=0))
        metrics["great_f1"] = float(f1_score(y_great[m2], yhat, zero_division=0))

    if trade_rows:
        trades = pd.DataFrame(trade_rows)
        metrics["n_trades"] = len(trades)
        metrics["avg_actual_apr"] = float(trades["actual_apr"].mean())
        metrics["median_actual_apr"] = float(trades["actual_apr"].median())
        metrics["win_rate_10pct"] = float((trades["actual_apr"] >= 10).mean() * 100)
        metrics["win_rate_20pct"] = float((trades["actual_apr"] >= 20).mean() * 100)
        # How many picks beat the 10% APR hurdle and the 20% "great" target
        metrics["pct_negative"] = float((trades["actual_apr"] < 0).mean() * 100)

    return metrics


def _report(baseline: dict, augmented: dict) -> None:
    logger.info("")
    logger.info("=" * 70)
    logger.info("RESULTS: baseline (TIER2 pre-Q4)  vs  +Q4 (TIER2 + 15 seasonality features)")
    logger.info("=" * 70)

    fmt = "  %-20s  %10s  %10s  %+10s"
    logger.info(fmt, "metric", "baseline", "+Q4", "delta")
    logger.info("  " + "-" * 60)

    keys = [
        ("n_oof", "{:d}"),
        ("avoid_auc", "{:.4f}"),
        ("avoid_ap", "{:.4f}"),
        ("avoid_f1", "{:.4f}"),
        ("avoid_prec", "{:.4f}"),
        ("avoid_rec", "{:.4f}"),
        ("great_auc", "{:.4f}"),
        ("great_ap", "{:.4f}"),
        ("great_f1", "{:.4f}"),
        ("great_prec", "{:.4f}"),
        ("great_rec", "{:.4f}"),
        ("n_trades", "{:d}"),
        ("avg_actual_apr", "{:.2f}%"),
        ("median_actual_apr", "{:.2f}%"),
        ("win_rate_10pct", "{:.1f}%"),
        ("win_rate_20pct", "{:.1f}%"),
        ("pct_negative", "{:.1f}%"),
    ]
    for key, fmt_str in keys:
        b = baseline.get(key)
        a = augmented.get(key)
        if b is None or a is None:
            continue
        bs = fmt_str.format(b)
        as_ = fmt_str.format(a)
        try:
            diff = a - b
            ds = f"{diff:+.4f}" if isinstance(b, float) else f"{diff:+d}"
        except TypeError:
            ds = ""
        logger.info(fmt, key, bs, as_, ds)


def main() -> None:
    df_raw, keepa_df, bl_apr = _load()
    df_feat = _build_features(df_raw, keepa_df)

    df, y_apr, groups = _prepare_targets(df_feat, bl_apr)

    baseline_feats = [
        f for f in TIER2_FEATURES
        if f in df.columns and f not in Q4_FEATURE_NAMES
    ]
    augmented_feats = [f for f in TIER2_FEATURES if f in df.columns]
    added = [f for f in Q4_FEATURE_NAMES if f in df.columns]

    logger.info("")
    logger.info("Feature counts: baseline=%d  +Q4=%d  (added %d Q4 features)",
                len(baseline_feats), len(augmented_feats), len(added))
    logger.info("Q4 features in use: %s", ", ".join(added) if added else "(none)")

    X_base = _build_X(df, baseline_feats)
    X_aug = _build_X(df, augmented_feats)

    baseline = _walk_forward_eval(X_base, y_apr, groups, "baseline")
    augmented = _walk_forward_eval(X_aug, y_apr, groups, "+Q4")

    _report(baseline, augmented)


if __name__ == "__main__":
    main()
