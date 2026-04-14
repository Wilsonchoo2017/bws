"""Experiment 31g: Priority improvements evaluation.

Measures each improvement in isolation and combined, using OOF metrics
on the training set (retired <= 2024) with GroupKFold by year_retired.

Improvements tested (in priority order):
  HIGH:
    1. Tune GREAT_BUY_THRESHOLD on temporal holdout
    2. Walk-forward AUC for P(great_buy) — temporal stability
    3. Calibrate for newly-retiring sets (2024 holdout)
  MEDIUM:
    4. Second classifier P(growth >= 10%) for GOOD category
    5. Asymmetric loss for regressor (penalize under-prediction of winners)
    6. Ensemble: P(great_buy) * regressor as combined signal

Run: python -m research.growth.31g_improvement_eval
"""
from __future__ import annotations

import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import (
    f1_score,
    fbeta_score,
    precision_score,
    recall_score,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, StratifiedKFold
from sklearn.preprocessing import PowerTransformer

print("=" * 70)
print("EXP 31g: PRIORITY IMPROVEMENTS EVALUATION")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.pg_queries import load_keepa_bl_training_data
from services.ml.growth.keepa_features import KEEPA_BL_FEATURES, engineer_keepa_bl_features
from services.ml.growth.model_selection import clip_outliers, compute_recency_weights

engine = get_engine()

# ============================================================================
# DATA LOADING
# ============================================================================
print("\n--- Loading data ---")
base_df, keepa_df, target_series = load_keepa_bl_training_data(engine)
print(f"Base: {len(base_df)}, Keepa: {len(keepa_df)}, Targets: {len(target_series)}")

df_feat = engineer_keepa_bl_features(base_df, keepa_df)
target_map = dict(zip(target_series.index, target_series.values))
df_feat["target"] = df_feat["set_number"].map(target_map)
df_feat = df_feat[df_feat["target"].notna()].copy()

# Add year_retired
yr_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
for _, row in base_df.iterrows():
    sn = str(row["set_number"])
    if sn not in yr_map or pd.isna(yr_map.get(sn)):
        rd = pd.to_datetime(str(row.get("retired_date", "")), errors="coerce")
        if rd is not pd.NaT:
            yr_map[sn] = rd.year
df_feat["year_retired"] = df_feat["set_number"].map(yr_map).fillna(2023).astype(int)

# Training set: retired <= 2024
train_mask = df_feat["year_retired"] <= 2024
df_train = df_feat[train_mask].copy()
df_holdout_2025 = df_feat[~train_mask].copy()

y_raw = df_train["target"].values.astype(float)
groups = df_train["year_retired"].values
feature_names = [f for f in KEEPA_BL_FEATURES if f in df_train.columns]
X_raw = df_train[feature_names].fillna(0).copy()
fill_values = X_raw.median()
X_raw = X_raw.fillna(fill_values)

lo, hi = np.percentile(y_raw, [2, 98])
y_clip = np.clip(y_raw, lo, hi)
y_growth_pct = (y_clip - 1.0) * 100

X_arr = clip_outliers(X_raw).values.astype(float)
sample_weight = compute_recency_weights(groups.astype(float))

print(f"Training: {len(df_train)} sets (retired <= 2024)")
print(f"Holdout 2025+: {len(df_holdout_2025)} sets")
print(f"Features: {len(feature_names)}")
print(f"Target: BL/RRP ratio (mean={y_raw.mean():.3f}, median={np.median(y_raw):.3f})")
print(f"Growth %: mean={y_growth_pct.mean():.1f}%, great_buy (>=20%): {(y_growth_pct >= 20).sum()} ({(y_growth_pct >= 20).mean()*100:.1f}%)")
print(f"Avoid (growth < 0%): {(y_growth_pct < 0).sum()} ({(y_growth_pct < 0).mean()*100:.1f}%)")
print(f"Good buy (>=10%): {(y_growth_pct >= 10).sum()} ({(y_growth_pct >= 10).mean()*100:.1f}%)")

import lightgbm as lgb

LGB_PARAMS = {
    "objective": "huber", "metric": "mae",
    "learning_rate": 0.068, "num_leaves": 20, "max_depth": 8,
    "min_child_samples": 19, "subsample": 0.60,
    "colsample_bytree": 0.88, "reg_alpha": 0.35,
    "reg_lambda": 0.009, "verbosity": -1,
}

n_splits = min(5, len(np.unique(groups)))
gkf = GroupKFold(n_splits=n_splits)


def _train_classifier_oof(
    X: np.ndarray,
    y_binary: np.ndarray,
    groups: np.ndarray,
    params: dict | None = None,
) -> np.ndarray:
    """OOF probabilities for a binary classifier using GroupKFold."""
    from sklearn.preprocessing import StandardScaler

    clf_params = params or {
        "objective": "binary", "metric": "auc",
        "learning_rate": 0.05, "num_leaves": 15, "max_depth": 4,
        "min_child_samples": 10, "is_unbalance": True,
        "reg_alpha": 0.1, "reg_lambda": 1.0, "verbosity": -1,
    }

    oof_probs = np.full(len(y_binary), np.nan)
    n_sp = min(5, len(np.unique(groups)))
    gkf_c = GroupKFold(n_splits=n_sp)

    for tr_idx, va_idx in gkf_c.split(X, y_binary, groups):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X[tr_idx])
        X_va = scaler.transform(X[va_idx])

        clf = lgb.LGBMClassifier(
            n_estimators=200, **clf_params, random_state=42, n_jobs=1,
        )
        clf.fit(X_tr, y_binary[tr_idx])
        oof_probs[va_idx] = clf.predict_proba(X_va)[:, 1]

    return oof_probs


def _regressor_oof(
    X: np.ndarray,
    y_clip: np.ndarray,
    groups: np.ndarray,
    sample_weight: np.ndarray | None,
    params: dict | None = None,
    custom_obj: object = None,
) -> np.ndarray:
    """OOF predictions for the regressor using GroupKFold."""
    lgb_params = params or LGB_PARAMS
    tt = PowerTransformer(method="yeo-johnson")
    y_t = tt.fit_transform(y_clip.reshape(-1, 1)).ravel()

    oof = np.full(len(y_clip), np.nan)
    n_sp = min(5, len(np.unique(groups)))
    gkf_r = GroupKFold(n_splits=n_sp)

    for tr_idx, va_idx in gkf_r.split(X, y_t, groups):
        w = sample_weight[tr_idx] if sample_weight is not None else None
        dtrain = lgb.Dataset(X[tr_idx], label=y_t[tr_idx], feature_name=feature_names, weight=w)
        dval = lgb.Dataset(X[va_idx], label=y_t[va_idx], feature_name=feature_names, reference=dtrain)

        train_params = dict(lgb_params)
        if custom_obj is not None:
            train_params.pop("objective", None)
            train_params["objective"] = custom_obj

        model = lgb.train(
            train_params, dtrain, num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        pred_t = model.predict(X[va_idx])
        oof[va_idx] = tt.inverse_transform(pred_t.reshape(-1, 1)).ravel()

    return oof


def _eval_buy_decision(
    oof_growth: np.ndarray,
    actual_growth: np.ndarray,
    avoid_proba: np.ndarray | None,
    great_buy_proba: np.ndarray | None,
    good_buy_proba: np.ndarray | None = None,
    avoid_threshold: float = 0.5,
    great_threshold: float = 0.5,
    good_threshold: float = 0.5,
    good_regressor_hurdle: float = 10.0,
    label: str = "",
) -> dict:
    """Evaluate buy decision quality across all 4 categories."""
    n = len(oof_growth)
    categories = np.full(n, "SKIP", dtype=object)

    # WORST: P(avoid) >= threshold
    if avoid_proba is not None:
        categories[avoid_proba >= avoid_threshold] = "WORST"

    # GREAT: P(great_buy) >= threshold (and not WORST)
    if great_buy_proba is not None:
        great_mask = (great_buy_proba >= great_threshold) & (categories != "WORST")
        categories[great_mask] = "GREAT"

    # GOOD: P(good_buy) >= threshold OR regressor >= hurdle (and not WORST/GREAT)
    remaining = (categories == "SKIP")
    if good_buy_proba is not None:
        good_mask = remaining & (good_buy_proba >= good_threshold)
        categories[good_mask] = "GOOD"
        remaining = (categories == "SKIP")

    # GOOD fallback: regressor >= hurdle
    good_reg_mask = remaining & (oof_growth >= good_regressor_hurdle)
    categories[good_reg_mask] = "GOOD"

    result = {"label": label}

    for cat in ["GREAT", "GOOD", "SKIP", "WORST"]:
        mask = categories == cat
        n_cat = mask.sum()
        if n_cat == 0:
            result[f"{cat}_n"] = 0
            result[f"{cat}_avg_return"] = 0
            result[f"{cat}_hit_rate"] = 0
            result[f"{cat}_hit_rate_20"] = 0
            continue
        actual_cat = actual_growth[mask]
        result[f"{cat}_n"] = n_cat
        result[f"{cat}_avg_return"] = float(actual_cat.mean())
        result[f"{cat}_hit_rate"] = float((actual_cat > 0).mean() * 100)
        result[f"{cat}_hit_rate_20"] = float((actual_cat >= 20).mean() * 100)

    # Overall metrics
    buy_mask = (categories == "GREAT") | (categories == "GOOD")
    if buy_mask.sum() > 0:
        result["buy_n"] = int(buy_mask.sum())
        result["buy_avg_return"] = float(actual_growth[buy_mask].mean())
        result["buy_hit_rate"] = float((actual_growth[buy_mask] > 0).mean() * 100)
        result["buy_precision_20"] = float((actual_growth[buy_mask] >= 20).mean() * 100)
    else:
        result["buy_n"] = 0
        result["buy_avg_return"] = 0
        result["buy_hit_rate"] = 0
        result["buy_precision_20"] = 0

    worst_mask = categories == "WORST"
    if worst_mask.sum() > 0 and (actual_growth < 0).sum() > 0:
        result["worst_recall"] = float(
            (actual_growth[worst_mask] < 0).sum() / (actual_growth < 0).sum() * 100
        )
    else:
        result["worst_recall"] = 0

    return result


def _print_buy_eval(r: dict) -> None:
    """Print buy decision evaluation."""
    print(f"\n  [{r['label']}]")
    print(f"    BUY signal: n={r['buy_n']}, avg_return={r['buy_avg_return']:+.1f}%, "
          f"hit_rate(>0%)={r['buy_hit_rate']:.1f}%, precision(>=20%)={r['buy_precision_20']:.1f}%")
    for cat in ["GREAT", "GOOD", "SKIP", "WORST"]:
        n = r[f"{cat}_n"]
        if n == 0:
            print(f"    {cat:5s}: n=0")
            continue
        print(f"    {cat:5s}: n={n:4d}, avg_return={r[f'{cat}_avg_return']:+.1f}%, "
              f"hit(>0%)={r[f'{cat}_hit_rate']:.1f}%, hit(>=20%)={r[f'{cat}_hit_rate_20']:.1f}%")
    if r.get("worst_recall"):
        print(f"    WORST recall (catches losers): {r['worst_recall']:.1f}%")


# ============================================================================
# BASELINE: Current model (regressor + P(avoid) + P(great_buy))
# ============================================================================
print("\n" + "=" * 70)
print("BASELINE: OOF predictions (regressor + P(avoid) + P(great_buy))")
print("=" * 70)

# Regressor OOF
oof_ratio = _regressor_oof(X_arr, y_clip, groups, sample_weight)
oof_growth = (oof_ratio - 1.0) * 100
actual_growth = y_growth_pct

valid = ~np.isnan(oof_ratio)
r2 = r2_score(y_clip[valid], oof_ratio[valid])
sp, _ = spearmanr(y_clip[valid], oof_ratio[valid])
print(f"\nRegressor OOF: R2={r2:.3f}, Spearman={sp:.3f}")

# P(avoid) OOF
y_avoid = (y_growth_pct < 0).astype(int)
oof_avoid = _train_classifier_oof(X_arr, y_avoid, groups)
auc_avoid = roc_auc_score(y_avoid[valid], oof_avoid[valid])
print(f"P(avoid) OOF: AUC={auc_avoid:.3f}")

# P(great_buy) OOF
y_great = (y_growth_pct >= 20).astype(int)
oof_great = _train_classifier_oof(X_arr, y_great, groups)
auc_great = roc_auc_score(y_great[valid], oof_great[valid])
print(f"P(great_buy) OOF: AUC={auc_great:.3f}")

# Baseline buy decision (using default thresholds)
baseline = _eval_buy_decision(
    oof_growth[valid], actual_growth[valid],
    oof_avoid[valid], oof_great[valid],
    avoid_threshold=0.5, great_threshold=0.5,
    label="Baseline (avoid=0.5, great=0.5, good_reg=10%)",
)
_print_buy_eval(baseline)

# ============================================================================
# IMPROVEMENT 1: Tune GREAT_BUY_THRESHOLD on temporal holdout
# ============================================================================
print("\n" + "=" * 70)
print("IMPROVEMENT 1: Tune GREAT_BUY_THRESHOLD")
print("=" * 70)

# Sweep thresholds for great_buy
print("\nGreat-buy threshold sweep (OOF):")
print(f"  {'Threshold':>10s} {'n_great':>8s} {'Precision(>=20%)':>17s} {'Avg Return':>11s} {'F2(>=20%)':>10s}")
print("-" * 65)

best_great_thresh = 0.5
best_f2_great = 0.0

for thresh_int in range(20, 76, 5):
    thresh = thresh_int / 100.0
    great_mask = (oof_great[valid] >= thresh) & (oof_avoid[valid] < 0.5)
    n_great = great_mask.sum()
    if n_great < 5:
        continue
    precision_20 = (actual_growth[valid][great_mask] >= 20).mean() * 100
    avg_ret = actual_growth[valid][great_mask].mean()
    # F2 score for great_buy detection
    y_pred_great = (oof_great[valid] >= thresh).astype(int)
    f2 = fbeta_score(y_great[valid], y_pred_great, beta=2, zero_division=0)
    print(f"  {thresh:10.2f} {n_great:8d} {precision_20:16.1f}% {avg_ret:+10.1f}% {f2:9.3f}")
    if f2 > best_f2_great:
        best_f2_great = f2
        best_great_thresh = thresh

print(f"\n  Best great_buy threshold (max F2): {best_great_thresh:.2f} (F2={best_f2_great:.3f})")

# Also sweep avoid threshold
print("\nAvoid threshold sweep (OOF):")
print(f"  {'Threshold':>10s} {'n_worst':>8s} {'Recall(losers)':>15s} {'Precision':>10s} {'F2':>6s}")
print("-" * 55)

best_avoid_thresh = 0.5
best_f2_avoid = 0.0

for thresh_int in range(20, 76, 5):
    thresh = thresh_int / 100.0
    y_pred_avoid = (oof_avoid[valid] >= thresh).astype(int)
    n_worst = y_pred_avoid.sum()
    if n_worst < 5:
        continue
    prec = precision_score(y_avoid[valid], y_pred_avoid, zero_division=0) * 100
    rec = recall_score(y_avoid[valid], y_pred_avoid, zero_division=0) * 100
    f2 = fbeta_score(y_avoid[valid], y_pred_avoid, beta=2, zero_division=0)
    print(f"  {thresh:10.2f} {n_worst:8d} {rec:14.1f}% {prec:9.1f}% {f2:5.3f}")
    if f2 > best_f2_avoid:
        best_f2_avoid = f2
        best_avoid_thresh = thresh

print(f"\n  Best avoid threshold (max F2): {best_avoid_thresh:.2f} (F2={best_f2_avoid:.3f})")

# Evaluate with tuned thresholds
tuned_thresh = _eval_buy_decision(
    oof_growth[valid], actual_growth[valid],
    oof_avoid[valid], oof_great[valid],
    avoid_threshold=best_avoid_thresh,
    great_threshold=best_great_thresh,
    label=f"Tuned thresholds (avoid={best_avoid_thresh:.2f}, great={best_great_thresh:.2f})",
)
_print_buy_eval(tuned_thresh)

delta_buy_return_1 = tuned_thresh["buy_avg_return"] - baseline["buy_avg_return"]
delta_buy_precision_1 = tuned_thresh["buy_precision_20"] - baseline["buy_precision_20"]
print(f"\n  DELTA vs baseline: buy_avg_return={delta_buy_return_1:+.1f}%, "
      f"buy_precision_20={delta_buy_precision_1:+.1f}pp")

# ============================================================================
# IMPROVEMENT 2: Walk-forward AUC for P(great_buy) — temporal stability
# ============================================================================
print("\n" + "=" * 70)
print("IMPROVEMENT 2: Walk-forward AUC for P(great_buy)")
print("=" * 70)

unique_years = sorted(np.unique(groups))
print(f"\nYears available: {unique_years}")

print(f"\n  {'Test Year':>10s} {'n_test':>7s} {'n_great':>8s} {'AUC(great)':>11s} {'AUC(avoid)':>11s} {'Regressor R2':>13s} {'Spearman':>9s}")
print("-" * 80)

for test_yr in unique_years:
    if test_yr < min(unique_years) + 3:
        continue
    train_mask_wf = groups < test_yr
    test_mask_wf = groups == test_yr

    if test_mask_wf.sum() < 10:
        continue

    X_tr_wf = X_arr[train_mask_wf]
    X_te_wf = X_arr[test_mask_wf]
    y_tr_wf = y_clip[train_mask_wf]
    y_te_wf = y_clip[test_mask_wf]
    g_pct_te = (y_te_wf - 1.0) * 100

    # Regressor
    tt = PowerTransformer(method="yeo-johnson")
    y_t_tr = tt.fit_transform(y_tr_wf.reshape(-1, 1)).ravel()
    w_tr = compute_recency_weights(groups[train_mask_wf].astype(float))
    dtrain = lgb.Dataset(X_tr_wf, label=y_t_tr, feature_name=feature_names, weight=w_tr)
    model = lgb.train(LGB_PARAMS, dtrain, num_boost_round=300)
    pred_t = model.predict(X_te_wf)
    pred_ratio = tt.inverse_transform(pred_t.reshape(-1, 1)).ravel()
    pred_growth = (pred_ratio - 1.0) * 100

    sp_yr, _ = spearmanr(g_pct_te, pred_growth) if len(g_pct_te) > 5 else (0, 0)
    r2_yr = r2_score(y_te_wf, pred_ratio)

    # P(great_buy) classifier
    from sklearn.preprocessing import StandardScaler
    y_great_tr = (((y_tr_wf - 1.0) * 100) >= 20).astype(int)
    y_great_te = ((g_pct_te >= 20)).astype(int)
    n_great_te = y_great_te.sum()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr_wf)
    X_te_s = scaler.transform(X_te_wf)

    if y_great_tr.sum() >= 5:
        clf = lgb.LGBMClassifier(
            n_estimators=200, objective="binary", is_unbalance=True,
            max_depth=4, num_leaves=15, learning_rate=0.05,
            verbosity=-1, random_state=42, n_jobs=1,
        )
        clf.fit(X_tr_s, y_great_tr)
        great_proba = clf.predict_proba(X_te_s)[:, 1]
        auc_great_yr = roc_auc_score(y_great_te, great_proba) if n_great_te > 0 and n_great_te < len(y_great_te) else 0
    else:
        auc_great_yr = 0

    # P(avoid) classifier
    y_avoid_tr = (((y_tr_wf - 1.0) * 100) < 0).astype(int)
    y_avoid_te = ((g_pct_te < 0)).astype(int)

    if y_avoid_tr.sum() >= 5:
        clf_a = lgb.LGBMClassifier(
            n_estimators=200, objective="binary", is_unbalance=True,
            max_depth=4, num_leaves=15, learning_rate=0.05,
            verbosity=-1, random_state=42, n_jobs=1,
        )
        clf_a.fit(X_tr_s, y_avoid_tr)
        avoid_proba = clf_a.predict_proba(X_te_s)[:, 1]
        n_avoid_te = y_avoid_te.sum()
        auc_avoid_yr = roc_auc_score(y_avoid_te, avoid_proba) if n_avoid_te > 0 and n_avoid_te < len(y_avoid_te) else 0
    else:
        auc_avoid_yr = 0

    print(f"  {test_yr:10d} {test_mask_wf.sum():7d} {n_great_te:8d} "
          f"{auc_great_yr:10.3f} {auc_avoid_yr:10.3f} "
          f"{r2_yr:12.3f} {sp_yr:8.3f}")

# ============================================================================
# IMPROVEMENT 3: Calibrate for newly-retiring sets (2024 holdout)
# ============================================================================
print("\n" + "=" * 70)
print("IMPROVEMENT 3: 2024 holdout performance (newly-retiring calibration)")
print("=" * 70)

# Train on <= 2023, test on 2024
train_23 = groups <= 2023
test_24 = groups == 2024

if test_24.sum() >= 10:
    X_tr_23 = X_arr[train_23]
    X_te_24 = X_arr[test_24]
    y_tr_23 = y_clip[train_23]
    y_te_24 = y_clip[test_24]
    g_pct_te_24 = (y_te_24 - 1.0) * 100

    # Regressor
    tt = PowerTransformer(method="yeo-johnson")
    y_t_tr_23 = tt.fit_transform(y_tr_23.reshape(-1, 1)).ravel()
    w_tr_23 = compute_recency_weights(groups[train_23].astype(float))
    dtrain_23 = lgb.Dataset(X_tr_23, label=y_t_tr_23, feature_name=feature_names, weight=w_tr_23)
    model_23 = lgb.train(LGB_PARAMS, dtrain_23, num_boost_round=300)
    pred_23 = tt.inverse_transform(model_23.predict(X_te_24).reshape(-1, 1)).ravel()
    pred_growth_24 = (pred_23 - 1.0) * 100

    r2_24 = r2_score(y_te_24, pred_23)
    sp_24, _ = spearmanr(g_pct_te_24, pred_growth_24)
    bias_24 = (pred_growth_24 - g_pct_te_24).mean()

    print(f"\n  2024 holdout (n={test_24.sum()}):")
    print(f"    Regressor: R2={r2_24:.3f}, Spearman={sp_24:.3f}, Bias={bias_24:+.1f}%")

    # Calibration by predicted bucket
    print(f"\n  {'Pred Bucket':>15s} {'n':>5s} {'Avg Actual':>11s} {'Avg Pred':>10s} {'Bias':>8s} {'Hit(>0%)':>9s}")
    print("  " + "-" * 65)

    for lo_b, hi_b, label in [
        (-50, 0, "<0%"), (0, 10, "0-10%"), (10, 20, "10-20%"), (20, 50, "20-50%"), (50, 200, ">50%"),
    ]:
        mask_b = (pred_growth_24 >= lo_b) & (pred_growth_24 < hi_b)
        n_b = mask_b.sum()
        if n_b < 3:
            continue
        avg_actual = g_pct_te_24[mask_b].mean()
        avg_pred = pred_growth_24[mask_b].mean()
        bias_b = avg_pred - avg_actual
        hit = (g_pct_te_24[mask_b] > 0).mean() * 100
        print(f"  {label:>15s} {n_b:5d} {avg_actual:+10.1f}% {avg_pred:+9.1f}% {bias_b:+7.1f}% {hit:8.1f}%")

    # Classifiers on 2024
    scaler24 = StandardScaler()
    X_tr_23_s = scaler24.fit_transform(X_tr_23)
    X_te_24_s = scaler24.transform(X_te_24)

    y_great_tr_23 = (((y_tr_23 - 1.0) * 100) >= 20).astype(int)
    y_great_te_24 = ((g_pct_te_24 >= 20)).astype(int)
    y_avoid_tr_23 = (((y_tr_23 - 1.0) * 100) < 0).astype(int)
    y_avoid_te_24 = ((g_pct_te_24 < 0)).astype(int)

    clf_g24 = lgb.LGBMClassifier(
        n_estimators=200, objective="binary", is_unbalance=True,
        max_depth=4, num_leaves=15, learning_rate=0.05,
        verbosity=-1, random_state=42, n_jobs=1,
    )
    clf_g24.fit(X_tr_23_s, y_great_tr_23)
    great_proba_24 = clf_g24.predict_proba(X_te_24_s)[:, 1]
    auc_g24 = roc_auc_score(y_great_te_24, great_proba_24) if y_great_te_24.sum() > 0 and y_great_te_24.sum() < len(y_great_te_24) else 0

    clf_a24 = lgb.LGBMClassifier(
        n_estimators=200, objective="binary", is_unbalance=True,
        max_depth=4, num_leaves=15, learning_rate=0.05,
        verbosity=-1, random_state=42, n_jobs=1,
    )
    clf_a24.fit(X_tr_23_s, y_avoid_tr_23)
    avoid_proba_24 = clf_a24.predict_proba(X_te_24_s)[:, 1]
    auc_a24 = roc_auc_score(y_avoid_te_24, avoid_proba_24) if y_avoid_te_24.sum() > 0 and y_avoid_te_24.sum() < len(y_avoid_te_24) else 0

    print(f"\n  2024 classifiers:")
    print(f"    P(great_buy) AUC: {auc_g24:.3f} (n_great={y_great_te_24.sum()}/{len(y_great_te_24)})")
    print(f"    P(avoid)     AUC: {auc_a24:.3f} (n_avoid={y_avoid_te_24.sum()}/{len(y_avoid_te_24)})")

    # Buy decision on 2024 holdout
    eval_24 = _eval_buy_decision(
        pred_growth_24, g_pct_te_24,
        avoid_proba_24, great_proba_24,
        avoid_threshold=best_avoid_thresh,
        great_threshold=best_great_thresh,
        label="2024 holdout with tuned thresholds",
    )
    _print_buy_eval(eval_24)
else:
    print("  Not enough 2024 sets for holdout analysis")


# ============================================================================
# IMPROVEMENT 4: Second classifier P(growth >= 10%) for GOOD category
# ============================================================================
print("\n" + "=" * 70)
print("IMPROVEMENT 4: P(good_buy) classifier (growth >= 10%)")
print("=" * 70)

y_good = (y_growth_pct >= 10).astype(int)
oof_good = _train_classifier_oof(X_arr, y_good, groups)
auc_good = roc_auc_score(y_good[valid], oof_good[valid])
print(f"\nP(good_buy) OOF: AUC={auc_good:.3f} (n_good={y_good.sum()}/{len(y_good)}, {y_good.mean()*100:.1f}%)")

# Sweep good_buy threshold
print(f"\n  {'Threshold':>10s} {'n_good':>7s} {'Precision(>=10%)':>17s} {'Avg Return':>11s} {'F1':>6s}")
print("  " + "-" * 55)

best_good_thresh = 0.5
best_f1_good = 0.0

for thresh_int in range(25, 76, 5):
    thresh = thresh_int / 100.0
    # GOOD = P(good_buy) >= thresh AND not WORST AND not GREAT
    good_mask = (
        (oof_good[valid] >= thresh)
        & (oof_avoid[valid] < best_avoid_thresh)
        & (oof_great[valid] < best_great_thresh)
    )
    n_good_cat = good_mask.sum()
    if n_good_cat < 5:
        continue
    prec_10 = (actual_growth[valid][good_mask] >= 10).mean() * 100
    avg_ret = actual_growth[valid][good_mask].mean()
    y_pred_good = (oof_good[valid] >= thresh).astype(int)
    f1 = f1_score(y_good[valid], y_pred_good, zero_division=0)
    print(f"  {thresh:10.2f} {n_good_cat:7d} {prec_10:16.1f}% {avg_ret:+10.1f}% {f1:5.3f}")
    if f1 > best_f1_good:
        best_f1_good = f1
        best_good_thresh = thresh

print(f"\n  Best good_buy threshold (max F1): {best_good_thresh:.2f} (F1={best_f1_good:.3f})")

# Evaluate with P(good_buy) classifier
with_good_clf = _eval_buy_decision(
    oof_growth[valid], actual_growth[valid],
    oof_avoid[valid], oof_great[valid],
    good_buy_proba=oof_good[valid],
    avoid_threshold=best_avoid_thresh,
    great_threshold=best_great_thresh,
    good_threshold=best_good_thresh,
    good_regressor_hurdle=999,  # disable regressor fallback
    label=f"With P(good_buy) classifier (thresh={best_good_thresh:.2f})",
)
_print_buy_eval(with_good_clf)

# Compare to regressor fallback
delta_buy_return_4 = with_good_clf["buy_avg_return"] - tuned_thresh["buy_avg_return"]
delta_buy_precision_4 = with_good_clf["buy_precision_20"] - tuned_thresh["buy_precision_20"]
print(f"\n  DELTA vs tuned baseline: buy_avg_return={delta_buy_return_4:+.1f}%, "
      f"buy_precision_20={delta_buy_precision_4:+.1f}pp")


# ============================================================================
# IMPROVEMENT 5: Asymmetric loss for regressor
# ============================================================================
print("\n" + "=" * 70)
print("IMPROVEMENT 5: Asymmetric loss (penalize under-prediction of winners)")
print("=" * 70)

# Custom asymmetric Huber loss: weight under-prediction 2x more than over-prediction
def asymmetric_huber(y_pred, dtrain):
    """Asymmetric Huber: penalize under-prediction 2x more for positive targets."""
    y_true = dtrain.get_label()
    residual = y_true - y_pred
    delta = 1.0
    alpha = 2.0  # under-prediction weight

    grad = np.where(
        np.abs(residual) <= delta,
        -residual * np.where(residual > 0, alpha, 1.0),  # under-prediction (positive residual) gets alpha weight
        -delta * np.sign(residual) * np.where(residual > 0, alpha, 1.0),
    )
    hess = np.where(
        np.abs(residual) <= delta,
        np.ones_like(residual) * np.where(residual > 0, alpha, 1.0),
        np.zeros_like(residual) + 0.01,  # small hessian for stability
    )
    return grad, hess


# Test different asymmetry ratios
print("\nAsymmetric loss with different under-prediction weights:")
print(f"  {'Alpha':>7s} {'OOF R2':>8s} {'Spearman':>9s} {'Bias(20%+)':>11s} {'MAE(20%+)':>10s} {'Avg Pred(20%+)':>15s}")
print("  " + "-" * 65)

for alpha_val in [1.0, 1.5, 2.0, 3.0, 5.0]:
    def _make_loss(alpha_v=alpha_val):
        def _loss(y_pred, dtrain):
            y_true = dtrain.get_label()
            residual = y_true - y_pred
            delta = 1.0
            grad = np.where(
                np.abs(residual) <= delta,
                -residual * np.where(residual > 0, alpha_v, 1.0),
                -delta * np.sign(residual) * np.where(residual > 0, alpha_v, 1.0),
            )
            hess = np.where(
                np.abs(residual) <= delta,
                np.ones_like(residual) * np.where(residual > 0, alpha_v, 1.0),
                np.zeros_like(residual) + 0.01,
            )
            return grad, hess
        return _loss

    asym_params = dict(LGB_PARAMS)
    asym_params.pop("objective")
    asym_params["metric"] = "mae"

    oof_asym = _regressor_oof(
        X_arr, y_clip, groups, sample_weight,
        params=asym_params,
        custom_obj=_make_loss(alpha_val),
    )
    oof_asym_growth = (oof_asym - 1.0) * 100
    v = ~np.isnan(oof_asym)

    r2_a = r2_score(y_clip[v], oof_asym[v])
    sp_a, _ = spearmanr(y_clip[v], oof_asym[v])

    winner_mask = actual_growth[v] >= 20
    if winner_mask.sum() > 5:
        bias_winners = (oof_asym_growth[v][winner_mask] - actual_growth[v][winner_mask]).mean()
        mae_winners = np.abs(oof_asym_growth[v][winner_mask] - actual_growth[v][winner_mask]).mean()
        avg_pred_winners = oof_asym_growth[v][winner_mask].mean()
    else:
        bias_winners = 0
        mae_winners = 0
        avg_pred_winners = 0

    label_a = "baseline" if alpha_val == 1.0 else f"  alpha={alpha_val}"
    print(f"  {alpha_val:7.1f} {r2_a:8.3f} {sp_a:8.3f} {bias_winners:+10.1f}% {mae_winners:9.1f}% {avg_pred_winners:14.1f}%")

# Use best asymmetric loss for combined eval
best_alpha = 2.0  # reasonable default, will be validated
asym_params_best = dict(LGB_PARAMS)
asym_params_best.pop("objective")
asym_params_best["metric"] = "mae"
oof_asym_best = _regressor_oof(
    X_arr, y_clip, groups, sample_weight,
    params=asym_params_best, custom_obj=_make_loss(best_alpha),
)
oof_asym_best_growth = (oof_asym_best - 1.0) * 100
v5 = ~np.isnan(oof_asym_best)

# Evaluate buy decisions with asymmetric regressor
asym_eval = _eval_buy_decision(
    oof_asym_best_growth[v5], actual_growth[v5],
    oof_avoid[v5], oof_great[v5],
    avoid_threshold=best_avoid_thresh,
    great_threshold=best_great_thresh,
    label=f"Asymmetric loss (alpha={best_alpha})",
)
_print_buy_eval(asym_eval)

delta_buy_return_5 = asym_eval["buy_avg_return"] - tuned_thresh["buy_avg_return"]
print(f"\n  DELTA vs tuned baseline: buy_avg_return={delta_buy_return_5:+.1f}%")


# ============================================================================
# IMPROVEMENT 6: Ensemble P(great_buy) * regressor
# ============================================================================
print("\n" + "=" * 70)
print("IMPROVEMENT 6: Ensemble P(great_buy) * regressor as combined signal")
print("=" * 70)

# Several ensemble strategies
print("\nEnsemble strategies for ranking:")
print(f"  {'Strategy':>30s} {'Spearman':>9s} {'Top20% Avg':>11s} {'Top20% Hit(>0%)':>16s} {'Top20% Hit(>=20%)':>18s}")
print("  " + "-" * 90)

n_valid = valid.sum()
top20_n = max(1, int(n_valid * 0.2))

strategies = {
    "Regressor only": oof_growth[valid],
    "P(great_buy) only": oof_great[valid] * 100,  # scale for ranking
    "Reg * P(great)": oof_growth[valid] * oof_great[valid],
    "0.5*Reg + 0.5*P(great)*50": 0.5 * oof_growth[valid] + 0.5 * oof_great[valid] * 50,
    "Reg + 10*(P(great)-0.5)": oof_growth[valid] + 10 * (oof_great[valid] - 0.5),
    "Reg * (1 - P(avoid))": oof_growth[valid] * (1 - oof_avoid[valid]),
    "P(great)*(1-P(avoid))*Reg": oof_growth[valid] * oof_great[valid] * (1 - oof_avoid[valid]),
}

for name, scores in strategies.items():
    sp_s, _ = spearmanr(actual_growth[valid], scores)
    top20_idx = np.argsort(scores)[-top20_n:]
    top20_actual = actual_growth[valid][top20_idx]
    top20_avg = top20_actual.mean()
    top20_hit = (top20_actual > 0).mean() * 100
    top20_hit_20 = (top20_actual >= 20).mean() * 100
    print(f"  {name:>30s} {sp_s:8.3f} {top20_avg:+10.1f}% {top20_hit:15.1f}% {top20_hit_20:17.1f}%")


# ============================================================================
# SUMMARY TABLE
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY: All improvements comparison")
print("=" * 70)

# Collect all evaluations
all_evals = [baseline, tuned_thresh]

# With good_buy classifier
all_evals.append(with_good_clf)

# Asymmetric
all_evals.append(asym_eval)

# Combined: tuned thresholds + P(good_buy)
combined = _eval_buy_decision(
    oof_growth[valid], actual_growth[valid],
    oof_avoid[valid], oof_great[valid],
    good_buy_proba=oof_good[valid],
    avoid_threshold=best_avoid_thresh,
    great_threshold=best_great_thresh,
    good_threshold=best_good_thresh,
    label="Combined: tuned thresholds + P(good_buy)",
)
all_evals.append(combined)

print(f"\n{'Config':>55s} {'Buy n':>6s} {'Avg Ret':>8s} {'Hit(>0%)':>9s} {'Prec(20%)':>10s} {'WORST n':>8s} {'WORST Rec':>10s}")
print("-" * 110)

for ev in all_evals:
    print(f"  {ev['label']:>53s} {ev['buy_n']:6d} {ev['buy_avg_return']:+7.1f}% "
          f"{ev['buy_hit_rate']:8.1f}% {ev['buy_precision_20']:9.1f}% "
          f"{ev['WORST_n']:8d} {ev['worst_recall']:9.1f}%")

# Per-category breakdown for best config
print(f"\n--- Best config category breakdown ---")
best_ev = all_evals[-1]  # combined
_print_buy_eval(best_ev)

print(f"\n--- Baseline metrics for reference ---")
print(f"  Regressor OOF: R2={r2:.3f}, Spearman={sp:.3f}")
print(f"  P(avoid) AUC: {auc_avoid:.3f}")
print(f"  P(great_buy) AUC: {auc_great:.3f}")
print(f"  P(good_buy) AUC: {auc_good:.3f}")
print(f"  Best avoid threshold: {best_avoid_thresh:.2f}")
print(f"  Best great_buy threshold: {best_great_thresh:.2f}")
print(f"  Best good_buy threshold: {best_good_thresh:.2f}")

print(f"\nTotal time: {time.time() - t0:.1f}s")
