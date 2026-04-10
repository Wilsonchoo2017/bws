"""Experiment 31d: Calibration evaluation + classifier assessment.

Questions answered:
1. If model predicts >10% growth, how often is it right?
2. If model predicts >20% growth, how often is it right?
3. How well calibrated is P(avoid)?
4. Does the new classifier (BL target) outperform the old one (BE target)?

Run: python -m research.growth.31d_calibration_eval
"""
from __future__ import annotations

import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score, roc_auc_score, precision_recall_curve
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer

print("=" * 70)
print("EXP 31d: CALIBRATION + CLASSIFIER ASSESSMENT")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.pg_queries import load_keepa_bl_training_data
from services.ml.growth.keepa_features import KEEPA_BL_FEATURES, engineer_keepa_bl_features
from services.ml.growth.model_selection import clip_outliers, compute_recency_weights

engine = get_engine()

# Load data
print("\n--- Loading data ---")
base_df, keepa_df, target_series = load_keepa_bl_training_data(engine)
print(f"Base: {len(base_df)}, Keepa: {len(keepa_df)}, Targets: {len(target_series)}")

# Engineer features
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

# Filter to retired <= 2024
train_mask = df_feat["year_retired"] <= 2024
df_train = df_feat[train_mask].copy()
df_holdout = df_feat[~train_mask].copy()

y = df_train["target"].values.astype(float)
groups = df_train["year_retired"].values
feature_names = [f for f in KEEPA_BL_FEATURES if f in df_train.columns]
X = df_train[feature_names].fillna(0).values.astype(float)

lo, hi = np.percentile(y, [2, 98])
y_clip = np.clip(y, lo, hi)

print(f"\nTraining: {len(df_train)} sets, Holdout (2025+): {len(df_holdout)} sets")
print(f"Target: BL price / RRP (mean={y.mean():.3f}, std={y.std():.3f})")

# ============================================================================
# PHASE 1: OOF PREDICTIONS
# ============================================================================
print("\n--- Phase 1: 5-fold GroupKFold OOF predictions ---")

import lightgbm as lgb

X_arr = clip_outliers(pd.DataFrame(X, columns=feature_names)).values.astype(float)
sample_weight = compute_recency_weights(groups.astype(float))

tt = PowerTransformer(method="yeo-johnson")
y_t = tt.fit_transform(y_clip.reshape(-1, 1)).ravel()

gkf = GroupKFold(n_splits=5)
oof = np.full(len(y_clip), np.nan)
oof_avoid_proba = np.full(len(y_clip), np.nan)

for fold_i, (tr, va) in enumerate(gkf.split(X_arr, y_t, groups)):
    # Regressor
    dtrain = lgb.Dataset(X_arr[tr], label=y_t[tr], feature_name=feature_names, weight=sample_weight[tr])
    dval = lgb.Dataset(X_arr[va], label=y_t[va], feature_name=feature_names, reference=dtrain)
    model = lgb.train(
        {"objective": "huber", "metric": "mae", "learning_rate": 0.068,
         "num_leaves": 20, "max_depth": 8, "min_child_samples": 19,
         "subsample": 0.60, "colsample_bytree": 0.88,
         "reg_alpha": 0.35, "reg_lambda": 0.009, "verbosity": -1},
        dtrain, num_boost_round=500, valid_sets=[dval],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    pred_t = model.predict(X_arr[va])
    oof[va] = tt.inverse_transform(pred_t.reshape(-1, 1)).ravel()

    # Classifier (P(avoid) where avoid = BL < RRP)
    y_binary_tr = (y_clip[tr] < 1.0).astype(int)
    y_binary_va = (y_clip[va] < 1.0).astype(int)

    dtrain_cls = lgb.Dataset(X_arr[tr], label=y_binary_tr, feature_name=feature_names)
    dval_cls = lgb.Dataset(X_arr[va], label=y_binary_va, feature_name=feature_names, reference=dtrain_cls)
    cls = lgb.train(
        {"objective": "binary", "metric": "auc", "learning_rate": 0.037,
         "num_leaves": 28, "max_depth": 6, "min_child_samples": 23,
         "feature_fraction": 0.755, "subsample": 0.704,
         "reg_alpha": 0.053, "reg_lambda": 0.060, "verbosity": -1},
        dtrain_cls, num_boost_round=300, valid_sets=[dval_cls],
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )
    oof_avoid_proba[va] = cls.predict(X_arr[va])

    yrs = sorted(np.unique(groups[va]).tolist())
    r2_f = r2_score(y_clip[va], oof[va])
    auc_f = roc_auc_score(y_binary_va, oof_avoid_proba[va]) if y_binary_va.sum() > 0 else 0
    print(f"  Fold {fold_i+1}: R2={r2_f:.3f}, AUC={auc_f:.3f}, years={yrs}")

valid = ~np.isnan(oof)
overall_r2 = r2_score(y_clip[valid], oof[valid])
sp, _ = spearmanr(y_clip[valid], oof[valid])
overall_auc = roc_auc_score((y_clip[valid] < 1.0).astype(int), oof_avoid_proba[valid])
print(f"\nOOF Regressor: R2={overall_r2:.3f}, Spearman={sp:.3f}")
print(f"OOF Classifier: AUC={overall_auc:.3f}")

# ============================================================================
# PHASE 2: CALIBRATION -- P(growth > X%)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 2: CALIBRATION -- If model predicts growth, how often is it right?")
print("=" * 70)

# Convert ratio predictions to growth %
oof_growth_pct = (oof[valid] - 1.0) * 100
actual_growth_pct = (y_clip[valid] - 1.0) * 100

# For various predicted thresholds, check actual outcomes
print(f"\n{'Pred Threshold':>20s} {'n_above':>8s} {'Actual>0%':>10s} {'Actual>10%':>11s} {'Actual>20%':>11s} {'Avg Actual':>11s}")
print("-" * 80)

for threshold in [0, 5, 10, 15, 20, 30]:
    mask = oof_growth_pct >= threshold
    n = mask.sum()
    if n < 5:
        continue
    actual_above = actual_growth_pct[mask]
    pct_above_0 = (actual_above > 0).mean() * 100
    pct_above_10 = (actual_above > 10).mean() * 100
    pct_above_20 = (actual_above > 20).mean() * 100
    avg_actual = actual_above.mean()
    print(f"  Predicted >= {threshold:3d}%   {n:8d} {pct_above_0:9.1f}% {pct_above_10:10.1f}% {pct_above_20:10.1f}% {avg_actual:10.1f}%")

# Reverse: for actual outcome ranges, what did model predict?
print(f"\n{'Actual Range':>20s} {'n':>5s} {'Avg Pred':>10s} {'Pred>0%':>8s} {'Pred>10%':>9s}")
print("-" * 60)

for lo_a, hi_a, label in [
    (-999, -10, "Lost >10%"),
    (-10, 0, "Lost 0-10%"),
    (0, 10, "Gained 0-10%"),
    (10, 20, "Gained 10-20%"),
    (20, 50, "Gained 20-50%"),
    (50, 999, "Gained >50%"),
]:
    mask = (actual_growth_pct >= lo_a) & (actual_growth_pct < hi_a)
    n = mask.sum()
    if n < 3:
        continue
    avg_pred = oof_growth_pct[mask].mean()
    pct_pred_pos = (oof_growth_pct[mask] > 0).mean() * 100
    pct_pred_10 = (oof_growth_pct[mask] > 10).mean() * 100
    print(f"  {label:>18s} {n:5d} {avg_pred:9.1f}% {pct_pred_pos:7.1f}% {pct_pred_10:8.1f}%")

# ============================================================================
# PHASE 3: CLASSIFIER CALIBRATION
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 3: CLASSIFIER CALIBRATION")
print("=" * 70)

y_binary = (y_clip[valid] < 1.0).astype(int)
proba = oof_avoid_proba[valid]

# Calibration by probability bucket
print(f"\n{'P(avoid) Bucket':>20s} {'n':>5s} {'Actual Avoid%':>14s} {'Avg P(avoid)':>13s}")
print("-" * 60)

for lo_p, hi_p in [(0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
                    (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]:
    mask = (proba >= lo_p) & (proba < hi_p)
    n = mask.sum()
    if n < 5:
        continue
    actual_avoid = y_binary[mask].mean() * 100
    avg_proba = proba[mask].mean() * 100
    gap = actual_avoid - avg_proba
    cal_label = "OK" if abs(gap) < 10 else ("overconfident" if gap < 0 else "underconfident")
    print(f"  P={lo_p:.1f}-{hi_p:.1f}          {n:5d} {actual_avoid:13.1f}% {avg_proba:12.1f}%  ({cal_label})")

# P(avoid) at useful decision thresholds
print(f"\n{'Threshold':>15s} {'Precision':>10s} {'Recall':>8s} {'n_flagged':>10s} {'Actual Avoid':>13s}")
print("-" * 65)

for thresh in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    flagged = proba >= thresh
    n_flagged = flagged.sum()
    if n_flagged == 0:
        continue
    precision = y_binary[flagged].mean() * 100
    recall = y_binary[flagged].sum() / y_binary.sum() * 100 if y_binary.sum() > 0 else 0
    print(f"  P >= {thresh:.1f}      {precision:9.1f}% {recall:7.1f}% {n_flagged:10d} {y_binary[flagged].sum():>5d}/{n_flagged}")

# ============================================================================
# PHASE 4: HIT RATE ANALYSIS
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 4: HIT RATE -- Buy signal accuracy")
print("=" * 70)

# Buy signal: P(avoid) < 0.5 AND predicted growth > X%
for growth_thresh in [0, 5, 10, 15]:
    buy_mask = (oof_avoid_proba[valid] < 0.5) & (oof_growth_pct >= growth_thresh)
    n_buy = buy_mask.sum()
    if n_buy < 5:
        continue
    actual_pos = (actual_growth_pct[buy_mask] > 0).mean() * 100
    actual_above_10 = (actual_growth_pct[buy_mask] > 10).mean() * 100
    avg_return = actual_growth_pct[buy_mask].mean()
    print(f"  Buy signal (P(avoid)<0.5 & pred>={growth_thresh}%): "
          f"n={n_buy}, hit(>0%)={actual_pos:.1f}%, hit(>10%)={actual_above_10:.1f}%, "
          f"avg return={avg_return:+.1f}%")

# ============================================================================
# PHASE 5: COMPARISON WITH OLD CLASSIFIER
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 5: NEW CLASSIFIER vs OLD (BE-based)")
print("=" * 70)

# Load old production predictions for comparison
with engine.connect() as conn:
    from sqlalchemy import text
    old_preds = pd.read_sql(text("""
        SELECT set_number, predicted_growth_pct, confidence
        FROM (
            SELECT set_number, predicted_growth_pct, confidence,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY snapshot_date DESC) AS rn
            FROM ml_prediction_snapshots
        ) sub WHERE rn = 1
    """), conn)

# Match with our eval set
old_map = dict(zip(old_preds["set_number"], old_preds["predicted_growth_pct"]))
old_growth = df_train.loc[valid, "set_number"].map(old_map).values

mask_both = ~np.isnan(old_growth) & valid[:len(old_growth)]
if mask_both.sum() > 50:
    # Old model: predicted growth % (BE target)
    old_pred = old_growth[mask_both]
    new_pred = oof_growth_pct[:len(mask_both)][mask_both]
    actual = actual_growth_pct[:len(mask_both)][mask_both]

    old_sp, _ = spearmanr(actual, old_pred)
    new_sp, _ = spearmanr(actual, new_pred)

    print(f"\n  Common sets: {mask_both.sum()}")
    print(f"  Old model (BE) Spearman: {old_sp:.3f}")
    print(f"  New model (Keepa+BL) Spearman: {new_sp:.3f}")
    print(f"  Delta: {new_sp - old_sp:+.3f}")

    # Hit rates comparison
    for thresh in [0, 10]:
        old_above = (old_pred > thresh)
        new_above = (new_pred > thresh)
        old_hit = (actual[old_above] > 0).mean() * 100 if old_above.sum() > 0 else 0
        new_hit = (actual[new_above] > 0).mean() * 100 if new_above.sum() > 0 else 0
        print(f"  Pred>{thresh}%: Old hit rate={old_hit:.1f}% (n={old_above.sum()}), "
              f"New hit rate={new_hit:.1f}% (n={new_above.sum()})")
else:
    print(f"  Too few common sets ({mask_both.sum()}) for comparison")

# ============================================================================
# PHASE 6: INVERSION MODEL ASSESSMENT
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 6: INVERSION MODEL -- Does the old classifier still work?")
print("=" * 70)

# The old classifier was trained on BE growth < 5%
# The new reality: avoid = BL price < RRP
# Question: does the old P(avoid) still identify BL losers?

# We don't have old P(avoid) OOF scores, but we can check:
# Does the old predicted_growth_pct identify BL losers?
old_growth_all = df_train["set_number"].map(old_map)
mask_old = old_growth_all.notna()

if mask_old.sum() > 100:
    old_g = old_growth_all[mask_old].values.astype(float)
    actual_bl = y_clip[:len(mask_old)][mask_old.values]
    bl_loser = (actual_bl < 1.0).astype(int)

    # Old model's implicit avoid: growth < 5%
    old_avoid = (old_g < 5).astype(int)
    from sklearn.metrics import precision_score, recall_score

    if bl_loser.sum() > 0 and (1 - bl_loser).sum() > 0:
        # How well does "old growth < 5%" predict "BL < RRP"?
        prec = precision_score(bl_loser, old_avoid)
        rec = recall_score(bl_loser, old_avoid)
        # AUC: use old growth as continuous score (negated for AUC)
        auc_old = roc_auc_score(bl_loser, -old_g)

        print(f"\n  Old model 'avoid' (BE growth < 5%) vs BL losers:")
        print(f"    Precision: {prec:.3f}")
        print(f"    Recall: {rec:.3f}")
        print(f"    AUC (negated growth): {auc_old:.3f}")

        # New classifier
        new_avoid_proba = oof_avoid_proba[valid][:len(mask_old)][mask_old.values]
        bl_loser_new = bl_loser
        if len(new_avoid_proba) == len(bl_loser_new):
            auc_new = roc_auc_score(bl_loser_new, new_avoid_proba)
            print(f"\n  New classifier P(avoid) vs BL losers:")
            print(f"    AUC: {auc_new:.3f}")
            print(f"    Delta: {auc_new - auc_old:+.3f}")

print(f"\nTotal time: {time.time() - t0:.1f}s")
