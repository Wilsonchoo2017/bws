"""Experiment 33: Theme-level growth trends from Keepa feature aggregates.

Replace removed BE theme growth features (theme_bayes, be_theme_avg_growth)
with theme-level aggregates computed from our own Keepa data. All Keepa
features are already cut at retired_date, so no lookahead.

New features (LOO Bayesian encoded, alpha=20):
  - theme_avg_3p_premium: mean 3p_above_rrp_pct within theme
  - theme_avg_retire_price: mean 3p_price_at_retire_vs_rrp within theme
  - theme_avg_demand: mean amz_review_count within theme
  - theme_growth_x_prem: interaction theme_avg_3p_premium * 3p_above_rrp_pct

Run: python -m research.growth.33_theme_bl_features
"""
from __future__ import annotations

import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer

print("=" * 70)
print("EXP 33: THEME-LEVEL KEEPA FEATURE AGGREGATES")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.pg_queries import load_keepa_bl_training_data, load_google_trends_data
from services.ml.growth.keepa_features import (
    KEEPA_BL_FEATURES,
    GT_FEATURES,
    engineer_keepa_bl_features,
    engineer_gt_features,
)
from services.ml.growth.model_selection import clip_outliers, compute_recency_weights
from services.ml.encodings import compute_group_stats, loo_bayesian_encode, group_mean_encode, group_size_encode

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

# Add year_retired and theme from base_df
yr_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
theme_map = dict(zip(base_df["set_number"].astype(str), base_df.get("theme")))
for _, row in base_df.iterrows():
    sn = str(row["set_number"])
    if sn not in yr_map or pd.isna(yr_map.get(sn)):
        rd = pd.to_datetime(str(row.get("retired_date", "")), errors="coerce")
        if rd is not pd.NaT:
            yr_map[sn] = rd.year
df_feat["year_retired"] = df_feat["set_number"].map(yr_map).fillna(2023).astype(int)
df_feat["theme"] = df_feat["set_number"].map(theme_map).fillna("")

# Add GT features (same as Exp 32)
gt_df = load_google_trends_data(engine)
gt_feat = engineer_gt_features(gt_df, base_df)
df_feat = df_feat.merge(gt_feat, on="set_number", how="left")
for col in GT_FEATURES:
    if col not in df_feat.columns:
        df_feat[col] = 0.0
    else:
        df_feat[col] = df_feat[col].fillna(0.0)

print(f"Sets with features + target: {len(df_feat)}")
print(f"Unique themes: {df_feat['theme'].nunique()}")

# ============================================================================
# THEME FEATURE ENGINEERING (LOO Bayesian encoding)
# ============================================================================
print("\n--- Theme Feature Engineering ---")

# Source features for theme aggregation (all already cut at retired_date)
THEME_SOURCE_FEATURES = {
    "theme_avg_3p_premium": "3p_above_rrp_pct",
    "theme_avg_retire_price": "3p_price_at_retire_vs_rrp",
    "theme_avg_demand": "amz_review_count",
}

THEME_FEATURE_NAMES = list(THEME_SOURCE_FEATURES.keys()) + ["theme_growth_x_prem"]

# Training set only
train_mask = df_feat["year_retired"] <= 2024
df_train = df_feat[train_mask].copy()

# Compute LOO-encoded theme features on training set
theme_stats_all = {}
for theme_feat, source_feat in THEME_SOURCE_FEATURES.items():
    source_vals = df_train[source_feat].fillna(0).astype(float)
    stats = compute_group_stats(df_train, "theme", source_vals)
    theme_stats_all[theme_feat] = stats

    # LOO Bayesian encode (training mode)
    df_train[theme_feat] = loo_bayesian_encode(
        df_train["theme"], source_vals, stats, alpha=20,
    )
    print(f"  {theme_feat}: global_mean={stats['global_mean']:.3f}, "
          f"n_themes={len(stats['groups'])}")

# Interaction feature
df_train["theme_growth_x_prem"] = (
    df_train["theme_avg_3p_premium"] * df_train["3p_above_rrp_pct"].fillna(0)
)

# ============================================================================
# THEME FEATURE DIAGNOSTICS
# ============================================================================
print("\n--- Theme Feature Correlations with Target ---")
y_growth_pct_all = (df_train["target"].values - 1.0) * 100

for col in THEME_FEATURE_NAMES:
    mask = df_train[col].notna() & (df_train[col] != 0)
    if mask.sum() > 30:
        sp, _ = spearmanr(df_train.loc[mask, col], y_growth_pct_all[mask])
        r = df_train.loc[mask, col].corr(pd.Series(y_growth_pct_all[mask], index=df_train.loc[mask].index))
        print(f"  {col:30s}  r={r:+.3f}  spearman={sp:+.3f}  n={mask.sum()}")
    else:
        print(f"  {col:30s}  n={mask.sum()} (too few)")

# Compare with binary theme flags
for col in ["theme_false_pos", "theme_strong"]:
    if col in df_train.columns:
        sp, _ = spearmanr(df_train[col], y_growth_pct_all)
        print(f"  {col:30s}  spearman={sp:+.3f}  (binary baseline)")

# Top/bottom themes
print("\n--- Top Themes by avg 3P premium (LOO encoded) ---")
theme_means = df_train.groupby("theme")["theme_avg_3p_premium"].mean().sort_values(ascending=False)
for theme, val in theme_means.head(10).items():
    n = (df_train["theme"] == theme).sum()
    print(f"  {theme:25s}  avg_3p_premium={val:+.2f}  n={n}")
print("  ...")
for theme, val in theme_means.tail(5).items():
    n = (df_train["theme"] == theme).sum()
    print(f"  {theme:25s}  avg_3p_premium={val:+.2f}  n={n}")

# LOO correctness check: verify same-theme sets get different values
print("\n--- LOO Correctness Check ---")
sw_sets = df_train[df_train["theme"] == "Star Wars"]
if len(sw_sets) > 2:
    vals = sw_sets["theme_avg_3p_premium"].values
    print(f"  Star Wars: {len(sw_sets)} sets, "
          f"theme_avg_3p_premium range=[{vals.min():.4f}, {vals.max():.4f}], "
          f"unique={len(np.unique(vals))}/{len(vals)}")
    if len(np.unique(vals)) > 1:
        print("  OK: LOO encoding produces different values per set")
    else:
        print("  WARNING: All values identical -- LOO may not be working")

# ============================================================================
# TRAINING SETUP
# ============================================================================
y_raw = df_train["target"].values.astype(float)
groups = df_train["year_retired"].values

lo, hi = np.percentile(y_raw, [2, 98])
y_clip = np.clip(y_raw, lo, hi)
y_growth_pct = (y_clip - 1.0) * 100

sample_weight = compute_recency_weights(groups.astype(float))

# Baseline: current 33-feature set (26 Keepa + 7 GT) -- EXCLUDE new theme features
baseline_features = [
    f for f in list(KEEPA_BL_FEATURES) + list(GT_FEATURES)
    if f in df_train.columns and f not in THEME_FEATURE_NAMES
]
# Augmented: baseline + 4 theme features
augmented_features = baseline_features + THEME_FEATURE_NAMES

print(f"\nTraining: {len(df_train)} sets")
print(f"Baseline features: {len(baseline_features)}")
print(f"Augmented features: {len(augmented_features)}")

import lightgbm as lgb

LGB_PARAMS = {
    "objective": "huber", "metric": "mae",
    "learning_rate": 0.068, "num_leaves": 20, "max_depth": 8,
    "min_child_samples": 19, "subsample": 0.60,
    "colsample_bytree": 0.88, "reg_alpha": 0.35,
    "reg_lambda": 0.009, "verbosity": -1,
}

CLF_PARAMS = {
    "objective": "binary", "metric": "auc",
    "learning_rate": 0.05, "num_leaves": 15, "max_depth": 4,
    "min_child_samples": 10, "is_unbalance": True,
    "reg_alpha": 0.1, "reg_lambda": 1.0, "verbosity": -1,
}

n_splits = min(5, len(np.unique(groups)))
gkf = GroupKFold(n_splits=n_splits)


# ============================================================================
# CV FUNCTIONS (LOO encoding must be done WITHIN each fold)
# ============================================================================
def _encode_theme_features_for_fold(
    df: pd.DataFrame,
    tr_idx: np.ndarray,
    va_idx: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute LOO theme features within CV fold to prevent leakage.

    Train fold: LOO Bayesian encode (exclude own value)
    Val fold: group_mean_encode from train fold stats (no LOO needed)
    """
    df_tr = df.iloc[tr_idx].copy()
    df_va = df.iloc[va_idx].copy()

    for theme_feat, source_feat in THEME_SOURCE_FEATURES.items():
        source_tr = df_tr[source_feat].fillna(0).astype(float)
        stats = compute_group_stats(df_tr, "theme", source_tr)

        # Train: LOO encode
        df_tr[theme_feat] = loo_bayesian_encode(
            df_tr["theme"], source_tr, stats, alpha=20,
        )
        # Val: full mean encode (from train stats only)
        df_va[theme_feat] = group_mean_encode(
            df_va["theme"], stats, alpha=20,
        )

    # Interaction
    df_tr["theme_growth_x_prem"] = (
        df_tr["theme_avg_3p_premium"] * df_tr["3p_above_rrp_pct"].fillna(0)
    )
    df_va["theme_growth_x_prem"] = (
        df_va["theme_avg_3p_premium"] * df_va["3p_above_rrp_pct"].fillna(0)
    )

    return df_tr, df_va


def run_regressor_oof(feature_names: list[str], label: str, use_theme_cv: bool = False) -> np.ndarray:
    """OOF predictions for regressor."""
    X_raw = df_train[feature_names].fillna(0).copy()
    X_arr = clip_outliers(X_raw).values.astype(float)

    tt = PowerTransformer(method="yeo-johnson")
    y_t = tt.fit_transform(y_clip.reshape(-1, 1)).ravel()

    oof = np.full(len(y_clip), np.nan)
    for tr_idx, va_idx in gkf.split(X_arr, y_t, groups):
        if use_theme_cv:
            # Re-encode theme features within fold
            df_tr, df_va = _encode_theme_features_for_fold(df_train, tr_idx, va_idx)
            X_tr = clip_outliers(df_tr[feature_names].fillna(0)).values.astype(float)
            X_va = clip_outliers(df_va[feature_names].fillna(0)).values.astype(float)
        else:
            X_tr = X_arr[tr_idx]
            X_va = X_arr[va_idx]

        w = sample_weight[tr_idx]
        dtrain = lgb.Dataset(X_tr, label=y_t[tr_idx], weight=w)
        dval = lgb.Dataset(X_va, label=y_t[va_idx], reference=dtrain)
        model = lgb.train(
            LGB_PARAMS, dtrain, num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        pred_t = model.predict(X_va)
        oof[va_idx] = tt.inverse_transform(pred_t.reshape(-1, 1)).ravel()

    oof_growth = (oof - 1.0) * 100
    actual_growth = y_growth_pct

    valid = ~np.isnan(oof_growth)
    r2 = r2_score(actual_growth[valid], oof_growth[valid])
    sp, _ = spearmanr(actual_growth[valid], oof_growth[valid])
    mae = np.mean(np.abs(actual_growth[valid] - oof_growth[valid]))
    print(f"  [{label}] Regressor: R2={r2:.4f}  Spearman={sp:.4f}  MAE={mae:.2f}%  (n={valid.sum()})")
    return oof


def run_classifier_oof(
    feature_names: list[str],
    threshold_pct: float,
    label_tag: str,
    use_theme_cv: bool = False,
    invert: bool = False,
) -> np.ndarray:
    """OOF probabilities for binary classifier."""
    X_raw = df_train[feature_names].fillna(0).copy()
    X_arr = clip_outliers(X_raw).values.astype(float)

    if invert:
        y_binary = (y_growth_pct >= threshold_pct).astype(int)
    else:
        y_binary = (y_growth_pct < threshold_pct).astype(int)

    oof_probs = np.full(len(y_binary), np.nan)
    for tr_idx, va_idx in gkf.split(X_arr, y_binary, groups):
        if use_theme_cv:
            df_tr, df_va = _encode_theme_features_for_fold(df_train, tr_idx, va_idx)
            X_tr_raw = clip_outliers(df_tr[feature_names].fillna(0)).values.astype(float)
            X_va_raw = clip_outliers(df_va[feature_names].fillna(0)).values.astype(float)
        else:
            X_tr_raw = X_arr[tr_idx]
            X_va_raw = X_arr[va_idx]

        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_tr_raw)
        X_va = scaler.transform(X_va_raw)
        clf = lgb.LGBMClassifier(n_estimators=200, **CLF_PARAMS, random_state=42, n_jobs=1)
        clf.fit(X_tr, y_binary[tr_idx])
        oof_probs[va_idx] = clf.predict_proba(X_va)[:, 1]

    valid = ~np.isnan(oof_probs)
    auc = roc_auc_score(y_binary[valid], oof_probs[valid])
    label_suffix = "inverted" if invert else "standard"
    print(f"  [{label_tag}] P(>={threshold_pct}%) AUC={auc:.4f} ({label_suffix}, n={valid.sum()})")
    return oof_probs


# ============================================================================
# HEAD-TO-HEAD: BASELINE vs THEME-AUGMENTED
# ============================================================================
print("\n" + "=" * 70)
print("REGRESSOR: BASELINE vs THEME-AUGMENTED")
print("=" * 70)
oof_base = run_regressor_oof(baseline_features, "BASELINE")
oof_theme = run_regressor_oof(augmented_features, "THEME", use_theme_cv=True)

print("\n" + "=" * 70)
print("CLASSIFIER P(great_buy >= 20%): BASELINE vs THEME-AUGMENTED")
print("=" * 70)
prob_base = run_classifier_oof(baseline_features, 20.0, "BASELINE", invert=True)
prob_theme = run_classifier_oof(augmented_features, 20.0, "THEME", use_theme_cv=True, invert=True)

print("\n" + "=" * 70)
print("CLASSIFIER P(avoid < 8%): BASELINE vs THEME-AUGMENTED")
print("=" * 70)
avoid_base = run_classifier_oof(baseline_features, 8.0, "BASELINE")
avoid_theme = run_classifier_oof(augmented_features, 8.0, "THEME", use_theme_cv=True)

# ============================================================================
# FEATURE IMPORTANCE: WHERE DO THEME FEATURES RANK?
# ============================================================================
print("\n" + "=" * 70)
print("THEME FEATURE IMPORTANCE (full model)")
print("=" * 70)

X_full = df_train[augmented_features].fillna(0).copy()
X_full = clip_outliers(X_full).values.astype(float)
tt = PowerTransformer(method="yeo-johnson")
y_t = tt.fit_transform(y_clip.reshape(-1, 1)).ravel()
dtrain = lgb.Dataset(X_full, label=y_t, weight=sample_weight)
model = lgb.train(LGB_PARAMS, dtrain, num_boost_round=300)
imp = dict(zip(augmented_features, model.feature_importance(importance_type="gain")))
sorted_imp = sorted(imp.items(), key=lambda x: x[1], reverse=True)

print(f"{'Feature':35s}  {'Gain':>10s}  {'Rank':>5s}")
print("-" * 55)
for rank, (feat, gain) in enumerate(sorted_imp, 1):
    marker = " <-- THEME" if feat in THEME_FEATURE_NAMES else ""
    print(f"{feat:35s}  {gain:10.1f}  {rank:5d}{marker}")

# ============================================================================
# ABLATION: EACH THEME FEATURE INDIVIDUALLY
# ============================================================================
print("\n" + "=" * 70)
print("ABLATION: EACH THEME FEATURE INDIVIDUALLY")
print("=" * 70)

for feat in THEME_FEATURE_NAMES:
    single_augmented = baseline_features + [feat]
    print(f"\n  + {feat}:")
    run_classifier_oof(single_augmented, 20.0, f"+{feat}", use_theme_cv=True, invert=True)
    run_classifier_oof(single_augmented, 8.0, f"+{feat}", use_theme_cv=True)

# ============================================================================
# VERDICT
# ============================================================================
print("\n" + "=" * 70)
print("VERDICT")
print("=" * 70)

oof_base_growth = (oof_base - 1.0) * 100
oof_theme_growth = (oof_theme - 1.0) * 100

v_base = ~np.isnan(oof_base_growth)
v_theme = ~np.isnan(oof_theme_growth)
r2_base = r2_score(y_growth_pct[v_base], oof_base_growth[v_base])
r2_theme = r2_score(y_growth_pct[v_theme], oof_theme_growth[v_theme])
sp_base, _ = spearmanr(y_growth_pct[v_base], oof_base_growth[v_base])
sp_theme, _ = spearmanr(y_growth_pct[v_theme], oof_theme_growth[v_theme])

print(f"Regressor R2:       BASELINE={r2_base:.4f}  THEME={r2_theme:.4f}  delta={r2_theme - r2_base:+.4f}")
print(f"Regressor Spearman: BASELINE={sp_base:.4f}  THEME={sp_theme:.4f}  delta={sp_theme - sp_base:+.4f}")

v_pb = ~np.isnan(prob_base)
v_pt = ~np.isnan(prob_theme)
y_great = (y_growth_pct >= 20).astype(int)
auc_base = roc_auc_score(y_great[v_pb], prob_base[v_pb])
auc_theme = roc_auc_score(y_great[v_pt], prob_theme[v_pt])
print(f"P(great_buy) AUC:   BASELINE={auc_base:.4f}  THEME={auc_theme:.4f}  delta={auc_theme - auc_base:+.4f}")

v_ab = ~np.isnan(avoid_base)
v_at = ~np.isnan(avoid_theme)
y_avoid = (y_growth_pct < 8).astype(int)
avoid_auc_base = roc_auc_score(y_avoid[v_ab], avoid_base[v_ab])
avoid_auc_theme = roc_auc_score(y_avoid[v_at], avoid_theme[v_at])
print(f"P(avoid) AUC:       BASELINE={avoid_auc_base:.4f}  THEME={avoid_auc_theme:.4f}  delta={avoid_auc_theme - avoid_auc_base:+.4f}")

print(f"\nTheme coverage: {(df_train['theme'] != '').mean() * 100:.1f}% of training sets")
print(f"Time: {time.time() - t0:.1f}s")

if auc_theme > auc_base + 0.005 or avoid_auc_theme > avoid_auc_base + 0.005:
    print("\n>> POSITIVE: Theme features improve classifier(s). Integrate into production.")
elif auc_theme < auc_base - 0.005 or avoid_auc_theme < avoid_auc_base - 0.005:
    print("\n>> NEGATIVE: Theme features HURT the model. Do not integrate.")
else:
    print("\n>> NEUTRAL: Theme features have no meaningful effect (< 0.005 delta).")
