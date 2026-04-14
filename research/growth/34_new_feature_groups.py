"""Experiment 34: New feature group evaluation.

Evaluate 6 groups of untried features against the 35-feature baseline:
  A) Regional RRP ratios (SAFE -- factual LEGO.com prices)
  B) Keepa volatility (SAFE -- pre-retirement timelines)
  C) Price positioning (SAFE -- metadata-derived)
  D) FBM/Buy Box (SAFE -- timelines cut at retired_date)
  E) Derived interactions (SAFE -- combos of existing features)
  F) Tracking users (LEAKY -- current snapshot, post-retirement)

Run: python -m research.growth.34_new_feature_groups
"""
from __future__ import annotations

import json
import time
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

print("=" * 70)
print("EXP 34: NEW FEATURE GROUP EVALUATION")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from services.ml.encodings import compute_group_stats, group_mean_encode, loo_bayesian_encode
from services.ml.growth.keepa_features import (
    CLASSIFIER_FEATURES,
    GT_FEATURES,
    KEEPA_BL_FEATURES,
    _parse_date,
    _parse_timeline,
    compute_theme_keepa_stats,
    encode_theme_keepa_features,
    engineer_gt_features,
    engineer_keepa_bl_features,
)
from services.ml.growth.model_selection import clip_outliers, compute_recency_weights
from services.ml.pg_queries import (
    load_bl_ground_truth,
    load_google_trends_data,
    load_keepa_bl_training_data,
)

engine = get_engine()

# ============================================================================
# PHASE 0: DATA LOADING
# ============================================================================
print("\n--- Phase 0: Data Loading ---")
base_df, keepa_df, target_series = load_keepa_bl_training_data(engine)
bl_target = load_bl_ground_truth(engine)
gt_df = load_google_trends_data(engine)

print(f"Base: {len(base_df)}, Keepa: {len(keepa_df)}, Targets: {len(target_series)}")
print(f"BL ground truth: {len(bl_target)} sets")

# Supplementary: regional RRP columns
from services.ml.pg_queries import _read

regional_df = _read(engine, """
    SELECT set_number, rrp_gbp_cents, rrp_eur_cents,
           rrp_cad_cents, rrp_aud_cents
    FROM (
        SELECT DISTINCT ON (set_number) *
        FROM brickeconomy_snapshots
        ORDER BY set_number, scraped_at DESC
    ) be
    WHERE be.rrp_usd_cents > 0
""")
base_df = base_df.merge(regional_df, on="set_number", how="left")
print(f"Regional RRP merged: {regional_df['rrp_gbp_cents'].notna().sum()} sets with GBP")

# Engineer baseline features (35 = 28 base + 7 GT)
df_feat = engineer_keepa_bl_features(base_df, keepa_df)

# Add theme encoding (Exp 33)
theme_stats = compute_theme_keepa_stats(df_feat)
df_feat = encode_theme_keepa_features(df_feat, theme_stats=theme_stats, training=True)

# Merge GT
gt_feat = engineer_gt_features(gt_df, base_df)
df_feat = df_feat.merge(gt_feat, on="set_number", how="left")
for col in GT_FEATURES:
    if col not in df_feat.columns:
        df_feat[col] = 0.0
    else:
        df_feat[col] = df_feat[col].fillna(0.0)

# Add year_retired and metadata from base_df
yr_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
rrp_map = dict(zip(base_df["set_number"].astype(str), base_df.get("rrp_usd_cents")))
theme_map = dict(zip(base_df["set_number"].astype(str), base_df.get("theme")))
parts_map = dict(zip(base_df["set_number"].astype(str), base_df.get("parts_count")))
retired_date_map = dict(zip(base_df["set_number"].astype(str), base_df.get("retired_date")))
gbp_map = dict(zip(base_df["set_number"].astype(str), base_df.get("rrp_gbp_cents")))
eur_map = dict(zip(base_df["set_number"].astype(str), base_df.get("rrp_eur_cents")))
cad_map = dict(zip(base_df["set_number"].astype(str), base_df.get("rrp_cad_cents")))
aud_map = dict(zip(base_df["set_number"].astype(str), base_df.get("rrp_aud_cents")))

for _, row in base_df.iterrows():
    sn = str(row["set_number"])
    if sn not in yr_map or pd.isna(yr_map.get(sn)):
        rd = pd.to_datetime(str(row.get("retired_date", "")), errors="coerce")
        if rd is not pd.NaT:
            yr_map[sn] = rd.year

df_feat["year_retired"] = df_feat["set_number"].map(yr_map).fillna(2023).astype(int)

# Map BL ground truth
df_feat["bl_ann_return"] = df_feat["set_number"].map(bl_target)
df_feat = df_feat[df_feat["bl_ann_return"].notna()].copy()

# Training set: retired <= 2024
train_mask = df_feat["year_retired"] <= 2024
df_train = df_feat[train_mask].copy()
print(f"\nTraining sets with BL ground truth: {len(df_train)} (retired <= 2024)")
print(f"Baseline features: {len(list(CLASSIFIER_FEATURES))}")

# ============================================================================
# PHASE 1: ENGINEER NEW FEATURES
# ============================================================================
print("\n--- Phase 1: Engineer New Features ---")

# Build keepa lookup for timeline re-parsing
keepa_lookup: dict[str, pd.Series] = {}
for _, row in keepa_df.iterrows():
    keepa_lookup[str(row["set_number"])] = row

# ---- GROUP A: Regional RRP Ratios ----
print("\n  Group A: Regional RRP Ratios")
for sn_col, src_map, col_name in [
    ("rrp_gbp_cents", gbp_map, "rrp_gbp_usd_ratio"),
    ("rrp_eur_cents", eur_map, "rrp_eur_usd_ratio"),
    ("rrp_cad_cents", cad_map, "rrp_cad_usd_ratio"),
    ("rrp_aud_cents", aud_map, "rrp_aud_usd_ratio"),
]:
    regional_vals = df_train["set_number"].map(src_map).astype(float)
    rrp_vals = df_train["set_number"].map(rrp_map).astype(float)
    df_train[col_name] = regional_vals / rrp_vals
    df_train[col_name] = df_train[col_name].replace([np.inf, -np.inf], np.nan)

# Regional CV (across exchange-rate-normalized prices)
# Approximate exchange rates (average over LEGO pricing history)
FX_RATES = {"usd": 1.0, "gbp": 1.27, "eur": 1.08, "cad": 0.74, "aud": 0.66}

regional_cols_for_cv = []
for curr, fx in FX_RATES.items():
    if curr == "usd":
        col = "rrp_usd_norm"
        df_train[col] = df_train["set_number"].map(rrp_map).astype(float) * fx
    else:
        src = {"gbp": gbp_map, "eur": eur_map, "cad": cad_map, "aud": aud_map}[curr]
        col = f"rrp_{curr}_norm"
        df_train[col] = df_train["set_number"].map(src).astype(float) * fx
    regional_cols_for_cv.append(col)

norm_df = df_train[regional_cols_for_cv].copy()
df_train["rrp_regional_cv"] = norm_df.std(axis=1) / norm_df.mean(axis=1)
df_train["rrp_regional_cv"] = df_train["rrp_regional_cv"].fillna(0)

# UK premium: deviation from mean GBP/USD ratio
mean_gbp_ratio = df_train["rrp_gbp_usd_ratio"].median()
df_train["rrp_uk_premium"] = df_train["rrp_gbp_usd_ratio"] - mean_gbp_ratio

# Clean up temp columns
for col in regional_cols_for_cv:
    df_train.drop(columns=[col], inplace=True, errors="ignore")

GROUP_A = ["rrp_gbp_usd_ratio", "rrp_eur_usd_ratio", "rrp_regional_cv", "rrp_uk_premium"]
a_cov = {f: df_train[f].notna().sum() for f in GROUP_A}
print(f"    Features: {GROUP_A}")
print(f"    Coverage: {a_cov}")


# ---- GROUP B: Keepa Volatility ----
print("\n  Group B: Keepa Volatility")

vol_records: list[dict] = []
for _, row in df_train.iterrows():
    sn = str(row["set_number"])
    kp = keepa_lookup.get(sn)
    rec: dict[str, float] = {"set_number": sn}

    if kp is None:
        vol_records.append(rec)
        continue

    rrp = float(rrp_map.get(sn, 0) or 0)
    if rrp <= 0:
        vol_records.append(rec)
        continue

    retired_str = None
    rd = _parse_date(str(retired_date_map.get(sn, "")))
    if rd and rd is not pd.NaT:
        try:
            retired_str = rd.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass

    def _cut(tl: list[list]) -> list[list]:
        if not retired_str:
            return tl
        return [p for p in tl if len(p) >= 2 and isinstance(p[0], str) and p[0] <= retired_str]

    amz_raw = _parse_timeline(kp.get("amazon_price_json"))
    fba_raw = _parse_timeline(kp.get("new_3p_fba_json"))
    amz = _cut(amz_raw)
    fba = _cut(fba_raw)

    amz_prices = [float(p[1]) for p in amz if p[1] is not None and p[1] > 0]
    fba_prices = [float(p[1]) for p in fba if p[1] is not None and p[1] > 0]

    # Amazon volatility
    if amz_prices and rrp > 0:
        rec["amz_price_range_pct"] = (max(amz_prices) - min(amz_prices)) / rrp * 100

        # Max drawdown: largest peak-to-trough
        peak = amz_prices[0]
        max_dd = 0.0
        for p in amz_prices:
            if p > peak:
                peak = p
            dd = (peak - p) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        rec["amz_price_drawdown"] = max_dd * 100

        # Late vs early CV
        if len(amz_prices) >= 10:
            half = len(amz_prices) // 2
            early = amz_prices[:half]
            late = amz_prices[half:]
            cv_early = np.std(early) / np.mean(early) if np.mean(early) > 0 else 0
            cv_late = np.std(late) / np.mean(late) if np.mean(late) > 0 else 0
            rec["late_vs_early_cv"] = cv_late / cv_early if cv_early > 0 else 1.0

    # FBA volatility
    if fba_prices and rrp > 0:
        rec["fba_price_range_pct"] = (max(fba_prices) - min(fba_prices)) / rrp * 100

        fba_mean = np.mean(fba_prices)
        if fba_mean > 0:
            within_band = sum(1 for p in fba_prices if abs(p - fba_mean) / fba_mean <= 0.10)
            rec["fba_price_stability"] = within_band / len(fba_prices) * 100

    vol_records.append(rec)

vol_df = pd.DataFrame(vol_records)
GROUP_B = ["amz_price_range_pct", "amz_price_drawdown", "late_vs_early_cv",
           "fba_price_range_pct", "fba_price_stability"]
for col in GROUP_B:
    if col in vol_df.columns:
        df_train[col] = vol_df.set_index("set_number").reindex(df_train["set_number"].values)[col].values
    else:
        df_train[col] = np.nan
    df_train[col] = df_train[col].fillna(0)

b_cov = {f: (df_train[f] != 0).sum() for f in GROUP_B}
print(f"    Features: {GROUP_B}")
print(f"    Coverage (non-zero): {b_cov}")


# ---- GROUP C: Price Positioning ----
print("\n  Group C: Price Positioning")

df_train["_rrp"] = df_train["set_number"].map(rrp_map).astype(float)
df_train["_parts"] = df_train["set_number"].map(parts_map).astype(float).fillna(0)
df_train["_theme"] = df_train["set_number"].map(theme_map).fillna("")
df_train["_ppp"] = df_train["_parts"] / df_train["_rrp"]
df_train["_ppp"] = df_train["_ppp"].replace([np.inf, -np.inf], 0).fillna(0)

# RRP percentile within theme (LOO: exclude self for rank)
df_train["rrp_pctile_in_theme"] = df_train.groupby("_theme")["_rrp"].rank(pct=True)
df_train["rrp_pctile_in_year"] = df_train.groupby("year_retired")["_rrp"].rank(pct=True)

# PPP vs theme average (LOO Bayesian encoded)
ppp_stats = compute_group_stats(df_train, "_theme", df_train["_ppp"].astype(float))
theme_avg_ppp = loo_bayesian_encode(df_train["_theme"], df_train["_ppp"].astype(float), ppp_stats, alpha=20)
df_train["ppp_vs_theme_avg"] = df_train["_ppp"] / theme_avg_ppp
df_train["ppp_vs_theme_avg"] = df_train["ppp_vs_theme_avg"].replace([np.inf, -np.inf], 1.0).fillna(1.0)

# RRP vs theme median
theme_rrp_median = df_train.groupby("_theme")["_rrp"].transform("median")
df_train["rrp_vs_theme_median"] = df_train["_rrp"] / theme_rrp_median
df_train["rrp_vs_theme_median"] = df_train["rrp_vs_theme_median"].replace([np.inf, -np.inf], 1.0).fillna(1.0)

GROUP_C = ["rrp_pctile_in_theme", "rrp_pctile_in_year", "ppp_vs_theme_avg", "rrp_vs_theme_median"]
print(f"    Features: {GROUP_C}")

# Clean up temp columns
for col in ["_rrp", "_parts", "_theme", "_ppp"]:
    df_train.drop(columns=[col], inplace=True, errors="ignore")


# ---- GROUP D: FBM / Buy Box ----
print("\n  Group D: FBM / Buy Box")

fbm_records: list[dict] = []
for _, row in df_train.iterrows():
    sn = str(row["set_number"])
    kp = keepa_lookup.get(sn)
    rec: dict[str, float] = {"set_number": sn}

    if kp is None:
        fbm_records.append(rec)
        continue

    rrp = float(rrp_map.get(sn, 0) or 0)
    if rrp <= 0:
        fbm_records.append(rec)
        continue

    retired_str = None
    rd = _parse_date(str(retired_date_map.get(sn, "")))
    if rd and rd is not pd.NaT:
        try:
            retired_str = rd.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass

    def _cut(tl: list[list]) -> list[list]:
        if not retired_str:
            return tl
        return [p for p in tl if len(p) >= 2 and isinstance(p[0], str) and p[0] <= retired_str]

    fbm_raw = _parse_timeline(kp.get("new_3p_fbm_json"))
    bb_raw = _parse_timeline(kp.get("buy_box_json"))
    fba_raw = _parse_timeline(kp.get("new_3p_fba_json"))
    amz_raw = _parse_timeline(kp.get("amazon_price_json"))

    fbm = _cut(fbm_raw)
    bb = _cut(bb_raw)
    fba = _cut(fba_raw)
    amz = _cut(amz_raw)

    fbm_prices = [float(p[1]) for p in fbm if p[1] is not None and p[1] > 0]
    bb_prices = [float(p[1]) for p in bb if p[1] is not None and p[1] > 0]
    fba_prices = [float(p[1]) for p in fba if p[1] is not None and p[1] > 0]

    rec["has_fbm_data"] = 1.0 if fbm_prices else 0.0

    if fbm_prices and fba_prices:
        rec["fbm_fba_spread"] = np.mean(fbm_prices) / np.mean(fba_prices)

    if bb_prices and rrp > 0:
        rec["buybox_premium_avg"] = np.mean(bb_prices) / rrp

    if bb_prices and amz:
        rec["buybox_coverage_pct"] = len(bb_prices) / max(len(amz), 1) * 100

    fbm_records.append(rec)

fbm_df = pd.DataFrame(fbm_records)
GROUP_D = ["has_fbm_data", "fbm_fba_spread", "buybox_premium_avg", "buybox_coverage_pct"]
for col in GROUP_D:
    if col in fbm_df.columns:
        df_train[col] = fbm_df.set_index("set_number").reindex(df_train["set_number"].values)[col].values
    else:
        df_train[col] = np.nan
    df_train[col] = df_train[col].fillna(0)

d_cov = {f: (df_train[f] != 0).sum() for f in GROUP_D}
print(f"    Features: {GROUP_D}")
print(f"    Coverage (non-zero): {d_cov}")


# ---- GROUP E: Derived Interactions ----
print("\n  Group E: Derived Interactions")

amz_retire = df_train.get("amz_price_at_retire_vs_rrp", pd.Series(dtype=float)).fillna(0)
fba_retire = df_train.get("3p_price_at_retire_vs_rrp", pd.Series(dtype=float)).fillna(0)
df_train["amz_fba_spread_at_retire"] = np.where(
    fba_retire > 0, amz_retire / fba_retire, 0
)

df_train["discount_x_tier"] = (
    df_train.get("amz_max_discount_pct", pd.Series(0, index=df_train.index)).fillna(0)
    * df_train.get("price_tier", pd.Series(0, index=df_train.index)).fillna(0)
)

rrp_usd_vals = df_train["set_number"].map(rrp_map).astype(float)
df_train["reviews_per_dollar"] = (
    df_train.get("amz_review_count", pd.Series(0, index=df_train.index)).fillna(0)
    / (rrp_usd_vals / 100).replace(0, np.nan)
).fillna(0)

GROUP_E = ["amz_fba_spread_at_retire", "discount_x_tier", "reviews_per_dollar"]
print(f"    Features: {GROUP_E}")


# ---- GROUP F: Tracking Users (LEAKY) ----
print("\n  Group F: Tracking Users (LEAKY)")

tracking_map: dict[str, float] = {}
for _, row in keepa_df.iterrows():
    sn = str(row["set_number"])
    tu = row.get("tracking_users")
    if pd.notna(tu) and float(tu) > 0:
        tracking_map[sn] = float(tu)

tracking_vals = df_train["set_number"].map(tracking_map)
df_train["log_tracking_users"] = np.log1p(tracking_vals.fillna(0))
df_train["tracking_per_dollar"] = tracking_vals.fillna(0) / (rrp_usd_vals / 100).replace(0, np.nan)
df_train["tracking_per_dollar"] = df_train["tracking_per_dollar"].fillna(0)
df_train["tracking_x_3p_premium"] = (
    df_train["log_tracking_users"]
    * df_train.get("3p_above_rrp_pct", pd.Series(0, index=df_train.index)).fillna(0)
)

GROUP_F = ["log_tracking_users", "tracking_per_dollar", "tracking_x_3p_premium"]
f_cov = (tracking_vals.notna()).sum()
print(f"    Features: {GROUP_F}")
print(f"    Coverage: {f_cov}/{len(df_train)} ({f_cov / len(df_train) * 100:.1f}%)")

ALL_NEW_FEATURES = GROUP_A + GROUP_B + GROUP_C + GROUP_D + GROUP_E + GROUP_F
SAFE_FEATURES = GROUP_A + GROUP_B + GROUP_C + GROUP_D + GROUP_E
print(f"\nTotal new features: {len(ALL_NEW_FEATURES)} ({len(SAFE_FEATURES)} safe + {len(GROUP_F)} leaky)")

# ============================================================================
# PHASE 2: DIAGNOSTICS
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 2: FEATURE DIAGNOSTICS")
print("=" * 70)

y_ann = df_train["bl_ann_return"].values.astype(float)
y_avoid = (y_ann < 8.0).astype(int)
y_great = (y_ann >= 20.0).astype(int)

print(f"\n{'Feature':35s} {'Cov%':>5s} {'Sprmn':>7s} {'MI_avd':>7s} {'MI_gb':>7s} {'p25':>7s} {'p50':>7s} {'p75':>7s} {'p90':>7s}")
print("-" * 110)

viable_features: list[str] = []
for feat in ALL_NEW_FEATURES:
    vals = df_train[feat].values.astype(float)
    nonzero = (vals != 0) & np.isfinite(vals)
    coverage = nonzero.sum() / len(vals) * 100

    if nonzero.sum() < 30:
        print(f"{feat:35s} {coverage:5.1f}  (too few non-zero)")
        continue

    sp, _ = spearmanr(vals[nonzero], y_ann[nonzero])

    # Mutual information (need finite values)
    finite_mask = np.isfinite(vals)
    vals_finite = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
    vals_2d = vals_finite.reshape(-1, 1)
    mi_avoid = mutual_info_classif(vals_2d, y_avoid, random_state=42, n_neighbors=5)[0]
    mi_great = mutual_info_classif(vals_2d, y_great, random_state=42, n_neighbors=5)[0]

    p25, p50, p75, p90 = np.nanpercentile(vals[nonzero], [25, 50, 75, 90])

    leaky = " LEAKY" if feat in GROUP_F else ""
    print(f"{feat:35s} {coverage:5.1f} {sp:+.4f} {mi_avoid:.4f} {mi_great:.4f} {p25:7.3f} {p50:7.3f} {p75:7.3f} {p90:7.3f}{leaky}")

    if mi_avoid >= 0.003 or mi_great >= 0.003:
        viable_features.append(feat)

print(f"\nViable features (MI >= 0.003): {len(viable_features)}")
for f in viable_features:
    tag = " (LEAKY)" if f in GROUP_F else ""
    print(f"  {f}{tag}")

# ============================================================================
# PHASE 3: GROUPKFOLD CV
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 3: GROUPKFOLD CV")
print("=" * 70)

baseline_features = [f for f in CLASSIFIER_FEATURES if f in df_train.columns]
groups = df_train["year_retired"].values
n_splits = min(5, len(np.unique(groups)))
gkf = GroupKFold(n_splits=n_splits)

CLF_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "max_depth": 4,
    "min_child_samples": 10,
    "is_unbalance": True,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "verbosity": -1,
}


def run_clf_cv(
    feature_names: list[str],
    label: str,
    threshold: float = 8.0,
    invert: bool = False,
) -> float:
    """Run GroupKFold CV for a binary classifier, return AUC."""
    X_raw = df_train[feature_names].fillna(0).copy()
    X_arr = clip_outliers(X_raw).values.astype(float)

    y_binary = (y_ann >= threshold).astype(int) if invert else (y_ann < threshold).astype(int)

    oof = np.full(len(y_binary), np.nan)
    for tr_idx, va_idx in gkf.split(X_arr, y_binary, groups):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_arr[tr_idx])
        X_va = scaler.transform(X_arr[va_idx])
        clf = lgb.LGBMClassifier(n_estimators=200, **CLF_PARAMS, random_state=42, n_jobs=1)
        clf.fit(X_tr, y_binary[tr_idx])
        oof[va_idx] = clf.predict_proba(X_va)[:, 1]

    valid = ~np.isnan(oof)
    auc = roc_auc_score(y_binary[valid], oof[valid])
    return auc


# Run all configurations
configs: dict[str, list[str]] = {
    "BASELINE": baseline_features,
    "+GROUP_A (Regional RRP)": baseline_features + GROUP_A,
    "+GROUP_B (Keepa Vol)": baseline_features + GROUP_B,
    "+GROUP_C (Price Pos)": baseline_features + GROUP_C,
    "+GROUP_D (FBM/BB)": baseline_features + GROUP_D,
    "+GROUP_E (Interactions)": baseline_features + GROUP_E,
    "+SAFE_ALL (A+B+C+D+E)": baseline_features + SAFE_FEATURES,
    "+GROUP_F (Tracking LEAKY)": baseline_features + GROUP_F,
    "+EVERYTHING": baseline_features + ALL_NEW_FEATURES,
}

results: list[dict] = []
print(f"\n{'Config':35s} {'#Feat':>6s} {'Avoid AUC':>10s} {'dAvoid':>8s} {'GB AUC':>10s} {'dGB':>8s}")
print("-" * 85)

baseline_avoid = None
baseline_gb = None

for config_name, feats in configs.items():
    avoid_auc = run_clf_cv(feats, config_name, threshold=8.0, invert=False)
    gb_auc = run_clf_cv(feats, config_name, threshold=20.0, invert=True)

    if config_name == "BASELINE":
        baseline_avoid = avoid_auc
        baseline_gb = gb_auc

    d_avoid = avoid_auc - baseline_avoid if baseline_avoid else 0
    d_gb = gb_auc - baseline_gb if baseline_gb else 0

    results.append({
        "config": config_name, "n_feat": len(feats),
        "avoid_auc": avoid_auc, "gb_auc": gb_auc,
        "d_avoid": d_avoid, "d_gb": d_gb,
    })

    leaky = " *LEAKY*" if "LEAKY" in config_name or "EVERYTHING" in config_name else ""
    print(f"{config_name:35s} {len(feats):6d} {avoid_auc:10.4f} {d_avoid:+8.4f} {gb_auc:10.4f} {d_gb:+8.4f}{leaky}")

# ============================================================================
# PHASE 4: ABLATION (LOFO on SAFE_ALL new features)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 4: ABLATION (LOFO on new features in SAFE_ALL)")
print("=" * 70)

safe_all_feats = baseline_features + SAFE_FEATURES
safe_avoid = run_clf_cv(safe_all_feats, "SAFE_ALL", threshold=8.0, invert=False)
safe_gb = run_clf_cv(safe_all_feats, "SAFE_ALL", threshold=20.0, invert=True)

print(f"\n{'Removed Feature':35s} {'Avoid AUC':>10s} {'dAvoid':>8s} {'GB AUC':>10s} {'dGB':>8s} {'Verdict':>10s}")
print("-" * 90)

for feat in SAFE_FEATURES:
    reduced = [f for f in safe_all_feats if f != feat]
    avoid_auc = run_clf_cv(reduced, f"-{feat}", threshold=8.0, invert=False)
    gb_auc = run_clf_cv(reduced, f"-{feat}", threshold=20.0, invert=True)
    d_avoid = avoid_auc - safe_avoid
    d_gb = gb_auc - safe_gb
    # If removing hurts (negative delta), the feature helps
    verdict = "HELPS" if (d_avoid < -0.002 or d_gb < -0.002) else (
        "HURTS" if (d_avoid > 0.002 or d_gb > 0.002) else "NEUTRAL"
    )
    print(f"{feat:35s} {avoid_auc:10.4f} {d_avoid:+8.4f} {gb_auc:10.4f} {d_gb:+8.4f} {verdict:>10s}")

# ============================================================================
# PHASE 5: FORWARD SELECTION
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 5: FORWARD SELECTION (greedy, from baseline)")
print("=" * 70)

selected: list[str] = []
remaining = list(SAFE_FEATURES)
current_feats = list(baseline_features)
current_avoid = baseline_avoid
current_gb = baseline_gb

print(f"\nStarting from baseline: Avoid={current_avoid:.4f}, GB={current_gb:.4f}")

for step in range(len(SAFE_FEATURES)):
    best_feat = None
    best_score = -1.0
    best_avoid = current_avoid
    best_gb = current_gb

    for feat in remaining:
        trial_feats = current_feats + selected + [feat]
        avoid_auc = run_clf_cv(trial_feats, f"+{feat}", threshold=8.0, invert=False)
        gb_auc = run_clf_cv(trial_feats, f"+{feat}", threshold=20.0, invert=True)
        # Combined improvement (equal weight on both classifiers)
        score = (avoid_auc - current_avoid) + (gb_auc - current_gb)
        if score > best_score:
            best_score = score
            best_feat = feat
            best_avoid = avoid_auc
            best_gb = gb_auc

    if best_score < 0.003:
        print(f"\n  Step {step + 1}: best candidate '{best_feat}' adds {best_score:+.4f} (< 0.003 threshold). STOPPING.")
        break

    selected.append(best_feat)
    remaining.remove(best_feat)
    current_avoid = best_avoid
    current_gb = best_gb
    print(f"  Step {step + 1}: +{best_feat:30s}  Avoid={best_avoid:.4f} ({best_avoid - baseline_avoid:+.4f})  "
          f"GB={best_gb:.4f} ({best_gb - baseline_gb:+.4f})  combined={best_score:+.4f}")

print(f"\nSelected features ({len(selected)}):")
for f in selected:
    group = "A" if f in GROUP_A else "B" if f in GROUP_B else "C" if f in GROUP_C else "D" if f in GROUP_D else "E"
    print(f"  [{group}] {f}")

# ============================================================================
# PHASE 6: FEATURE IMPORTANCE (best config)
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 6: FEATURE IMPORTANCE (SAFE_ALL)")
print("=" * 70)

X_full = df_train[safe_all_feats].fillna(0).copy()
X_arr = clip_outliers(X_full).values.astype(float)
y_binary = (y_ann < 8.0).astype(int)

clf = lgb.LGBMClassifier(n_estimators=200, **CLF_PARAMS, random_state=42, n_jobs=1)
clf.fit(X_arr, y_binary)
imp = dict(zip(safe_all_feats, clf.feature_importances_))
sorted_imp = sorted(imp.items(), key=lambda x: x[1], reverse=True)

print(f"\n{'Rank':>4s} {'Feature':35s} {'Importance':>12s} {'Group':>6s}")
print("-" * 62)
for rank, (feat, importance) in enumerate(sorted_imp[:30], 1):
    group = ("A" if feat in GROUP_A else "B" if feat in GROUP_B else "C" if feat in GROUP_C
             else "D" if feat in GROUP_D else "E" if feat in GROUP_E else "-")
    marker = f"  NEW" if feat in SAFE_FEATURES else ""
    print(f"{rank:4d} {feat:35s} {importance:12d} {group:>6s}{marker}")

# ============================================================================
# PHASE 7: SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("EXPERIMENT 34: SUMMARY")
print("=" * 70)

print(f"\nBaseline: {len(baseline_features)} features, Avoid AUC={baseline_avoid:.4f}, GB AUC={baseline_gb:.4f}")
print(f"\nGroup Results:")
for r in results:
    leaky = " *LEAKY*" if "LEAKY" in r["config"] or "EVERYTHING" in r["config"] else ""
    sign_a = "+" if r["d_avoid"] > 0.003 else ("-" if r["d_avoid"] < -0.003 else "=")
    sign_g = "+" if r["d_gb"] > 0.003 else ("-" if r["d_gb"] < -0.003 else "=")
    print(f"  {r['config']:35s}  Avoid {sign_a}{r['d_avoid']:+.4f}  GB {sign_g}{r['d_gb']:+.4f}{leaky}")

print(f"\nForward-selected features: {selected}")
print(f"Total features if integrated: {len(baseline_features) + len(selected)}")

elapsed = time.time() - t0
print(f"\nTime: {elapsed:.1f}s")
