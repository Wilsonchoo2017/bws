"""
07 - BrickLink Ground Truth + Asymmetric Loss Validation
=========================================================
Compare classifier performance when trained on:
  A. BE annual_growth_pct (old target)
  B. BL annualized returns (new ground truth)
  C. BL + asymmetric sample weights (penalize severe losers)

Run with: python research/inversion/07_bl_ground_truth.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    fbeta_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "inversion"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

AVOID_THRESHOLD = 8.0  # match production threshold

# ---------------------------------------------------------------------------
# 0. Load data
# ---------------------------------------------------------------------------

print("=" * 70)
print("BL GROUND TRUTH + ASYMMETRIC LOSS VALIDATION")
print("=" * 70)

from db.pg.engine import get_engine
from services.ml.growth.classifier import (
    _build_classifier,
    _get_oof_probabilities,
    compute_avoid_sample_weights,
    make_avoid_labels,
)
from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
from services.ml.growth.model_selection import clip_outliers
from services.ml.pg_queries import load_bl_ground_truth, load_growth_training_data

engine = get_engine()

# Load BE data (full set)
df_raw = load_growth_training_data(engine)
y_be_all = df_raw["annual_growth_pct"].values.astype(float)
print(f"BE dataset: {len(df_raw)} sets")

# Load BL ground truth
bl_target = load_bl_ground_truth(engine)
print(f"BL ground truth: {len(bl_target)} sets")

# Feature engineering on full dataset
df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
    df_raw, training_target=pd.Series(y_be_all),
)
tier1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
X_raw = df_feat[tier1_candidates].copy()
for c in X_raw.columns:
    X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
fill_values = X_raw.median()
X_full = X_raw.fillna(fill_values)
X_full_clipped = clip_outliers(X_full)

# Filter to BL sets
set_numbers = df_feat["set_number"].values if "set_number" in df_feat.columns else df_raw["set_number"].values
bl_mask = np.array([sn in bl_target for sn in set_numbers])
y_bl = np.array([bl_target[sn] for sn in set_numbers[bl_mask]])
X_bl = X_full_clipped.values[bl_mask]
themes_bl = df_feat["theme"].values[bl_mask] if "theme" in df_feat.columns else None

# BE target for the same BL subset (for fair comparison)
y_be_subset = y_be_all[bl_mask]

print(f"\nBL subset: {len(y_bl)} sets")
print(f"  BL avoid (<{AVOID_THRESHOLD}%): {(y_bl < AVOID_THRESHOLD).sum()} ({(y_bl < AVOID_THRESHOLD).mean():.1%})")
print(f"  BE avoid (<{AVOID_THRESHOLD}%): {(y_be_subset < AVOID_THRESHOLD).sum()} ({(y_be_subset < AVOID_THRESHOLD).mean():.1%})")

# Tier breakdown for BL
print(f"\nBL tier breakdown:")
print(f"  Strong loser (<-15%): {(y_bl < -15).sum()}")
print(f"  Loser (-15% to -5%):  {((y_bl >= -15) & (y_bl < -5)).sum()}")
print(f"  Stagnant (-5% to 5%): {((y_bl >= -5) & (y_bl < 5)).sum()}")
print(f"  Neutral (5% to 20%):  {((y_bl >= 5) & (y_bl < 20)).sum()}")
print(f"  Performer (>=20%):    {(y_bl >= 20).sum()}")

# ---------------------------------------------------------------------------
# A. Baseline: classifier on BE target (same BL subset)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("A. BASELINE: Classifier on BE target (same BL subset)")
print("=" * 70)

y_avoid_be = make_avoid_labels(y_be_subset, AVOID_THRESHOLD)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

probs_be = cross_val_predict(
    _build_classifier(), StandardScaler().fit_transform(X_bl),
    y_avoid_be, cv=cv, method="predict_proba",
)[:, 1]

# ---------------------------------------------------------------------------
# B. BL ground truth classifier (no weights)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("B. BL GROUND TRUTH: Classifier on BL target (no weights)")
print("=" * 70)

y_avoid_bl = make_avoid_labels(y_bl, AVOID_THRESHOLD)

probs_bl = cross_val_predict(
    _build_classifier(), StandardScaler().fit_transform(X_bl),
    y_avoid_bl, cv=cv, method="predict_proba",
)[:, 1]

# ---------------------------------------------------------------------------
# C. BL + asymmetric weights
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("C. BL + ASYMMETRIC WEIGHTS")
print("=" * 70)

avoid_weights = compute_avoid_sample_weights(y_bl)
print(f"Weight distribution: 1.0={(avoid_weights == 1).sum()}, 2.0={(avoid_weights == 2).sum()}, 3.0={(avoid_weights == 3).sum()}")

# OOF with weights
probs_bl_w = _get_oof_probabilities(
    StandardScaler().fit_transform(X_bl),
    y_avoid_bl,
    sample_weight=avoid_weights,
)

# ---------------------------------------------------------------------------
# Compare all three
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("COMPARISON (all evaluated against BL ground truth labels)")
print("=" * 70)


def evaluate(probs, y_true, label, threshold=0.30):
    preds = (probs >= threshold).astype(int)
    auc = roc_auc_score(y_true, probs)
    rec = recall_score(y_true, preds, zero_division=0)
    prec = precision_score(y_true, preds, zero_division=0)
    f2 = fbeta_score(y_true, preds, beta=2, zero_division=0)
    fn = ((y_true == 1) & (preds == 0)).sum()
    return {"label": label, "auc": auc, "recall": rec, "precision": prec, "f2": f2, "fn": fn}


# Evaluate all against BL labels (ground truth)
results = [
    evaluate(probs_be, y_avoid_bl, "BE target (baseline)"),
    evaluate(probs_bl, y_avoid_bl, "BL target"),
    evaluate(probs_bl_w, y_avoid_bl, "BL + weights"),
]

print(f"\n{'Model':<25} {'AUC':>8} {'Recall':>8} {'Prec':>8} {'F2':>8} {'FN':>6}")
print("-" * 65)
for r in results:
    print(f"{r['label']:<25} {r['auc']:>7.4f} {r['recall']:>7.1%} {r['precision']:>7.1%} {r['f2']:>7.3f} {r['fn']:>6}")

# ---------------------------------------------------------------------------
# Per-tier FN analysis (does asymmetric weighting help severe losers?)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PER-TIER FALSE NEGATIVE ANALYSIS")
print("   Does asymmetric weighting reduce FN for severe losers?")
print("=" * 70)

tiers = [
    ("Strong loser (<-15%)", y_bl < -15),
    ("Loser (-15% to -5%)", (y_bl >= -15) & (y_bl < -5)),
    ("Stagnant (-5% to 5%)", (y_bl >= -5) & (y_bl < 5)),
]

threshold = 0.30
print(f"\n{'Tier':<25} {'N':>5} | {'BE FN':>7} {'BL FN':>7} {'BL+W FN':>8} | {'BE Miss':>8} {'BL Miss':>8} {'BL+W Miss':>10}")
print("-" * 95)

for tier_label, mask in tiers:
    n = mask.sum()
    if n == 0:
        continue
    be_fn = ((mask) & (probs_be < threshold)).sum()
    bl_fn = ((mask) & (probs_bl < threshold)).sum()
    blw_fn = ((mask) & (probs_bl_w < threshold)).sum()
    print(f"{tier_label:<25} {n:>5} | {be_fn:>7} {bl_fn:>7} {blw_fn:>8} | {be_fn/n:>7.0%} {bl_fn/n:>7.0%} {blw_fn/n:>9.0%}")

# ---------------------------------------------------------------------------
# Per-theme analysis
# ---------------------------------------------------------------------------

if themes_bl is not None:
    print("\n" + "=" * 70)
    print("PER-THEME ANALYSIS (BL+weights, threshold=0.30)")
    print("=" * 70)

    preds_blw = (probs_bl_w >= threshold).astype(int)
    unique_themes = pd.Series(themes_bl).value_counts()

    print(f"\n{'Theme':<22} {'N':>5} {'Avoid':>6} {'FN':>5} {'Miss%':>7} {'AUC':>7}")
    print("-" * 58)

    for theme in unique_themes.index:
        mask = themes_bl == theme
        n = mask.sum()
        n_avoid = y_avoid_bl[mask].sum()
        if n < 5 or n_avoid < 2 or n_avoid == n:
            continue
        fn = ((y_avoid_bl[mask] == 1) & (preds_blw[mask] == 0)).sum()
        miss = fn / n_avoid if n_avoid > 0 else 0
        try:
            t_auc = roc_auc_score(y_avoid_bl[mask], probs_bl_w[mask])
        except ValueError:
            t_auc = 0.0
        flag = " <--" if miss > 0.30 else ""
        print(f"{str(theme)[:21]:<22} {n:>5} {n_avoid:>6} {fn:>5} {miss:>6.0%} {t_auc:>6.3f}{flag}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

best = results[-1]  # BL + weights
baseline = results[0]  # BE

print(f"""
Ground truth: BrickLink annualized returns ({len(y_bl)} retired sets)
Avoid threshold: {AVOID_THRESHOLD}% annual growth
Avoid class: {y_avoid_bl.sum()} / {len(y_avoid_bl)} ({y_avoid_bl.mean():.1%})

BASELINE (BE target):
  AUC={baseline['auc']:.4f}, Recall={baseline['recall']:.1%}, FN={baseline['fn']}

BEST (BL + asymmetric weights):
  AUC={best['auc']:.4f}, Recall={best['recall']:.1%}, FN={best['fn']}
  Delta: AUC {best['auc']-baseline['auc']:+.4f}, FN {best['fn']-baseline['fn']:+d}
""")

print("Done.")
