"""
03 - Red Flag Signal Validation
================================
Validate rule-based red flag signals against actual growth rates.

Since BrickLink monthly sales data is sparse, this experiment focuses on:
1. theme_decay signal (uses theme growth rates from config)
2. Intrinsic red flags derived from set characteristics
3. Correlation of these signals with actual annual_growth_pct

Run with: python research/inversion/03_red_flag_signals.py
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.ml import InversionConfig
from config.value_investing import THEME_MULTIPLIERS, get_theme_annual_growth
from services.backtesting.red_flags import compute_theme_decay
from services.ml.growth_model import (
    _engineer_intrinsic_features,
    _load_training_data,
)

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "inversion"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

AVOID_THRESHOLD = 5.0

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

print("=" * 70)
print("RED FLAG SIGNAL VALIDATION")
print("=" * 70)

raw_df = _load_training_data(db)
target = raw_df["annual_growth_pct"].astype(float)
feat_df, theme_stats, subtheme_stats = _engineer_intrinsic_features(
    raw_df, training_target=target,
)

feat_df["actual_growth"] = target.values
feat_df["avoid"] = (target < AVOID_THRESHOLD).astype(int)

print(f"Sets: {len(feat_df)}")
print(f"Avoid class: {feat_df['avoid'].sum()} ({feat_df['avoid'].mean():.1%})")

# ---------------------------------------------------------------------------
# 2. Compute available red flag signals
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("COMPUTING RED FLAG SIGNALS")
print("=" * 70)

# Signal 1: Theme decay (from config growth rates)
feat_df["rf_theme_decay"] = feat_df["theme"].apply(compute_theme_decay)

# Signal 2: High price per part (expensive generic sets)
ppp = pd.to_numeric(feat_df.get("price_per_part", 0), errors="coerce").fillna(0)
feat_df["rf_expensive"] = np.where(
    ppp > 25, 90.0,
    np.where(ppp > 18, 70.0,
    np.where(ppp > 12, 50.0,
    np.where(ppp > 8, 30.0, 10.0)))
)

# Signal 3: Low minifig density (less collectible)
mfig_dens = pd.to_numeric(feat_df.get("minifig_density", 0), errors="coerce").fillna(0)
feat_df["rf_low_minifigs"] = np.where(
    mfig_dens < 0.2, 85.0,
    np.where(mfig_dens < 0.5, 65.0,
    np.where(mfig_dens < 1.0, 45.0,
    np.where(mfig_dens < 2.0, 25.0, 10.0)))
)

# Signal 4: Low subtheme track record
sub_loo = pd.to_numeric(feat_df.get("subtheme_loo", 0), errors="coerce").fillna(0)
feat_df["rf_weak_subtheme"] = np.where(
    sub_loo < 4, 90.0,
    np.where(sub_loo < 6, 70.0,
    np.where(sub_loo < 8, 50.0,
    np.where(sub_loo < 10, 30.0, 10.0)))
)

# Signal 5: Low theme Bayesian score
theme_bay = pd.to_numeric(feat_df.get("theme_bayes", 0), errors="coerce").fillna(0)
feat_df["rf_weak_theme"] = np.where(
    theme_bay < 8, 90.0,
    np.where(theme_bay < 10, 70.0,
    np.where(theme_bay < 12, 45.0,
    np.where(theme_bay < 14, 25.0, 10.0)))
)

# Signal 6: High RRP (overpriced sets harder to appreciate)
log_rrp = pd.to_numeric(feat_df.get("log_rrp", 0), errors="coerce").fillna(0)
rrp_usd = np.exp(log_rrp) / 100  # convert back to dollars
feat_df["rf_overpriced"] = np.where(
    rrp_usd > 200, 80.0,
    np.where(rrp_usd > 100, 60.0,
    np.where(rrp_usd > 50, 40.0,
    np.where(rrp_usd > 20, 20.0, 10.0)))
)

# Composite red flag score
rf_cols = ["rf_theme_decay", "rf_expensive", "rf_low_minifigs",
           "rf_weak_subtheme", "rf_weak_theme", "rf_overpriced"]
weights = [0.15, 0.15, 0.15, 0.20, 0.20, 0.15]

rf_matrix = feat_df[rf_cols].copy()
for col in rf_cols:
    rf_matrix[col] = pd.to_numeric(rf_matrix[col], errors="coerce").fillna(50.0)

feat_df["rf_composite"] = sum(
    rf_matrix[col] * w for col, w in zip(rf_cols, weights)
)

# Flag count (signals above 60)
feat_df["rf_flag_count"] = sum(
    (rf_matrix[col] >= 60).astype(int) for col in rf_cols
)

signal_coverage = {col: rf_matrix[col].notna().sum() for col in rf_cols}
print(f"\nSignal coverage:")
for col, n in signal_coverage.items():
    print(f"  {col:<25}: {n} / {len(feat_df)}")

# ---------------------------------------------------------------------------
# 3. Correlation with actual growth
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("RED FLAG CORRELATIONS WITH annual_growth_pct")
print("=" * 70)

all_signals = rf_cols + ["rf_composite", "rf_flag_count"]

print(f"\n{'Signal':<25} {'Corr w/Growth':>14} {'Corr w/Avoid':>14}")
print("-" * 58)
for col in all_signals:
    valid = feat_df[[col, "actual_growth", "avoid"]].dropna()
    if len(valid) < 20:
        print(f"{col:<25} {'N/A':>14} {'N/A':>14}")
        continue
    corr_growth = valid[col].corr(valid["actual_growth"])
    corr_avoid = valid[col].corr(valid["avoid"].astype(float))
    print(f"{col:<25} {corr_growth:>13.3f} {corr_avoid:>13.3f}")

# ---------------------------------------------------------------------------
# 4. Composite score thresholds vs actual avoid rate
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("COMPOSITE SCORE THRESHOLDS vs ACTUAL AVOID RATE")
print("=" * 70)

total_avoid = feat_df["avoid"].sum()
print(f"\n{'Threshold':>10} {'Flagged':>8} {'True Avoid':>11} {'Precision':>10} {'Recall':>10}")
print("-" * 55)

for threshold in [30, 40, 45, 50, 55, 60, 65, 70]:
    flagged = feat_df[feat_df["rf_composite"] >= threshold]
    n_flagged = len(flagged)
    if n_flagged > 0:
        n_true_avoid = flagged["avoid"].sum()
        precision = n_true_avoid / n_flagged
        recall = n_true_avoid / total_avoid if total_avoid > 0 else 0
    else:
        n_true_avoid = 0
        precision = 0
        recall = 0
    print(f"{threshold:>10} {n_flagged:>8} {n_true_avoid:>11} {precision:>9.1%} {recall:>9.1%}")

# ---------------------------------------------------------------------------
# 5. Flag count analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FLAG COUNT vs ACTUAL GROWTH")
print("=" * 70)

for count in range(0, 7):
    subset = feat_df[feat_df["rf_flag_count"] == count]
    if subset.empty:
        continue
    avg_growth = subset["actual_growth"].mean()
    pct_avoid = subset["avoid"].mean()
    print(f"  {count} flags: n={len(subset):>3}, avg_growth={avg_growth:>6.1f}%, pct_avoid={pct_avoid:>6.1%}")

# ---------------------------------------------------------------------------
# 6. Compare: signal-only vs ML-only vs combined
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SIGNAL-ONLY vs ML CLASSIFIER vs COMBINED")
print("=" * 70)

# Load ML predictions from experiment 02
ml_preds_path = RESULTS_DIR / "02_classifier_predictions.csv"
if ml_preds_path.exists():
    ml_df = pd.read_csv(ml_preds_path)

    # Merge
    ml_df["set_number"] = ml_df["set_number"].astype(str)
    feat_merge = feat_df[["set_number", "actual_growth", "avoid", "rf_composite"]].copy()
    feat_merge["set_number"] = feat_merge["set_number"].astype(str)
    compare = feat_merge.merge(
        ml_df[["set_number", "avoid_prob"]], on="set_number", how="inner"
    )

    # Normalize composite to 0-1
    rf_norm = compare["rf_composite"] / 100.0
    ml_prob = compare["avoid_prob"]
    y_true = compare["avoid"].values

    # Combined score
    compare["combined"] = 0.6 * ml_prob + 0.4 * rf_norm

    from sklearn.metrics import roc_auc_score

    approaches = {
        "Signal-only (composite)": rf_norm.values,
        "ML-only (GBM)": ml_prob.values,
        "Combined (0.6 ML + 0.4 RF)": compare["combined"].values,
    }

    print(f"\n{'Approach':<30} {'AUC':>8} {'P@50%':>8} {'R@50%':>8}")
    print("-" * 58)
    for name, scores in approaches.items():
        try:
            auc = roc_auc_score(y_true, scores)
        except ValueError:
            auc = 0.0
        preds = (scores >= 0.5).astype(int)
        n_flagged = preds.sum()
        if n_flagged > 0:
            precision = (preds & y_true).sum() / n_flagged
            recall = (preds & y_true).sum() / y_true.sum() if y_true.sum() > 0 else 0
        else:
            precision = 0.0
            recall = 0.0
        print(f"{name:<30} {auc:>7.3f} {precision:>7.1%} {recall:>7.1%}")

    # Detailed threshold comparison for combined
    print(f"\nCombined score thresholds:")
    print(f"{'Threshold':>10} {'Precision':>10} {'Recall':>10} {'N_flagged':>10}")
    print("-" * 45)
    for t in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        preds = (compare["combined"].values >= t).astype(int)
        n_flagged = preds.sum()
        if n_flagged > 0:
            precision = (preds & y_true).sum() / n_flagged
            recall = (preds & y_true).sum() / y_true.sum()
        else:
            precision = recall = 0.0
        print(f"{t:>10.1f} {precision:>10.1%} {recall:>10.1%} {n_flagged:>10}")
else:
    print("  (Run experiment 02 first to compare with ML classifier)")

# ---------------------------------------------------------------------------
# 7. Save results
# ---------------------------------------------------------------------------

output_cols = ["set_number", "title", "theme", "actual_growth", "avoid"] + rf_cols + ["rf_composite", "rf_flag_count"]
feat_df[output_cols].to_csv(RESULTS_DIR / "03_red_flag_scores.csv", index=False)

print(f"\nRed flag scores saved to {RESULTS_DIR / '03_red_flag_scores.csv'}")

db.close()
print("\nDone.")
