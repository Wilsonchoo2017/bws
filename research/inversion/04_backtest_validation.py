"""
04 - Backtest Validation: Inversion Filter vs Unfiltered Portfolio
==================================================================
LOO cross-validated comparison of portfolio strategies:
  A) Buy everything (baseline)
  B) Buy top 50% by growth prediction (current growth model)
  C) Buy with inversion filter (exclude flagged sets)
  D) Combined: growth top 50% + inversion filter

Uses annual_growth_pct from BrickEconomy as the ground truth.

Run with: python research/inversion/04_backtest_validation.py
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.pipeline import Pipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.ml.growth_model import (
    TIER1_FEATURES,
    _engineer_intrinsic_features,
    _load_training_data,
)

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "inversion"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

AVOID_THRESHOLD = 5.0

# ---------------------------------------------------------------------------
# 1. Load data and engineer features
# ---------------------------------------------------------------------------

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

print("=" * 70)
print("BACKTEST VALIDATION: Inversion Filter vs Unfiltered Portfolio")
print("=" * 70)

raw_df = _load_training_data(db)
target = raw_df["annual_growth_pct"].astype(float)
feat_df, theme_stats, subtheme_stats = _engineer_intrinsic_features(
    raw_df, training_target=target,
)

feature_cols = [c for c in TIER1_FEATURES if c in feat_df.columns]
for col in feature_cols:
    feat_df[col] = pd.to_numeric(feat_df[col], errors="coerce")

X = feat_df[feature_cols].fillna(feat_df[feature_cols].median())
y_growth = target.values
y_avoid = (target < AVOID_THRESHOLD).astype(int).values

print(f"Sets: {len(feat_df)}, Features: {len(feature_cols)}")
print(f"Avoid class: {y_avoid.sum()} ({y_avoid.mean():.1%})")
print(f"Baseline avg growth: {y_growth.mean():.1f}%")

# ---------------------------------------------------------------------------
# 2. Generate LOO predictions for both models
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("GENERATING LOO PREDICTIONS")
print("=" * 70)

# Inversion classifier (avoid probability)
inv_model = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("model", HistGradientBoostingClassifier(
        max_iter=200, max_depth=4, learning_rate=0.05,
        class_weight="balanced", random_state=42,
    )),
])

loo = LeaveOneOut()
avoid_probs = cross_val_predict(inv_model, X.values, y_avoid, cv=loo, method="predict_proba")[:, 1]
print(f"Inversion predictions: {len(avoid_probs)} sets")

# Growth regression model (predicted growth)
growth_model = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("model", GradientBoostingRegressor(
        n_estimators=250, max_depth=4, learning_rate=0.02,
        min_samples_leaf=6, random_state=42,
    )),
])

growth_preds = cross_val_predict(growth_model, X.values, y_growth, cv=loo)
print(f"Growth predictions: {len(growth_preds)} sets")

# ---------------------------------------------------------------------------
# 3. Strategy comparison
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("STRATEGY COMPARISON")
print("=" * 70)

strategies = {}

# A: Buy everything
strategies["A_buy_all"] = np.ones(len(feat_df), dtype=bool)

# B: Growth model top 50%
growth_median = np.median(growth_preds)
strategies["B_growth_top50"] = growth_preds >= growth_median

# C: Inversion filter at various thresholds
for t in [40, 50, 60, 70]:
    strategies[f"C_inv_filter_{t}"] = avoid_probs < (t / 100)

# D: Combined (growth top 50% + inversion filter)
for t in [40, 50, 60, 70]:
    strategies[f"D_combined_{t}"] = (growth_preds >= growth_median) & (avoid_probs < (t / 100))

print(f"\n{'Strategy':<22} {'N':>5} {'AvgGrw':>8} {'MedGrw':>8} "
      f"{'%<5%':>7} {'Min':>7} {'Sharpe':>8}")
print("-" * 72)

summary_rows = []
for name, mask in strategies.items():
    rets = y_growth[mask]
    n = len(rets)
    if n == 0:
        continue

    mean_g = np.mean(rets)
    med_g = np.median(rets)
    pct_avoid = np.mean(rets < AVOID_THRESHOLD)
    min_g = np.min(rets)
    std_g = np.std(rets)
    sharpe = mean_g / std_g if std_g > 0 else 0

    print(f"{name:<22} {n:>5} {mean_g:>7.1f}% {med_g:>7.1f}% "
          f"{pct_avoid:>6.1%} {min_g:>6.1f}% {sharpe:>8.2f}")

    summary_rows.append({
        "strategy": name,
        "n_sets": n,
        "avg_growth": mean_g,
        "median_growth": med_g,
        "pct_below_5": pct_avoid,
        "min_growth": min_g,
        "sharpe_like": sharpe,
    })

# ---------------------------------------------------------------------------
# 4. Improvement analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("IMPROVEMENT vs BASELINE")
print("=" * 70)

baseline_mean = y_growth.mean()
baseline_pct_avoid = (y_growth < AVOID_THRESHOLD).mean()

print(f"\nBaseline: {len(y_growth)} sets, avg growth {baseline_mean:.1f}%, "
      f"{baseline_pct_avoid:.1%} below {AVOID_THRESHOLD}%")

for name, mask in strategies.items():
    if name == "A_buy_all":
        continue
    rets = y_growth[mask]
    if len(rets) == 0:
        continue
    excluded = y_growth[~mask]
    growth_lift = np.mean(rets) - baseline_mean
    avoided_duds = np.mean(excluded < AVOID_THRESHOLD) if len(excluded) > 0 else 0
    pct_remaining = len(rets) / len(y_growth)

    print(f"  {name:<22}: growth +{growth_lift:>+5.1f}%, "
          f"kept {pct_remaining:.0%} of sets, "
          f"{avoided_duds:.0%} of excluded were duds")

# ---------------------------------------------------------------------------
# 5. Head-to-head: Growth model vs Inversion filter
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("HEAD-TO-HEAD: What does inversion catch that growth model misses?")
print("=" * 70)

# Sets that growth model keeps (top 50%) but inversion flags (>60%)
growth_keeps = growth_preds >= growth_median
inv_flags = avoid_probs >= 0.6

caught_by_inv = growth_keeps & inv_flags
n_caught = caught_by_inv.sum()
if n_caught > 0:
    caught_growth = y_growth[caught_by_inv]
    print(f"\nSets growth model keeps but inversion flags: {n_caught}")
    print(f"  Avg actual growth: {caught_growth.mean():.1f}%")
    print(f"  % actually avoid:  {(caught_growth < AVOID_THRESHOLD).mean():.0%}")

    print(f"\n  {'Set':<10} {'Title':<28} {'GrwPred':>8} {'AvoidP':>7} {'Actual':>7}")
    print("  " + "-" * 65)
    caught_df = feat_df.iloc[np.where(caught_by_inv)[0]][["set_number", "title"]].copy()
    caught_df["growth_pred"] = growth_preds[caught_by_inv]
    caught_df["avoid_prob"] = avoid_probs[caught_by_inv]
    caught_df["actual"] = y_growth[caught_by_inv]
    caught_df = caught_df.sort_values("actual")
    for _, row in caught_df.iterrows():
        title = str(row["title"])[:27]
        print(f"  {row['set_number']:<10} {title:<28} {row['growth_pred']:>7.1f}% "
              f"{row['avoid_prob']:>6.0%} {row['actual']:>6.1f}%")

# Sets inversion misses (low prob) but are actually bad
inv_misses = (avoid_probs < 0.4) & (y_growth < AVOID_THRESHOLD)
n_missed = inv_misses.sum()
if n_missed > 0:
    print(f"\nSets inversion MISSES (prob<40% but actually avoid): {n_missed}")
    missed_df = feat_df.iloc[np.where(inv_misses)[0]][["set_number", "title", "theme"]].copy()
    missed_df["avoid_prob"] = avoid_probs[inv_misses]
    missed_df["actual"] = y_growth[inv_misses]
    missed_df = missed_df.sort_values("actual")
    for _, row in missed_df.head(10).iterrows():
        title = str(row["title"])[:27]
        print(f"  {row['set_number']:<10} {title:<28} {row['theme']:<15} "
              f"prob={row['avoid_prob']:.0%} actual={row['actual']:.1f}%")

# ---------------------------------------------------------------------------
# 6. Save results
# ---------------------------------------------------------------------------

summary_df = pd.DataFrame(summary_rows)
summary_df.to_csv(RESULTS_DIR / "04_strategy_comparison.csv", index=False)

pred_df = feat_df[["set_number", "title", "theme"]].copy()
pred_df["growth_pred"] = growth_preds
pred_df["avoid_prob"] = avoid_probs
pred_df["actual_growth"] = y_growth
pred_df["actually_avoid"] = y_avoid
pred_df.to_csv(RESULTS_DIR / "04_per_set_predictions.csv", index=False)

print(f"\nResults saved to {RESULTS_DIR}")

db.close()
print("\nDone.")
