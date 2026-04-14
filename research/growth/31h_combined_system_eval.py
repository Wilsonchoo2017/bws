"""Experiment 31h: Combined system evaluation.

Evaluates the FULL prediction pipeline on BL ground truth (1319 sets):
  - Inversion classifier (avoid): BE-trained vs BL-trained vs BL+weights
  - Growth model (regressor + P(great_buy)): Keepa+BL pipeline
  - Combined buy decisions: 4-tier categories

Answers: does the improved inversion classifier help or hurt the overall
system when paired with the growth prediction model?

Run: python -m research.growth.31h_combined_system_eval
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
from sklearn.preprocessing import PowerTransformer, StandardScaler

print("=" * 70)
print("EXP 31h: COMBINED SYSTEM EVALUATION")
print("  Inversion classifier + growth model on BL ground truth")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.growth.classifier import (
    _build_classifier,
    compute_avoid_sample_weights,
    make_avoid_labels,
)
from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
from services.ml.growth.keepa_features import KEEPA_BL_FEATURES, engineer_keepa_bl_features
from services.ml.growth.model_selection import clip_outliers, compute_recency_weights
from services.ml.pg_queries import (
    load_bl_ground_truth,
    load_growth_training_data,
    load_keepa_bl_training_data,
)

engine = get_engine()

import lightgbm as lgb

# ============================================================================
# LOAD DATA
# ============================================================================
print("\n--- Loading data ---")

# BL ground truth
bl_target = load_bl_ground_truth(engine)
print(f"BL ground truth: {len(bl_target)} sets")

# Legacy BE data (for inversion classifier)
df_raw = load_growth_training_data(engine)
y_be_all = df_raw["annual_growth_pct"].values.astype(float)
print(f"BE dataset: {len(df_raw)} sets")

# Keepa+BL data (for growth model)
base_df, keepa_df, target_series = load_keepa_bl_training_data(engine)
print(f"Keepa+BL: {len(base_df)} base, {len(keepa_df)} keepa, {len(target_series)} targets")

# ============================================================================
# PREPARE: Inversion classifier features (legacy T1)
# ============================================================================
print("\n--- Preparing inversion classifier features ---")

df_feat_inv, theme_stats, subtheme_stats = engineer_intrinsic_features(
    df_raw, training_target=pd.Series(y_be_all),
)
inv_features = [f for f in TIER1_FEATURES if f in df_feat_inv.columns]
X_inv_raw = df_feat_inv[inv_features].copy()
for c in X_inv_raw.columns:
    X_inv_raw[c] = pd.to_numeric(X_inv_raw[c], errors="coerce")
X_inv = clip_outliers(X_inv_raw.fillna(X_inv_raw.median()))

# Find sets that have BOTH inversion features AND BL ground truth
inv_set_numbers = df_feat_inv["set_number"].values if "set_number" in df_feat_inv.columns else df_raw["set_number"].values
inv_bl_mask = np.array([str(sn) in bl_target for sn in inv_set_numbers])
inv_sn_bl = np.array([str(sn) for sn in inv_set_numbers[inv_bl_mask]])
y_bl_inv = np.array([bl_target[sn] for sn in inv_sn_bl])
X_inv_bl = X_inv.values[inv_bl_mask]
y_be_bl = y_be_all[inv_bl_mask]

print(f"Inversion sets with BL truth: {len(y_bl_inv)}")

# ============================================================================
# PREPARE: Growth model features (Keepa+BL)
# ============================================================================
print("\n--- Preparing growth model features ---")

df_feat_growth = engineer_keepa_bl_features(base_df, keepa_df)
target_map = dict(zip(target_series.index, target_series.values))
df_feat_growth["target"] = df_feat_growth["set_number"].map(target_map)
df_feat_growth = df_feat_growth[df_feat_growth["target"].notna()].copy()

# Add year_retired
yr_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
for _, row in base_df.iterrows():
    sn = str(row["set_number"])
    if sn not in yr_map or pd.isna(yr_map.get(sn)):
        rd = pd.to_datetime(str(row.get("retired_date", "")), errors="coerce")
        if rd is not pd.NaT:
            yr_map[sn] = rd.year
df_feat_growth["year_retired"] = df_feat_growth["set_number"].map(yr_map).fillna(2023).astype(int)

# BL ground truth for growth sets
growth_sn = df_feat_growth["set_number"].values.astype(str)
growth_bl_mask = np.array([sn in bl_target for sn in growth_sn])
growth_sn_bl = growth_sn[growth_bl_mask]
y_bl_growth = np.array([bl_target[sn] for sn in growth_sn_bl])

growth_features = [f for f in KEEPA_BL_FEATURES if f in df_feat_growth.columns]
X_growth_all = df_feat_growth[growth_features].fillna(0).copy()
fill_vals = X_growth_all.median()
X_growth_all = X_growth_all.fillna(fill_vals)
X_growth_bl = clip_outliers(X_growth_all).values[growth_bl_mask].astype(float)

y_ratio_bl = df_feat_growth["target"].values[growth_bl_mask]
groups_bl = df_feat_growth["year_retired"].values[growth_bl_mask]

# Find common sets (have both inversion AND growth features AND BL truth)
common_sn = set(inv_sn_bl) & set(growth_sn_bl)
print(f"Growth sets with BL truth: {len(y_bl_growth)}")
print(f"Common sets (both pipelines + BL): {len(common_sn)}")

# ============================================================================
# PHASE 1: Inversion classifier variants (OOF on BL truth sets)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 1: Inversion classifier variants (evaluated on BL ground truth)")
print("=" * 70)

AVOID_THRESHOLD_INV = 8.0  # production threshold for inversion

y_avoid_be = make_avoid_labels(y_be_bl, AVOID_THRESHOLD_INV)
y_avoid_bl = make_avoid_labels(y_bl_inv, AVOID_THRESHOLD_INV)

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

# A. BE target
from sklearn.model_selection import cross_val_predict

probs_be = cross_val_predict(
    _build_classifier(), StandardScaler().fit_transform(X_inv_bl),
    y_avoid_be, cv=cv, method="predict_proba",
)[:, 1]

# B. BL target
probs_bl_no_w = cross_val_predict(
    _build_classifier(), StandardScaler().fit_transform(X_inv_bl),
    y_avoid_bl, cv=cv, method="predict_proba",
)[:, 1]

# C. BL + asymmetric weights
from services.ml.growth.classifier import _get_oof_probabilities

avoid_weights = compute_avoid_sample_weights(y_bl_inv)
probs_bl_w = _get_oof_probabilities(
    StandardScaler().fit_transform(X_inv_bl),
    y_avoid_bl,
    sample_weight=avoid_weights,
)

print(f"\nInversion classifier performance (against BL truth, threshold=0.30):")
print(f"  {'Variant':<25s} {'AUC':>7s} {'Recall':>8s} {'Prec':>7s} {'F2':>7s} {'FN':>5s}")
print("  " + "-" * 60)

inv_variants = {}
for label, probs in [("BE target", probs_be), ("BL target", probs_bl_no_w), ("BL + weights", probs_bl_w)]:
    preds = (probs >= 0.30).astype(int)
    auc = roc_auc_score(y_avoid_bl, probs)
    rec = recall_score(y_avoid_bl, preds, zero_division=0)
    prec = precision_score(y_avoid_bl, preds, zero_division=0)
    f2 = fbeta_score(y_avoid_bl, preds, beta=2, zero_division=0)
    fn = ((y_avoid_bl == 1) & (preds == 0)).sum()
    print(f"  {label:<25s} {auc:>6.4f} {rec:>7.1%} {prec:>6.1%} {f2:>6.3f} {fn:>5d}")
    inv_variants[label] = probs

# ============================================================================
# PHASE 2: Growth model OOF on BL truth sets
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 2: Growth model (regressor + P(great_buy)) on BL truth sets")
print("=" * 70)

LGB_PARAMS = {
    "objective": "huber", "metric": "mae",
    "learning_rate": 0.068, "num_leaves": 20, "max_depth": 8,
    "min_child_samples": 19, "subsample": 0.60,
    "colsample_bytree": 0.88, "reg_alpha": 0.35,
    "reg_lambda": 0.009, "verbosity": -1,
}

# Regressor OOF (GroupKFold by year_retired)
tt = PowerTransformer(method="yeo-johnson")
lo, hi = np.percentile(y_ratio_bl, [2, 98])
y_clip = np.clip(y_ratio_bl, lo, hi)
y_t = tt.fit_transform(y_clip.reshape(-1, 1)).ravel()
sw = compute_recency_weights(groups_bl.astype(float))

n_splits = min(5, len(np.unique(groups_bl)))
gkf = GroupKFold(n_splits=n_splits)

oof_ratio = np.full(len(y_clip), np.nan)
for tr, va in gkf.split(X_growth_bl, y_t, groups_bl):
    dtrain = lgb.Dataset(X_growth_bl[tr], label=y_t[tr], feature_name=growth_features, weight=sw[tr])
    dval = lgb.Dataset(X_growth_bl[va], label=y_t[va], feature_name=growth_features, reference=dtrain)
    model = lgb.train(
        LGB_PARAMS, dtrain, num_boost_round=500,
        valid_sets=[dval], callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    pred_t = model.predict(X_growth_bl[va])
    oof_ratio[va] = tt.inverse_transform(pred_t.reshape(-1, 1)).ravel()

oof_growth_pct = (oof_ratio - 1.0) * 100
valid = ~np.isnan(oof_ratio)

r2_reg = r2_score(y_clip[valid], oof_ratio[valid])
sp_reg, _ = spearmanr(y_bl_growth[valid], oof_growth_pct[valid])
print(f"\nRegressor on BL truth sets: R2={r2_reg:.3f}, Spearman={sp_reg:.3f}")

# P(great_buy) OOF
y_great_bl = (y_bl_growth >= 20).astype(int)

oof_great = np.full(len(y_bl_growth), np.nan)
for tr, va in gkf.split(X_growth_bl, y_great_bl, groups_bl):
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_growth_bl[tr])
    X_va = scaler.transform(X_growth_bl[va])
    clf = lgb.LGBMClassifier(
        n_estimators=200, objective="binary", is_unbalance=True,
        max_depth=4, num_leaves=15, learning_rate=0.05,
        verbosity=-1, random_state=42, n_jobs=1,
    )
    clf.fit(X_tr, y_great_bl[tr])
    oof_great[va] = clf.predict_proba(X_va)[:, 1]

auc_great = roc_auc_score(y_great_bl[valid], oof_great[valid])
print(f"P(great_buy) on BL truth: AUC={auc_great:.3f} (n_great={y_great_bl.sum()}/{len(y_great_bl)})")

# ============================================================================
# PHASE 3: Combined system evaluation on COMMON sets
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 3: Combined system -- inversion + growth model")
print("=" * 70)

# Align data: for each common set, get inversion probs and growth predictions
# Build index mappings
inv_sn_to_idx = {sn: i for i, sn in enumerate(inv_sn_bl)}
growth_sn_to_idx = {sn: i for i, sn in enumerate(growth_sn_bl)}

common_list = sorted(common_sn)
n_common = len(common_list)
print(f"\nCommon sets: {n_common}")

# Extract aligned arrays
common_bl_growth = np.array([bl_target[sn] for sn in common_list])  # BL annualized return
common_inv_idx = np.array([inv_sn_to_idx[sn] for sn in common_list])
common_growth_idx = np.array([growth_sn_to_idx[sn] for sn in common_list])

# Growth model signals
common_oof_growth_pct = oof_growth_pct[common_growth_idx]
common_oof_great = oof_great[common_growth_idx]
common_valid = valid[common_growth_idx]

# Filter to valid predictions
v = common_valid
n_valid = v.sum()
print(f"Valid predictions: {n_valid}")

c_bl = common_bl_growth[v]
c_growth = common_oof_growth_pct[v]
c_great = common_oof_great[v]

# Evaluate buy decisions with different inversion classifier variants
print(f"\n{'System Config':<55s} {'Buy n':>6s} {'Avg Ret':>8s} {'Hit>0%':>7s} {'P>=20%':>7s} {'WORST n':>8s} {'W Rec':>6s} {'Skip Ret':>9s}")
print("-" * 115)


def _eval_combined(
    bl_growth: np.ndarray,
    growth_pct: np.ndarray,
    great_proba: np.ndarray,
    avoid_proba: np.ndarray,
    avoid_thresh: float,
    great_thresh: float,
    good_hurdle: float,
    label: str,
) -> dict:
    n = len(bl_growth)
    cats = np.full(n, "SKIP", dtype=object)
    cats[avoid_proba >= avoid_thresh] = "WORST"
    great_mask = (great_proba >= great_thresh) & (cats != "WORST")
    cats[great_mask] = "GREAT"
    good_mask = (cats == "SKIP") & (growth_pct >= good_hurdle)
    cats[good_mask] = "GOOD"

    buy = (cats == "GREAT") | (cats == "GOOD")
    worst = cats == "WORST"
    skip = cats == "SKIP"

    # BL ground truth evaluation
    buy_n = buy.sum()
    buy_ret = bl_growth[buy].mean() if buy_n > 0 else 0
    buy_hit = (bl_growth[buy] > 0).mean() * 100 if buy_n > 0 else 0
    buy_p20 = (bl_growth[buy] >= 20).mean() * 100 if buy_n > 0 else 0

    worst_n = worst.sum()
    actual_losers = (bl_growth < 0).sum()
    worst_rec = (bl_growth[worst] < 0).sum() / actual_losers * 100 if actual_losers > 0 else 0

    skip_n = skip.sum()
    skip_ret = bl_growth[skip].mean() if skip_n > 0 else 0

    print(f"  {label:<53s} {buy_n:6d} {buy_ret:+7.1f}% {buy_hit:6.1f}% {buy_p20:6.1f}% {worst_n:8d} {worst_rec:5.1f}% {skip_ret:+8.1f}%")

    return {
        "label": label, "buy_n": buy_n, "buy_ret": buy_ret,
        "buy_hit": buy_hit, "buy_p20": buy_p20,
        "worst_n": worst_n, "worst_rec": worst_rec,
        "skip_ret": skip_ret, "categories": cats,
    }


# Try all inversion variants x threshold combos
results_all = []

for inv_label, inv_key in [("BE target", "BE target"), ("BL target", "BL target"), ("BL + weights", "BL + weights")]:
    inv_probs_full = inv_variants[inv_key]
    inv_probs = inv_probs_full[common_inv_idx][v]

    for avoid_t in [0.20, 0.30, 0.50]:
        for great_t in [0.20, 0.50]:
            label = f"{inv_label} | avoid>={avoid_t:.2f}, great>={great_t:.2f}"
            r = _eval_combined(
                c_bl, c_growth, c_great, inv_probs,
                avoid_thresh=avoid_t, great_thresh=great_t, good_hurdle=10.0,
                label=label,
            )
            results_all.append(r)

# ============================================================================
# PHASE 4: Money-weighted analysis -- where does each dollar go?
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 4: Portfolio return simulation (equal-weight)")
print("=" * 70)

print(f"\n  If you buy every set the model recommends (equal weight),")
print(f"  what is your portfolio annualized return?")
print(f"\n  {'Config':<55s} {'n Buy':>6s} {'Port Return':>12s} {'vs All Sets':>12s}")
print("  " + "-" * 90)

all_sets_return = c_bl.mean()
print(f"  {'(Baseline: buy ALL sets)':<55s} {len(c_bl):6d} {all_sets_return:+11.1f}% {'--':>12s}")

# Best from each inversion variant
for inv_label, inv_key in [("BE target", "BE target"), ("BL target", "BL target"), ("BL + weights", "BL + weights")]:
    inv_probs = inv_variants[inv_key][common_inv_idx][v]

    # Best thresholds from 31g: avoid=0.20, great=0.20
    avoid_t, great_t = 0.20, 0.20
    cats = np.full(n_valid, "SKIP", dtype=object)
    cats[inv_probs >= avoid_t] = "WORST"
    great_mask = (c_great >= great_t) & (cats != "WORST")
    cats[great_mask] = "GREAT"
    good_mask = (cats == "SKIP") & (c_growth >= 10.0)
    cats[good_mask] = "GOOD"

    buy = (cats == "GREAT") | (cats == "GOOD")
    if buy.sum() > 0:
        port_ret = c_bl[buy].mean()
        delta = port_ret - all_sets_return
        label = f"{inv_label} | avoid>={avoid_t}, great>={great_t}"
        print(f"  {label:<55s} {buy.sum():6d} {port_ret:+11.1f}% {delta:+11.1f}%")

# ============================================================================
# PHASE 5: Category breakdown by BL outcome
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 5: Category breakdown -- what happens to each tier?")
print("=" * 70)

# Use the best config: BL + weights, avoid=0.20, great=0.20
best_inv = inv_variants["BL + weights"][common_inv_idx][v]
cats = np.full(n_valid, "SKIP", dtype=object)
cats[best_inv >= 0.20] = "WORST"
great_mask = (c_great >= 0.20) & (cats != "WORST")
cats[great_mask] = "GREAT"
good_mask = (cats == "SKIP") & (c_growth >= 10.0)
cats[good_mask] = "GOOD"

print(f"\n  Best config: BL+weights inversion, avoid>=0.20, great>=0.20")
print(f"\n  {'Category':<8s} {'n':>5s} {'Avg BL Ret':>11s} {'Hit>0%':>7s} {'Hit>=20%':>9s} {'Median':>8s} {'Worst':>8s} {'Best':>8s}")
print("  " + "-" * 70)

for cat in ["GREAT", "GOOD", "SKIP", "WORST"]:
    mask = cats == cat
    n = mask.sum()
    if n == 0:
        print(f"  {cat:<8s} {0:5d}")
        continue
    bl = c_bl[mask]
    print(f"  {cat:<8s} {n:5d} {bl.mean():+10.1f}% {(bl>0).mean()*100:6.1f}% {(bl>=20).mean()*100:8.1f}% "
          f"{np.median(bl):+7.1f}% {bl.min():+7.1f}% {bl.max():+7.1f}%")

# ============================================================================
# PHASE 6: Head-to-head -- old system vs new system
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 6: Head-to-head -- OLD vs NEW system")
print("=" * 70)

# OLD system: BE-trained avoid classifier, no P(great_buy), regressor-only buy signal
old_inv = inv_variants["BE target"][common_inv_idx][v]

print(f"\n  OLD: BE avoid (>=0.50) + regressor (>=8%) buy signal")
print(f"  NEW: BL+weights avoid (>=0.20) + P(great_buy)(>=0.20) + regressor (>=10%)")

# Old system
old_worst = old_inv >= 0.50
old_buy = (~old_worst) & (c_growth >= 8.0)

# New system
new_worst = best_inv >= 0.20
new_great = (c_great >= 0.20) & (~new_worst)
new_good = (~new_worst) & (~new_great) & (c_growth >= 10.0)
new_buy = new_great | new_good

print(f"\n  {'Metric':<35s} {'OLD':>12s} {'NEW':>12s} {'Delta':>10s}")
print("  " + "-" * 72)

old_buy_n = old_buy.sum()
new_buy_n = new_buy.sum()
old_buy_ret = c_bl[old_buy].mean() if old_buy_n > 0 else 0
new_buy_ret = c_bl[new_buy].mean() if new_buy_n > 0 else 0
old_buy_hit = (c_bl[old_buy] > 0).mean() * 100 if old_buy_n > 0 else 0
new_buy_hit = (c_bl[new_buy] > 0).mean() * 100 if new_buy_n > 0 else 0
old_buy_p20 = (c_bl[old_buy] >= 20).mean() * 100 if old_buy_n > 0 else 0
new_buy_p20 = (c_bl[new_buy] >= 20).mean() * 100 if new_buy_n > 0 else 0

old_worst_n = old_worst.sum()
new_worst_n = new_worst.sum()
actual_losers = (c_bl < 0).sum()
old_worst_rec = (c_bl[old_worst] < 0).sum() / actual_losers * 100 if actual_losers > 0 else 0
new_worst_rec = (c_bl[new_worst] < 0).sum() / actual_losers * 100 if actual_losers > 0 else 0

metrics = [
    ("Buy signals", f"{old_buy_n}", f"{new_buy_n}", f"{new_buy_n - old_buy_n:+d}"),
    ("Buy avg BL return", f"{old_buy_ret:+.1f}%", f"{new_buy_ret:+.1f}%", f"{new_buy_ret-old_buy_ret:+.1f}%"),
    ("Buy hit rate (>0%)", f"{old_buy_hit:.1f}%", f"{new_buy_hit:.1f}%", f"{new_buy_hit-old_buy_hit:+.1f}pp"),
    ("Buy precision (>=20%)", f"{old_buy_p20:.1f}%", f"{new_buy_p20:.1f}%", f"{new_buy_p20-old_buy_p20:+.1f}pp"),
    ("WORST signals", f"{old_worst_n}", f"{new_worst_n}", f"{new_worst_n-old_worst_n:+d}"),
    ("WORST recall (catches losers)", f"{old_worst_rec:.1f}%", f"{new_worst_rec:.1f}%", f"{new_worst_rec-old_worst_rec:+.1f}pp"),
]

for name, old_v, new_v, delta in metrics:
    print(f"  {name:<35s} {old_v:>12s} {new_v:>12s} {delta:>10s}")

# Missed losers analysis
print(f"\n  Losers missed by each system (bought but BL return < 0%):")
old_fn_losers = c_bl[old_buy & (c_bl < 0)]
new_fn_losers = c_bl[new_buy & (c_bl < 0)]
print(f"    OLD: {len(old_fn_losers)} losers bought, avg loss={old_fn_losers.mean():+.1f}%" if len(old_fn_losers) > 0 else "    OLD: 0 losers bought")
print(f"    NEW: {len(new_fn_losers)} losers bought, avg loss={new_fn_losers.mean():+.1f}%" if len(new_fn_losers) > 0 else "    NEW: 0 losers bought")

# ============================================================================
# PHASE 7: Confusion matrix -- agreement between old and new
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 7: System agreement -- where do OLD and NEW disagree?")
print("=" * 70)

agree_buy = old_buy & new_buy
agree_skip = (~old_buy) & (~new_buy)
old_only = old_buy & (~new_buy)  # old buys, new doesn't
new_only = (~old_buy) & new_buy  # new buys, old doesn't

print(f"\n  {'Agreement':<30s} {'n':>5s} {'Avg BL Return':>14s} {'Hit>0%':>7s}")
print("  " + "-" * 60)
for label, mask in [
    ("Both buy", agree_buy),
    ("Both skip", agree_skip),
    ("OLD buys, NEW skips", old_only),
    ("NEW buys, OLD skips", new_only),
]:
    n = mask.sum()
    if n == 0:
        print(f"  {label:<30s} {0:5d}")
        continue
    bl = c_bl[mask]
    print(f"  {label:<30s} {n:5d} {bl.mean():+13.1f}% {(bl>0).mean()*100:6.1f}%")

print(f"\n  Key question: sets OLD bought but NEW skips -- are they actual losers?")
if old_only.sum() > 0:
    losers_in_old_only = (c_bl[old_only] < 0).sum()
    print(f"    {old_only.sum()} sets: {losers_in_old_only} are actual BL losers ({losers_in_old_only/old_only.sum()*100:.0f}%)")
    print(f"    avg return: {c_bl[old_only].mean():+.1f}%, median: {np.median(c_bl[old_only]):+.1f}%")
if new_only.sum() > 0:
    losers_in_new_only = (c_bl[new_only] < 0).sum()
    print(f"\n  Sets NEW bought but OLD skips:")
    print(f"    {new_only.sum()} sets: {losers_in_new_only} are actual BL losers ({losers_in_new_only/new_only.sum()*100:.0f}%)")
    print(f"    avg return: {c_bl[new_only].mean():+.1f}%, median: {np.median(c_bl[new_only]):+.1f}%")

print(f"\nTotal time: {time.time() - t0:.1f}s")
