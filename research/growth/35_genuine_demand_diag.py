"""Diagnostic: genuine-buyer demand features (tracking, reviews, quality interactions).

Tests F2/F3/F4 candidates from the genuine-demand plan against BL ground truth:
  F2: amz_log_tracking_users
  F3: amz_tracker_review_ratio
  F4: amz_quality_demand = log1p(reviews) * rating

Reports raw correlations, MI, distributions, quartile analysis, and
collinearity vs existing demand features. No CV (skipped due to clip_outliers
crash in 35_phase_composites.py); diagnostic phase only.

Run: python -m research.growth.35_genuine_demand_diag
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr
from sklearn.feature_selection import mutual_info_classif

from db.pg.engine import get_engine
from services.ml.growth.keepa_features import engineer_keepa_bl_features
from services.ml.pg_queries import (
    load_bl_ground_truth,
    load_keepa_bl_training_data,
)

print("=" * 72)
print("GENUINE-DEMAND DIAGNOSTIC: F2/F3/F4 (tracking, ratios, quality)")
print("=" * 72)

engine = get_engine()
base_df, keepa_df, _ = load_keepa_bl_training_data(engine)
bl_target = load_bl_ground_truth(engine)
print(f"Base: {len(base_df)}  Keepa: {len(keepa_df)}  BL target: {len(bl_target)}")

df = engineer_keepa_bl_features(base_df, keepa_df)
df["bl_ann_return"] = df["set_number"].map(bl_target)
df = df[df["bl_ann_return"].notna()].copy()

# Year filter (mirror production: retired <= 2024)
yr_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
df["year_retired"] = df["set_number"].map(yr_map).fillna(2024).astype(int)
df = df[df["year_retired"] <= 2024].copy()
print(f"Training sets with BL ground truth (retired<=2024): {len(df)}")

# Pull tracking_users from keepa_df (not in engineered features yet)
tracking_map: dict[str, float] = {}
for _, row in keepa_df.iterrows():
    sn = str(row["set_number"])
    tu = row.get("tracking_users")
    if pd.notna(tu) and float(tu) > 0:
        tracking_map[sn] = float(tu)

df["tracking_users_raw"] = df["set_number"].astype(str).map(tracking_map)

print(f"\nCoverage: tracking_users non-null = {df['tracking_users_raw'].notna().sum()}/{len(df)}")
print(f"          amz_review_count > 0   = {(df.get('amz_review_count', 0) > 0).sum()}/{len(df)}")
print(f"          amz_rating > 0         = {(df.get('amz_rating', 0) > 0).sum()}/{len(df)}")

# ============================================================================
# Engineer F2/F3/F4
# ============================================================================
df["amz_log_tracking_users"] = np.log1p(df["tracking_users_raw"].fillna(0))

reviews = df.get("amz_review_count", pd.Series(0, index=df.index)).fillna(0)
rating = df.get("amz_rating", pd.Series(0, index=df.index)).fillna(0)
tracking = df["tracking_users_raw"].fillna(0)

df["amz_tracker_review_ratio"] = tracking / np.maximum(reviews, 1.0)
df["amz_log_tracker_review_ratio"] = np.log1p(df["amz_tracker_review_ratio"])

df["amz_quality_demand"] = np.log1p(reviews) * rating

# Existing features for comparison
df["meta_demand_proxy_existing"] = df.get("meta_demand_proxy", 0).fillna(0)
df["amz_review_count_existing"] = reviews
df["amz_rating_existing"] = rating

# ============================================================================
# Diagnostic table
# ============================================================================
y = df["bl_ann_return"].values.astype(float)
y_avoid = (y < 8.0).astype(int)
y_great = (y >= 20.0).astype(int)

CANDIDATES = [
    # New
    "amz_log_tracking_users",
    "amz_tracker_review_ratio",
    "amz_log_tracker_review_ratio",
    "amz_quality_demand",
    # Existing baselines for comparison
    "amz_review_count_existing",
    "amz_rating_existing",
    "meta_demand_proxy_existing",
]

print("\n" + "=" * 100)
print("PHASE 1: UNIVARIATE DIAGNOSTIC (Spearman vs BL ann return; MI vs avoid/great_buy)")
print("=" * 100)
print(f"{'Feature':35s} {'Cov%':>5s} {'Sprmn':>8s} {'MI_avd':>8s} {'MI_gb':>8s} {'p25':>10s} {'p50':>10s} {'p75':>10s} {'p90':>10s}")
print("-" * 110)

for feat in CANDIDATES:
    vals = df[feat].values.astype(float)
    nonzero = (vals != 0) & np.isfinite(vals)
    cov = nonzero.sum() / len(vals) * 100

    if nonzero.sum() < 30:
        print(f"{feat:35s} {cov:5.1f}  (too few non-zero)")
        continue

    sp, _ = spearmanr(vals[nonzero], y[nonzero])
    vals_finite = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
    mi_a = mutual_info_classif(vals_finite.reshape(-1, 1), y_avoid, random_state=42, n_neighbors=5)[0]
    mi_g = mutual_info_classif(vals_finite.reshape(-1, 1), y_great, random_state=42, n_neighbors=5)[0]
    p25, p50, p75, p90 = np.nanpercentile(vals[nonzero], [25, 50, 75, 90])

    print(f"{feat:35s} {cov:5.1f} {sp:+.4f} {mi_a:8.4f} {mi_g:8.4f} {p25:10.3f} {p50:10.3f} {p75:10.3f} {p90:10.3f}")

# ============================================================================
# Collinearity: how much do new features overlap with existing ones?
# ============================================================================
print("\n" + "=" * 72)
print("PHASE 2: COLLINEARITY (Pearson) vs existing demand features")
print("=" * 72)

NEW = ["amz_log_tracking_users", "amz_tracker_review_ratio", "amz_log_tracker_review_ratio", "amz_quality_demand"]
EXISTING = ["amz_review_count_existing", "amz_rating_existing", "meta_demand_proxy_existing"]

print(f"\n{'New feature':35s}" + "".join(f"{e[:18]:>20s}" for e in EXISTING))
print("-" * 100)
for n in NEW:
    n_vals = df[n].values.astype(float)
    n_finite = np.nan_to_num(n_vals, nan=0.0, posinf=0.0, neginf=0.0)
    row_str = f"{n:35s}"
    for e in EXISTING:
        e_vals = df[e].values.astype(float)
        e_finite = np.nan_to_num(e_vals, nan=0.0, posinf=0.0, neginf=0.0)
        try:
            r, _ = pearsonr(n_finite, e_finite)
        except Exception:
            r = float("nan")
        row_str += f"{r:+20.4f}"
    print(row_str)

# ============================================================================
# Quartile analysis: for each new feature, do high values track higher returns?
# ============================================================================
print("\n" + "=" * 72)
print("PHASE 3: QUARTILE GROWTH (Q1=lowest, Q4=highest feature value)")
print("=" * 72)

for feat in NEW:
    vals = df[feat].values.astype(float)
    mask = np.isfinite(vals) & (vals != 0)
    if mask.sum() < 100:
        print(f"\n{feat}: too few non-zero ({mask.sum()})")
        continue
    sub = pd.DataFrame({"v": vals[mask], "y": y[mask]})
    sub["q"] = pd.qcut(sub["v"], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
    g = sub.groupby("q", observed=True)["y"].agg(["count", "mean", "median"])
    delta = g.loc["Q4", "mean"] - g.loc["Q1", "mean"] if "Q1" in g.index and "Q4" in g.index else float("nan")
    print(f"\n{feat}  (n={mask.sum()}, Q4-Q1 delta = {delta:+.2f}%)")
    print(g.round(2))

# ============================================================================
# Cross-check: tracker_review_ratio split
# ============================================================================
print("\n" + "=" * 72)
print("PHASE 4: tracker_review_ratio - HIGH ratio = speculator-watched, low-bought?")
print("=" * 72)

mask = (df["tracking_users_raw"] > 0) & (df["amz_review_count_existing"] > 0)
sub = df[mask].copy()
print(f"Sets with both signals present: {len(sub)}")
sub["tier"] = pd.qcut(sub["amz_tracker_review_ratio"], 4, labels=["Low (real buyers)", "Med-Low", "Med-High", "High (speculator-watched)"], duplicates="drop")
print(sub.groupby("tier", observed=True).agg(
    n=("bl_ann_return", "size"),
    mean_return=("bl_ann_return", "mean"),
    median_return=("bl_ann_return", "median"),
    avoid_rate=("bl_ann_return", lambda s: float((s < 8.0).mean())),
    great_buy_rate=("bl_ann_return", lambda s: float((s >= 20.0).mean())),
).round(3))

print("\n" + "=" * 72)
print("DONE")
print("=" * 72)
