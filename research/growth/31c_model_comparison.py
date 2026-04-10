"""Experiment 31c: Model comparison -- production T1 vs Exp 31 Keepa+BL model.

Both models evaluated against the SAME ground truth: BrickLink actual market
prices (not BE growth). This is the only fair comparison.

Ground truth targets:
  1. BL current new price / RRP (from bricklink_price_history)
  2. Keepa current price / RRP (from keepa_snapshots)

Run: python -m research.growth.31c_model_comparison
"""
from __future__ import annotations

import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score, mean_absolute_error

print("=" * 70)
print("EXP 31c: MODEL COMPARISON")
print("Production T1 vs Keepa+BL model -- same BrickLink ground truth")
print("=" * 70)

t0 = time.time()

from db.pg.engine import get_engine
from sqlalchemy import text

engine = get_engine()

# ============================================================================
# PHASE 1: LOAD ALL DATA
# ============================================================================
print("\n--- Phase 1: Load Data ---")

with engine.connect() as conn:
    # 1a. Production ML predictions (latest per set)
    prod_df = pd.read_sql(text("""
        SELECT set_number, predicted_growth_pct, confidence
        FROM (
            SELECT set_number, predicted_growth_pct, confidence,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY snapshot_date DESC) AS rn
            FROM ml_prediction_snapshots
        ) sub WHERE rn = 1
    """), conn)

    # 1b. BE metadata (for RRP, theme, retired_date -- factual only)
    be_df = pd.read_sql(text("""
        SELECT set_number, rrp_usd_cents, theme, subtheme, retired_date,
               year_retired, annual_growth_pct, value_new_cents
        FROM (
            SELECT set_number, rrp_usd_cents, theme, subtheme,
                   CAST(retired_date AS TEXT) AS retired_date,
                   year_retired, annual_growth_pct, value_new_cents,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY scraped_at DESC) AS rn
            FROM brickeconomy_snapshots
        ) sub WHERE rn = 1
    """), conn)

    # 1c. BrickLink price history (ground truth #1)
    bl_df = pd.read_sql(text("""
        SELECT set_number, current_new, six_month_new
        FROM (
            SELECT DISTINCT ON (set_number) set_number, current_new, six_month_new
            FROM bricklink_price_history
            ORDER BY set_number, scraped_at DESC
        ) sub
    """), conn)

    # 1d. Keepa current prices (ground truth #2)
    keepa_df = pd.read_sql(text("""
        SELECT set_number, current_buy_box_cents, current_amazon_cents,
               current_new_cents, new_3p_fba_json
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM keepa_snapshots
            ORDER BY set_number, scraped_at DESC
        ) sub
    """), conn)

    # 1e. lego_items for year_retired fallback
    li_df = pd.read_sql(text("""
        SELECT set_number, year_retired AS li_year_retired,
               CAST(retired_date AS TEXT) AS li_retired_date
        FROM lego_items
    """), conn)

print(f"Production predictions: {len(prod_df)} sets")
print(f"BE metadata: {len(be_df)} sets")
print(f"BL price history: {len(bl_df)} sets")
print(f"Keepa snapshots: {len(keepa_df)} sets")

# ============================================================================
# PHASE 2: BUILD GROUND TRUTH
# ============================================================================
print("\n--- Phase 2: Build Ground Truth ---")


def extract_bl_price(row: pd.Series, field: str) -> float | None:
    """Extract price from BL price history JSONB."""
    data = row.get(field)
    if not isinstance(data, dict):
        return None
    for key in ("qty_avg_price", "avg_price"):
        val = data.get(key)
        if isinstance(val, dict) and val.get("amount"):
            return float(val["amount"])
    return None


# BL current new price
bl_prices: dict[str, float] = {}
for _, row in bl_df.iterrows():
    price = extract_bl_price(row, "current_new")
    if price and price > 0:
        bl_prices[row["set_number"]] = price

# BL 6-month average
bl_6mo_prices: dict[str, float] = {}
for _, row in bl_df.iterrows():
    price = extract_bl_price(row, "six_month_new")
    if price and price > 0:
        bl_6mo_prices[row["set_number"]] = price

# Keepa: latest 3P FBA price (last data point)
import json

keepa_3p_prices: dict[str, float] = {}
for _, row in keepa_df.iterrows():
    raw = row.get("new_3p_fba_json")
    if raw is None:
        continue
    tl = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(tl, list) and tl:
        # Last non-null price
        for point in reversed(tl):
            if len(point) >= 2 and point[1] is not None and point[1] > 0:
                keepa_3p_prices[row["set_number"]] = float(point[1])
                break

# Keepa buy box
keepa_bb_prices: dict[str, float] = {}
for _, row in keepa_df.iterrows():
    bb = row.get("current_buy_box_cents")
    if bb and bb > 0:
        keepa_bb_prices[row["set_number"]] = float(bb)

print(f"BL current prices: {len(bl_prices)} sets")
print(f"BL 6-month avg prices: {len(bl_6mo_prices)} sets")
print(f"Keepa 3P FBA prices: {len(keepa_3p_prices)} sets")
print(f"Keepa buy box prices: {len(keepa_bb_prices)} sets")

# ============================================================================
# PHASE 3: BUILD COMPARISON DATASET
# ============================================================================
print("\n--- Phase 3: Build Comparison Dataset ---")

# Merge everything
comp = be_df[["set_number", "rrp_usd_cents", "theme", "retired_date",
              "year_retired", "annual_growth_pct", "value_new_cents"]].copy()
comp = comp.merge(li_df[["set_number", "li_year_retired", "li_retired_date"]],
                  on="set_number", how="left")

# Coalesce year_retired
comp["year_retired_final"] = comp["year_retired"].fillna(
    pd.to_numeric(comp["li_year_retired"], errors="coerce")
)
# Approximate from retired_date
retired_dt = pd.to_datetime(comp["retired_date"].fillna(comp["li_retired_date"]), errors="coerce")
comp["year_retired_final"] = comp["year_retired_final"].fillna(retired_dt.dt.year)
comp["is_retired"] = comp["year_retired_final"].notna()

# Add production predictions
comp = comp.merge(prod_df, on="set_number", how="left")

# Add BL ground truth
comp["bl_current_myr"] = comp["set_number"].map(bl_prices)
comp["bl_6mo_myr"] = comp["set_number"].map(bl_6mo_prices)

# Convert BL MYR to USD cents (MYR/USD ~ 4.4)
MYR_TO_USD = 1 / 4.4
comp["bl_current_usd_cents"] = comp["bl_current_myr"] * MYR_TO_USD
comp["bl_6mo_usd_cents"] = comp["bl_6mo_myr"] * MYR_TO_USD

# BL price / RRP ratio (ground truth)
comp["bl_vs_rrp"] = np.where(
    comp["rrp_usd_cents"] > 0,
    comp["bl_current_usd_cents"] / comp["rrp_usd_cents"],
    np.nan
)
comp["bl_6mo_vs_rrp"] = np.where(
    comp["rrp_usd_cents"] > 0,
    comp["bl_6mo_usd_cents"] / comp["rrp_usd_cents"],
    np.nan
)

# Add Keepa ground truth
comp["keepa_3p_usd_cents"] = comp["set_number"].map(keepa_3p_prices)
comp["keepa_bb_usd_cents"] = comp["set_number"].map(keepa_bb_prices)
comp["keepa_3p_vs_rrp"] = np.where(
    comp["rrp_usd_cents"] > 0,
    comp["keepa_3p_usd_cents"] / comp["rrp_usd_cents"],
    np.nan
)
comp["keepa_bb_vs_rrp"] = np.where(
    comp["rrp_usd_cents"] > 0,
    comp["keepa_bb_usd_cents"] / comp["rrp_usd_cents"],
    np.nan
)

# Production model: predicted price/RRP = 1 + growth%/100
# (BE growth is annual, but we use it as total appreciation proxy for retired sets)
comp["prod_predicted_vs_rrp"] = 1 + comp["predicted_growth_pct"].fillna(0) / 100

# BE value_new as another "prediction" baseline
comp["be_value_vs_rrp"] = np.where(
    comp["rrp_usd_cents"] > 0,
    comp["value_new_cents"] / comp["rrp_usd_cents"],
    np.nan
)

print(f"Comparison dataset: {len(comp)} sets")

# ============================================================================
# PHASE 4: EVALUATE ON RETIRED SETS WITH BL GROUND TRUTH
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 4: EVALUATION ON RETIRED SETS")
print("=" * 70)

# Filter: retired sets with both BL price and production prediction
eval_mask = (
    comp["bl_vs_rrp"].notna()
    & comp["predicted_growth_pct"].notna()
    & comp["is_retired"]
    & (comp["year_retired_final"] <= 2024)  # exclude barely-retired
)
df_eval = comp[eval_mask].copy()
print(f"\nEval set (retired <=2024, has BL price + prod prediction): {len(df_eval)}")

# Ground truths
gt_bl = df_eval["bl_vs_rrp"].values
gt_bl_6mo = df_eval["bl_6mo_vs_rrp"].values
gt_keepa_3p = df_eval["keepa_3p_vs_rrp"].values

# Predictions / baselines
pred_prod = df_eval["prod_predicted_vs_rrp"].values
pred_be_value = df_eval["be_value_vs_rrp"].values
pred_naive = np.ones(len(df_eval))  # naive: everything stays at RRP


def evaluate(name: str, pred: np.ndarray, actual: np.ndarray, min_n: int = 30) -> dict | None:
    """Evaluate predictions against actual."""
    mask = np.isfinite(pred) & np.isfinite(actual)
    if mask.sum() < min_n:
        return None
    p, a = pred[mask], actual[mask]
    r2 = r2_score(a, p)
    mae = mean_absolute_error(a, p)
    sp, _ = spearmanr(a, p)
    bias = float(np.mean(p - a))

    # Quintile separation
    q20 = np.percentile(p, 20)
    q80 = np.percentile(p, 80)
    bot_actual = a[p <= q20].mean() if (p <= q20).sum() > 0 else np.nan
    top_actual = a[p >= q80].mean() if (p >= q80).sum() > 0 else np.nan

    return {
        "name": name, "n": int(mask.sum()), "r2": r2, "mae": mae,
        "spearman": sp, "bias": bias,
        "bot20_actual": bot_actual, "top20_actual": top_actual,
        "separation": top_actual - bot_actual,
    }


print("\n--- Evaluation against BL Current Price / RRP ---")
print(f"{'Model':>25s} {'n':>5s} {'R2':>7s} {'MAE':>7s} {'Spearman':>9s} {'Bias':>7s} {'Bot20':>7s} {'Top20':>7s} {'Sep':>7s}")
print("-" * 90)

results = []
for name, pred in [
    ("Naive (1.0)", pred_naive),
    ("BE value_new/RRP", pred_be_value),
    ("Prod T1 (1+growth%)", pred_prod),
]:
    r = evaluate(name, pred, gt_bl)
    if r:
        results.append(r)
        print(f"  {r['name']:>23s} {r['n']:5d} {r['r2']:7.3f} {r['mae']:7.3f} {r['spearman']:9.3f} "
              f"{r['bias']:+7.3f} {r['bot20_actual']:7.3f} {r['top20_actual']:7.3f} {r['separation']:7.3f}")

# ============================================================================
# PHASE 5: EVALUATE KEEPA+BL MODEL (EXP 31)
# ============================================================================
print("\n--- Loading Exp 31 model predictions ---")

# We need to regenerate the Exp 31 OOF predictions for the same eval set.
# The fastest approach: re-run the model on the overlapping sets.
# Load keepa timelines and extract features for eval sets.

with engine.connect() as conn:
    keepa_tl = pd.read_sql(text("""
        SELECT set_number, amazon_price_json, new_3p_fba_json,
               new_3p_fbm_json, buy_box_json,
               tracking_users, review_count AS kp_reviews, rating AS kp_rating
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM keepa_snapshots
            WHERE amazon_price_json IS NOT NULL
            ORDER BY set_number, scraped_at DESC
        ) sub
    """), conn)

# Build base for feature extraction (same as exp 31)
from config.ml import LICENSED_THEMES
from datetime import datetime, timedelta

base_meta = be_df[["set_number", "rrp_usd_cents", "theme", "retired_date"]].copy()
base_meta = base_meta.merge(li_df[["set_number", "li_retired_date"]], on="set_number", how="left")
base_meta["retired_date"] = base_meta["retired_date"].fillna(base_meta["li_retired_date"])
base_meta = base_meta[base_meta["retired_date"].notna() & (base_meta["rrp_usd_cents"] > 0)]

merged_eval = base_meta.merge(keepa_tl, on="set_number", how="inner")
print(f"Sets for Exp 31 feature extraction: {len(merged_eval)}")

# Import the extract function from exp 31 (it's defined at module level)
# We'll inline a minimal version for speed
print("Re-extracting features inline...")

# Instead of importing, just do the model comparison using the data we already have.
# The Exp 31 model was trained with OOF on retired<=2024 sets.
# We stored oof_iter predictions in phase 12.
# But those are in-memory from the exp 31 run. We need to re-run or save/load.

# SIMPLEST APPROACH: Train the Exp 31 model on the FULL training pool,
# then predict on the eval set. This is slightly optimistic (not OOF) but
# allows a fair feature-set comparison.

# Actually, the cleanest approach: re-run both models with the SAME CV splits
# on the SAME data. Let me do that.

print("\nRe-running both models on same eval set with same CV...")

# We need the Exp 31 features for eval sets. Let me extract them.
# Copy the extract_features_for_set function body (it's ~300 lines in exp 31)
# For efficiency, let's just exec the extract function definition.

import importlib
import sys
import types

# Load just the function from exp 31 without running the whole script
exp31_path = "research/growth/31_keepa_bl_experiment.py"
with open(exp31_path) as f:
    source = f.read()

# Extract just the helper functions and extract_features_for_set
# Find the function boundaries
func_start = source.index("def parse_timeline(")
func_end = source.index("# Extract features for all sets")
func_code = source[func_start:func_end]

# Add necessary imports
exec_globals = {
    "np": np, "pd": pd, "json": json,
    "datetime": datetime, "timedelta": timedelta,
    "__builtins__": __builtins__,
}
exec(func_code, exec_globals)  # noqa: S102
extract_fn = exec_globals["extract_features_for_set"]

print("Feature extraction function loaded.")

# Extract features for all eval-eligible sets
print("Extracting Exp 31 features for eval sets...")
t_ext = time.time()
feat_rows = []
for _, row in merged_eval.iterrows():
    feat_rows.append(extract_fn(row))
exp31_features_df = pd.DataFrame(feat_rows)
print(f"Extracted {len(exp31_features_df)} sets in {time.time()-t_ext:.1f}s")

# Add metadata features
meta_eval = base_meta.copy()
for col in ("rrp_usd_cents",):
    meta_eval[col] = pd.to_numeric(meta_eval[col], errors="coerce")

# Merge with BE for parts/minifigs/etc
meta_full = meta_eval.merge(
    be_df[["set_number", "theme", "subtheme"]].drop_duplicates("set_number"),
    on="set_number", how="left", suffixes=("", "_be")
)
meta_full["theme"] = meta_full["theme"].fillna(meta_full.get("theme_be", ""))

# Add key metadata columns from lego_items
with engine.connect() as conn:
    li_meta = pd.read_sql(text("""
        SELECT set_number, parts_count, minifig_count
        FROM lego_items
    """), conn)
    be_extra = pd.read_sql(text("""
        SELECT set_number, pieces, minifigs, minifig_value_cents, exclusive_minifigs,
               rating_value, review_count AS be_reviews
        FROM (
            SELECT DISTINCT ON (set_number) *
            FROM brickeconomy_snapshots
            ORDER BY set_number, scraped_at DESC
        ) sub
    """), conn)

meta_full = meta_full.merge(li_meta, on="set_number", how="left")
meta_full = meta_full.merge(be_extra, on="set_number", how="left")
meta_full["parts_count"] = pd.to_numeric(
    meta_full["parts_count"].fillna(meta_full.get("pieces")), errors="coerce"
).fillna(0)
meta_full["minifig_count"] = pd.to_numeric(
    meta_full["minifig_count"].fillna(meta_full.get("minifigs")), errors="coerce"
).fillna(0)
meta_full["minifig_value_cents"] = pd.to_numeric(meta_full.get("minifig_value_cents"), errors="coerce").fillna(0)

# Compute metadata features
meta_full["price_per_part"] = np.where(
    meta_full["parts_count"] > 0,
    meta_full["rrp_usd_cents"] / meta_full["parts_count"], 0
)
meta_full["minifig_density"] = np.where(
    meta_full["parts_count"] > 0,
    meta_full["minifig_count"] / meta_full["parts_count"] * 100, 0
)
meta_full["minifig_value_ratio"] = np.where(
    meta_full["rrp_usd_cents"] > 0,
    meta_full["minifig_value_cents"] / meta_full["rrp_usd_cents"], 0
)
meta_full["has_exclusive_minifigs"] = meta_full["exclusive_minifigs"].notna().astype(float)
rrp_usd = meta_full["rrp_usd_cents"] / 100
meta_full["price_tier"] = pd.cut(
    rrp_usd, bins=[0, 15, 30, 50, 80, 120, 200, 500, 9999], labels=range(1, 9)
).astype(float)
meta_full["is_licensed"] = meta_full["theme"].isin(LICENSED_THEMES).astype(float)

retired_dt_m = pd.to_datetime(meta_full["retired_date"], errors="coerce")
meta_full["year_retired"] = retired_dt_m.dt.year

# Theme features
FALSE_POS_THEMES = {"Dots", "DUPLO", "Duplo", "Classic", "Seasonal",
                    "Holiday & Event", "Trolls World Tour", "Vidiyo"}
STRONG_THEMES = {"Star Wars", "Super Heroes", "Harry Potter", "Technic",
                 "Creator", "Icons", "NINJAGO", "Ninjago"}
meta_full["theme_false_pos"] = meta_full["theme"].isin(FALSE_POS_THEMES).astype(float)
meta_full["theme_strong"] = meta_full["theme"].isin(STRONG_THEMES).astype(float)

# Merge features + metadata
exp31_full = exp31_features_df.merge(
    meta_full[["set_number", "price_per_part", "minifig_density", "minifig_value_ratio",
               "has_exclusive_minifigs", "price_tier", "theme_false_pos", "theme_strong",
               "year_retired", "theme", "rrp_usd_cents"]],
    on="set_number", how="left"
)

# Add interaction and theme features
prem = exp31_full.get("3p_above_rrp_pct", pd.Series(0, index=exp31_full.index)).fillna(0)
exp31_full["3p_prem_adj"] = prem * (1 - 0.5 * exp31_full["theme_false_pos"].fillna(0))
exp31_full["strong_theme_x_prem"] = exp31_full["theme_strong"].fillna(0) * prem
exp31_full["3p_premium_x_minifig_density"] = (
    exp31_full.get("3p_avg_premium_vs_rrp_pct", pd.Series(0, index=exp31_full.index)).fillna(0)
    * exp31_full["minifig_density"].fillna(0)
)
exp31_full["has_keepa_3p"] = exp31_full["3p_above_rrp_pct"].notna().astype(float)
exp31_full["meta_demand_proxy"] = (
    np.log1p(exp31_full.get("amz_review_count", pd.Series(0, index=exp31_full.index)).fillna(0))
    * exp31_full["minifig_value_ratio"].fillna(0)
)

# Add BL ground truth
exp31_full["bl_vs_rrp"] = exp31_full["set_number"].map(
    dict(zip(comp["set_number"], comp["bl_vs_rrp"]))
)

# Final Exp 31 feature list (from phase 12)
EXP31_FEATURES = [
    "3p_price_at_retire_vs_rrp", "3p_premium_x_minifig_density",
    "3p_above_rrp_pct", "amz_review_count", "keepa_n_price_points",
    "3p_max_premium_vs_rrp_pct", "amz_discount_trend",
    "amz_price_at_retire_vs_rrp", "amz_max_discount_pct",
    "price_per_part", "amz_price_cv", "price_tier",
    "minifig_value_ratio", "3p_above_rrp_duration_days",
    "amz_max_restock_delay_days", "3p_price_cv",
    "minifig_density", "amz_never_discounted",
    "has_exclusive_minifigs", "amz_rating",
    "theme_false_pos", "theme_strong", "3p_prem_adj",
    "strong_theme_x_prem", "has_keepa_3p", "meta_demand_proxy",
]

# Filter to retired <= 2024, has target
eval_31 = exp31_full[
    (exp31_full["bl_vs_rrp"].notna())
    & (exp31_full["year_retired"].fillna(9999) <= 2024)
].copy()

print(f"\nExp 31 eval set: {len(eval_31)} sets")

# ============================================================================
# PHASE 6: HEAD-TO-HEAD CV COMPARISON
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 6: HEAD-TO-HEAD CV COMPARISON")
print("=" * 70)

import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer

# Find common sets between prod predictions and Exp 31 features
common_sets = set(df_eval["set_number"]) & set(eval_31["set_number"])
print(f"Common sets (both models can score): {len(common_sets)}")

# Build aligned datasets
df_common = df_eval[df_eval["set_number"].isin(common_sets)].copy()
df_common = df_common.sort_values("set_number").reset_index(drop=True)

exp31_common = eval_31[eval_31["set_number"].isin(common_sets)].copy()
exp31_common = exp31_common.sort_values("set_number").reset_index(drop=True)

# Verify alignment
assert list(df_common["set_number"]) == list(exp31_common["set_number"]), "Misaligned!"

y_common = df_common["bl_vs_rrp"].values.astype(float)
groups_common = df_common["year_retired_final"].fillna(2023).astype(int).values

print(f"Aligned common eval set: {len(df_common)} sets")
print(f"Target mean: {y_common.mean():.3f}, std: {y_common.std():.3f}")

# Winsorize
lo, hi = np.percentile(y_common, [2, 98])
y_clip = np.clip(y_common, lo, hi)

# --- Exp 31 Model: CV ---
print("\n--- Exp 31 Keepa+BL Model (5-fold GroupKFold) ---")
X_31 = exp31_common[EXP31_FEATURES].fillna(0).values.astype(float)

yt_31 = PowerTransformer(method="yeo-johnson")
y_t_31 = yt_31.fit_transform(y_clip.reshape(-1, 1)).ravel()

gkf = GroupKFold(n_splits=5)
oof_31 = np.full(len(y_clip), np.nan)

for fold_i, (tr, va) in enumerate(gkf.split(X_31, y_t_31, groups_common)):
    dtrain = lgb.Dataset(X_31[tr], label=y_t_31[tr], feature_name=EXP31_FEATURES)
    dval = lgb.Dataset(X_31[va], label=y_t_31[va], feature_name=EXP31_FEATURES, reference=dtrain)
    model = lgb.train(
        {"objective": "huber", "metric": "mae", "learning_rate": 0.068,
         "num_leaves": 20, "max_depth": 8, "min_child_samples": 19,
         "subsample": 0.6, "colsample_bytree": 0.88,
         "reg_alpha": 0.35, "reg_lambda": 0.009, "verbosity": -1},
        dtrain, num_boost_round=500, valid_sets=[dval],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    pred_t = model.predict(X_31[va])
    oof_31[va] = yt_31.inverse_transform(pred_t.reshape(-1, 1)).ravel()
    r2_f = r2_score(y_clip[va], oof_31[va])
    yrs = sorted(np.unique(groups_common[va]).tolist())
    print(f"  Fold {fold_i+1}: R2={r2_f:.3f}, years={yrs}")

# --- Production T1 Model: Use stored predictions (not CV, but fair enough) ---
# Prod predictions were made by a model trained on all data (including these sets),
# so this slightly favors production. But it's the "production" comparison.
oof_prod = df_common["prod_predicted_vs_rrp"].values
oof_be = df_common["be_value_vs_rrp"].values
oof_naive = np.ones(len(y_clip))

# ============================================================================
# PHASE 7: FINAL COMPARISON TABLE
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 7: FINAL COMPARISON -- ALL MODELS vs BL GROUND TRUTH")
print("=" * 70)

valid_31 = ~np.isnan(oof_31)

models = [
    ("Naive (1.0x RRP)", oof_naive, np.ones(len(y_clip), dtype=bool)),
    ("BE value_new / RRP", oof_be, np.isfinite(oof_be)),
    ("Prod T1 (1+growth%)", oof_prod, np.isfinite(oof_prod)),
    ("Exp 31 Keepa+BL (OOF)", oof_31, valid_31),
]

print(f"\n{'Model':>30s} {'n':>5s} {'R2':>7s} {'MAE':>7s} {'Spearman':>9s} {'Bias':>7s} {'Bot20':>7s} {'Top20':>7s} {'Sep':>7s}")
print("-" * 100)

for name, pred, mask in models:
    if mask.sum() < 30:
        print(f"  {name:>28s}  (too few: {mask.sum()})")
        continue
    p, a = pred[mask], y_clip[mask]
    r2 = r2_score(a, p)
    mae = mean_absolute_error(a, p)
    sp, _ = spearmanr(a, p)
    bias = float(np.mean(p - a))
    q20 = np.percentile(p, 20)
    q80 = np.percentile(p, 80)
    bot = a[p <= q20].mean()
    top = a[p >= q80].mean()
    sep = top - bot
    print(f"  {name:>28s} {mask.sum():5d} {r2:7.3f} {mae:7.3f} {sp:9.3f} {bias:+7.3f} {bot:7.3f} {top:7.3f} {sep:7.3f}")

# ============================================================================
# PHASE 8: PER-THEME COMPARISON
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 8: PER-THEME COMPARISON (Prod T1 vs Exp 31)")
print("=" * 70)

df_theme_comp = df_common.copy()
df_theme_comp["oof_31"] = oof_31
df_theme_comp["oof_prod"] = oof_prod

print(f"\n{'Theme':>20s} {'n':>4s}  {'Prod Sp':>8s} {'Exp31 Sp':>9s} {'Delta':>7s}  {'Prod R2':>8s} {'Exp31 R2':>9s}")
print("-" * 85)

theme_results = []
for theme, grp in df_theme_comp.groupby("theme"):
    if len(grp) < 10:
        continue
    a = y_clip[grp.index]
    p_prod = oof_prod[grp.index]
    p_31 = oof_31[grp.index]

    valid_both = np.isfinite(p_prod) & np.isfinite(p_31)
    if valid_both.sum() < 10:
        continue

    sp_prod, _ = spearmanr(a[valid_both], p_prod[valid_both])
    sp_31, _ = spearmanr(a[valid_both], p_31[valid_both])
    r2_prod = r2_score(a[valid_both], p_prod[valid_both])
    r2_31 = r2_score(a[valid_both], p_31[valid_both])

    delta = sp_31 - sp_prod
    winner = "<<< Exp31" if delta > 0.05 else (">>> Prod" if delta < -0.05 else "~tie")
    theme_results.append((theme, valid_both.sum(), sp_prod, sp_31, delta, r2_prod, r2_31, winner))

theme_results.sort(key=lambda x: -x[4])
for theme, n, sp_p, sp_31, delta, r2_p, r2_31, winner in theme_results:
    print(f"  {theme[:20]:>18s} {n:4d}  {sp_p:8.3f} {sp_31:9.3f} {delta:+7.3f}  {r2_p:8.3f} {r2_31:9.3f}  {winner}")

# Count wins
exp31_wins = sum(1 for _, _, _, _, d, _, _, _ in theme_results if d > 0.05)
prod_wins = sum(1 for _, _, _, _, d, _, _, _ in theme_results if d < -0.05)
ties = len(theme_results) - exp31_wins - prod_wins
print(f"\nTheme scoreboard: Exp31 wins {exp31_wins}, Prod wins {prod_wins}, Ties {ties}")

# ============================================================================
# PHASE 9: PER-YEAR COMPARISON
# ============================================================================
print("\n" + "=" * 70)
print("PHASE 9: PER-YEAR COMPARISON")
print("=" * 70)

print(f"\n{'Year':>6s} {'n':>4s}  {'Prod Sp':>8s} {'Exp31 Sp':>9s} {'Delta':>7s}  {'Prod R2':>8s} {'Exp31 R2':>9s}")
print("-" * 70)

for yr, grp in df_theme_comp.groupby("year_retired_final"):
    if len(grp) < 10 or pd.isna(yr):
        continue
    a = y_clip[grp.index]
    p_prod = oof_prod[grp.index]
    p_31 = oof_31[grp.index]
    valid_both = np.isfinite(p_prod) & np.isfinite(p_31)
    if valid_both.sum() < 10:
        continue
    sp_prod, _ = spearmanr(a[valid_both], p_prod[valid_both])
    sp_31, _ = spearmanr(a[valid_both], p_31[valid_both])
    r2_prod = r2_score(a[valid_both], p_prod[valid_both])
    r2_31 = r2_score(a[valid_both], p_31[valid_both])
    delta = sp_31 - sp_prod
    print(f"  {int(yr):6d} {valid_both.sum():4d}  {sp_prod:8.3f} {sp_31:9.3f} {delta:+7.3f}  {r2_prod:8.3f} {r2_31:9.3f}")

print(f"\nTotal time: {time.time() - t0:.1f}s")