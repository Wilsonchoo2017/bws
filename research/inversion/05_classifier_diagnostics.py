"""
05 - Classifier Diagnostics: Where Does AUC=0.85 Fail?
=======================================================
Comprehensive diagnostics for the avoid classifier + new feature evaluation.

Diagnostics (from ML improvement brainstorm):
  1. False negative deep-dive: which losers does the classifier miss?
  2. Calibration curve: is P(avoid) well-calibrated?
  3. Per-theme AUC: does the classifier fail on specific themes?
  4. Threshold sensitivity: is 5% the right loser cutoff?
  5. Temporal drift: does performance degrade on recent cohorts?

New feature evaluation (from BrickTalk gap analysis):
  6. Shelf life months (short shelf life = bullish)
  7. Retire quarter (July vs December retirement)
  8. Retires before Q4 (no Black Friday discounting)

Run with: python research/inversion/05_classifier_diagnostics.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import (
    GroupKFold,
    RepeatedStratifiedKFold,
    StratifiedKFold,
    cross_val_predict,
)
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "inversion"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

AVOID_THRESHOLD = 5.0

# ---------------------------------------------------------------------------
# 0. Load data via production pipeline
# ---------------------------------------------------------------------------

print("=" * 70)
print("CLASSIFIER DIAGNOSTICS (1701-set production pipeline)")
print("=" * 70)

from db.pg.engine import get_engine
from services.ml.growth.classifier import _build_classifier, make_avoid_labels
from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
from services.ml.growth.model_selection import clip_outliers, compute_recency_weights
from services.ml.pg_queries import load_growth_training_data

engine = get_engine()
df_raw = load_growth_training_data(engine)
print(f"Loaded {len(df_raw)} sets")

y_all = df_raw["annual_growth_pct"].values.astype(float)
y_avoid = make_avoid_labels(y_all, AVOID_THRESHOLD)

df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
    df_raw, training_target=pd.Series(y_all),
)

# Select features that exist
tier1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
X_raw = df_feat[tier1_candidates].copy()
for c in X_raw.columns:
    X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
fill_values = X_raw.median()
X = X_raw.fillna(fill_values)
X_clipped = clip_outliers(X)

print(f"Features: {len(tier1_candidates)}")
print(f"Avoid class: {y_avoid.sum()} ({y_avoid.mean():.1%})")

# Temporal groups
year_retired = pd.to_numeric(df_raw.get("year_retired"), errors="coerce").values

# ---------------------------------------------------------------------------
# 1. False Negative Deep-Dive
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("1. FALSE NEGATIVE DEEP-DIVE")
print("   Which losers does the classifier miss?")
print("=" * 70)

# Cross-validated predictions
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_clipped.values)

avoid_probs = cross_val_predict(
    _build_classifier(), X_scaled, y_avoid, cv=cv, method="predict_proba",
)[:, 1]

# False negatives: actually avoid but low P(avoid)
fn_mask = (y_avoid == 1) & (avoid_probs < 0.3)
fn_df = df_feat.iloc[np.where(fn_mask)[0]][["set_number", "title", "theme", "subtheme"]].copy()
fn_df["avoid_prob"] = avoid_probs[fn_mask]
fn_df["actual_growth"] = y_all[fn_mask]
fn_df = fn_df.sort_values("actual_growth")

print(f"\nFalse negatives (actual loser, P(avoid) < 30%): {fn_mask.sum()} / {y_avoid.sum()}")
print(f"\n{'Set':<10} {'Title':<28} {'Theme':<18} {'P(av)':>6} {'Growth':>7}")
print("-" * 75)
for _, row in fn_df.head(20).iterrows():
    title = str(row["title"])[:27]
    theme = str(row["theme"])[:17]
    print(f"{row['set_number']:<10} {title:<28} {theme:<18} {row['avoid_prob']:>5.0%} {row['actual_growth']:>6.1f}%")

# Theme distribution of false negatives vs all losers
fn_themes = fn_df["theme"].value_counts()
all_loser_themes = df_feat.loc[y_avoid == 1, "theme"].value_counts()
print(f"\nTheme concentration of missed losers:")
print(f"{'Theme':<25} {'Missed':>7} {'All Losers':>11} {'Miss Rate':>10}")
print("-" * 58)
for theme in fn_themes.head(10).index:
    n_missed = fn_themes.get(theme, 0)
    n_total = all_loser_themes.get(theme, 0)
    miss_rate = n_missed / n_total if n_total > 0 else 0
    print(f"{str(theme)[:24]:<25} {n_missed:>7} {n_total:>11} {miss_rate:>9.0%}")

# False positives: not avoid but high P(avoid)
fp_mask = (y_avoid == 0) & (avoid_probs > 0.7)
fp_df = df_feat.iloc[np.where(fp_mask)[0]][["set_number", "title", "theme"]].copy()
fp_df["avoid_prob"] = avoid_probs[fp_mask]
fp_df["actual_growth"] = y_all[fp_mask]
fp_df = fp_df.sort_values("actual_growth", ascending=False)

print(f"\nFalse positives (not loser, P(avoid) > 70%): {fp_mask.sum()} / {(1 - y_avoid).sum()}")
print(f"  These are missed opportunities (good sets flagged as bad).")
print(f"\n{'Set':<10} {'Title':<28} {'Theme':<18} {'P(av)':>6} {'Growth':>7}")
print("-" * 75)
for _, row in fp_df.head(15).iterrows():
    title = str(row["title"])[:27]
    theme = str(row["theme"])[:17]
    print(f"{row['set_number']:<10} {title:<28} {theme:<18} {row['avoid_prob']:>5.0%} {row['actual_growth']:>6.1f}%")

# ---------------------------------------------------------------------------
# 2. Calibration Curve
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("2. CALIBRATION CURVE")
print("   Is P(avoid) = 60% actually 60% losers?")
print("=" * 70)

n_bins = 10
bin_edges = np.linspace(0, 1, n_bins + 1)
print(f"\n{'Bin':>12} {'N':>6} {'Predicted':>10} {'Actual':>10} {'Gap':>8}")
print("-" * 50)
for i in range(n_bins):
    lo, hi = bin_edges[i], bin_edges[i + 1]
    mask = (avoid_probs >= lo) & (avoid_probs < hi)
    if mask.sum() == 0:
        continue
    pred_mean = avoid_probs[mask].mean()
    actual_mean = y_avoid[mask].mean()
    gap = actual_mean - pred_mean
    print(f"[{lo:.1f}, {hi:.1f}){mask.sum():>6} {pred_mean:>9.1%} {actual_mean:>9.1%} {gap:>+7.1%}")

brier = brier_score_loss(y_avoid, avoid_probs)
print(f"\nBrier score: {brier:.4f} (lower = better calibrated, random = 0.25)")

auc = roc_auc_score(y_avoid, avoid_probs)
print(f"ROC AUC:     {auc:.4f}")

# ---------------------------------------------------------------------------
# 3. Per-Theme AUC Breakdown
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("3. PER-THEME AUC BREAKDOWN")
print("   Does the classifier fail on specific themes?")
print("=" * 70)

themes = df_feat["theme"].values
unique_themes = pd.Series(themes).value_counts()
# Only compute AUC for themes with sufficient samples (n >= 10 and at least 2 classes)
print(f"\n{'Theme':<25} {'N':>5} {'N_avoid':>8} {'AUC':>8} {'Avg P(av)':>10}")
print("-" * 60)

theme_aucs = []
for theme in unique_themes.index:
    mask = themes == theme
    n = mask.sum()
    n_avoid = y_avoid[mask].sum()
    if n < 10 or n_avoid < 2 or n_avoid == n:
        continue
    try:
        theme_auc = roc_auc_score(y_avoid[mask], avoid_probs[mask])
    except ValueError:
        continue
    avg_prob = avoid_probs[mask].mean()
    theme_aucs.append((theme, n, n_avoid, theme_auc, avg_prob))

theme_aucs.sort(key=lambda x: x[3])
for theme, n, n_avoid, theme_auc, avg_prob in theme_aucs:
    flag = " <-- WEAK" if theme_auc < 0.65 else ""
    print(f"{str(theme)[:24]:<25} {n:>5} {n_avoid:>8} {theme_auc:>7.3f} {avg_prob:>9.1%}{flag}")

weak = [t for t in theme_aucs if t[3] < 0.65]
strong = [t for t in theme_aucs if t[3] >= 0.85]
print(f"\nWeak themes (AUC < 0.65): {len(weak)}")
print(f"Strong themes (AUC >= 0.85): {len(strong)}")

# ---------------------------------------------------------------------------
# 4. Threshold Sensitivity
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("4. THRESHOLD SENSITIVITY")
print("   Is 5% the right loser cutoff?")
print("=" * 70)

print(f"\n{'Threshold':>10} {'N_avoid':>8} {'%avoid':>8} {'AUC':>8} {'Brier':>8} {'P@50':>8} {'R@50':>8}")
print("-" * 66)

for threshold in [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0]:
    y_t = make_avoid_labels(y_all, threshold)
    n_avoid_t = y_t.sum()
    pct_avoid = y_t.mean()

    if n_avoid_t < 5 or n_avoid_t == len(y_t):
        continue

    # Re-run CV with this threshold
    probs_t = cross_val_predict(
        _build_classifier(), X_scaled, y_t,
        cv=StratifiedKFold(5, shuffle=True, random_state=42),
        method="predict_proba",
    )[:, 1]

    try:
        auc_t = roc_auc_score(y_t, probs_t)
    except ValueError:
        auc_t = 0.0
    brier_t = brier_score_loss(y_t, probs_t)

    pred_50 = (probs_t >= 0.5).astype(int)
    n_flagged = pred_50.sum()
    if n_flagged > 0:
        prec_50 = (pred_50 & y_t).sum() / n_flagged
        rec_50 = (pred_50 & y_t).sum() / n_avoid_t
    else:
        prec_50 = rec_50 = 0.0

    print(f"{threshold:>9.0f}% {n_avoid_t:>8} {pct_avoid:>7.1%} {auc_t:>7.3f} {brier_t:>7.4f} {prec_50:>7.1%} {rec_50:>7.1%}")

# ---------------------------------------------------------------------------
# 5. Temporal Drift Check
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("5. TEMPORAL DRIFT CHECK")
print("   Does classifier performance degrade on recent cohorts?")
print("=" * 70)

yr_valid = np.isfinite(year_retired)
unique_years = sorted(set(year_retired[yr_valid].astype(int)))
print(f"Available retirement years: {unique_years}")

# Walk-forward: train on all years < Y, test on year Y
print(f"\n{'Test Year':>10} {'N_test':>7} {'N_avoid':>8} {'AUC':>8} {'Precision':>10} {'Recall':>10}")
print("-" * 58)

for test_year in unique_years:
    if test_year < min(unique_years) + 2:
        continue  # need at least 2 years of training data

    train_mask = yr_valid & (year_retired < test_year)
    test_mask = yr_valid & (year_retired == test_year)

    if train_mask.sum() < 30 or test_mask.sum() < 10:
        continue

    n_avoid_test = y_avoid[test_mask].sum()
    if n_avoid_test < 2 or n_avoid_test == test_mask.sum():
        continue

    s = StandardScaler()
    X_tr = s.fit_transform(X_clipped.values[train_mask])
    X_te = s.transform(X_clipped.values[test_mask])

    clf = _build_classifier()
    clf.fit(X_tr, y_avoid[train_mask])
    probs_te = clf.predict_proba(X_te)[:, 1]
    preds_te = (probs_te >= 0.5).astype(int)

    try:
        auc_te = roc_auc_score(y_avoid[test_mask], probs_te)
    except ValueError:
        auc_te = 0.0

    n_flagged = preds_te.sum()
    if n_flagged > 0:
        prec = (preds_te & y_avoid[test_mask]).sum() / n_flagged
        rec = (preds_te & y_avoid[test_mask]).sum() / n_avoid_test
    else:
        prec = rec = 0.0

    print(f"{test_year:>10} {test_mask.sum():>7} {n_avoid_test:>8} {auc_te:>7.3f} {prec:>9.1%} {rec:>9.1%}")

# ---------------------------------------------------------------------------
# 6. New Feature Analysis: Shelf Life
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("6. NEW FEATURE: shelf_life_months")
print("   Short shelf life = bullish (BrickTalk #1 signal)")
print("=" * 70)

shelf = pd.to_numeric(df_feat.get("shelf_life_months"), errors="coerce")
shelf_valid = shelf.notna()
print(f"Coverage: {shelf_valid.sum()} / {len(df_feat)} ({shelf_valid.mean():.1%})")

if shelf_valid.sum() > 50:
    sl = shelf[shelf_valid].values
    gr = y_all[shelf_valid]
    av = y_avoid[shelf_valid]
    corr_growth = np.corrcoef(sl, gr)[0, 1]
    corr_avoid = np.corrcoef(sl, av.astype(float))[0, 1]
    print(f"Correlation with growth: {corr_growth:.3f}")
    print(f"Correlation with avoid:  {corr_avoid:.3f}")

    # Bin analysis
    bins = [0, 12, 18, 24, 36, 48, 999]
    labels = ["<1yr", "1-1.5yr", "1.5-2yr", "2-3yr", "3-4yr", "4yr+"]
    shelf_bins = pd.cut(shelf[shelf_valid], bins=bins, labels=labels)
    print(f"\n{'Shelf Life':<12} {'N':>5} {'Avg Growth':>11} {'%Avoid':>8}")
    print("-" * 40)
    for label in labels:
        mask = shelf_bins == label
        if mask.sum() == 0:
            continue
        avg_g = gr[mask.values].mean()
        pct_av = av[mask.values].mean()
        print(f"{label:<12} {mask.sum():>5} {avg_g:>10.1f}% {pct_av:>7.1%}")
else:
    print("  Insufficient coverage for analysis")

# ---------------------------------------------------------------------------
# 7. New Feature Analysis: Retire Quarter
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("7. NEW FEATURE: retire_quarter + retires_before_q4")
print("   July retirement = no Black Friday = less supply flooding")
print("=" * 70)

rq = pd.to_numeric(df_feat.get("retire_quarter"), errors="coerce")
rq_valid = rq.notna()
print(f"Coverage: {rq_valid.sum()} / {len(df_feat)} ({rq_valid.mean():.1%})")

if rq_valid.sum() > 50:
    print(f"\n{'Quarter':>8} {'N':>5} {'Avg Growth':>11} {'%Avoid':>8}")
    print("-" * 36)
    for q in [1, 2, 3, 4]:
        mask = rq == q
        if mask.sum() == 0:
            continue
        avg_g = y_all[mask.values].mean()
        pct_av = y_avoid[mask.values].mean()
        print(f"      Q{q} {mask.sum():>5} {avg_g:>10.1f}% {pct_av:>7.1%}")

    rb4 = pd.to_numeric(df_feat.get("retires_before_q4"), errors="coerce")
    if rb4.notna().sum() > 0:
        pre = rb4 == 1
        post = rb4 == 0
        if pre.sum() > 0 and post.sum() > 0:
            print(f"\n  Retires before Q4: n={pre.sum()}, avg growth={y_all[pre.values].mean():.1f}%, avoid={y_avoid[pre.values].mean():.1%}")
            print(f"  Retires in Q4:     n={post.sum()}, avg growth={y_all[post.values].mean():.1f}%, avoid={y_avoid[post.values].mean():.1%}")

# ---------------------------------------------------------------------------
# 8. Avoid-Class Boundary Analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("8. DECISION BOUNDARY ANALYSIS")
print("   Sets near P(avoid) = 0.4-0.6 (the uncertainty zone)")
print("=" * 70)

boundary_mask = (avoid_probs >= 0.35) & (avoid_probs <= 0.65)
n_boundary = boundary_mask.sum()
boundary_growth = y_all[boundary_mask]
boundary_avoid = y_avoid[boundary_mask]

print(f"Sets in uncertainty zone (P=0.35-0.65): {n_boundary} ({n_boundary / len(y_all):.1%})")
print(f"  Avg growth: {boundary_growth.mean():.1f}%")
print(f"  Actually avoid: {boundary_avoid.mean():.1%}")
print(f"  Growth std: {boundary_growth.std():.1f}% (vs overall {y_all.std():.1f}%)")

# Feature comparison: boundary vs confident
confident_good = avoid_probs < 0.2
confident_bad = avoid_probs > 0.8

compare_feats = ["shelf_life_months", "retire_quarter", "price_per_part",
                 "mfigs", "theme_bayes", "subtheme_loo", "log_rrp",
                 "rating_value", "log_reviews", "usd_vs_mean"]
compare_feats = [f for f in compare_feats if f in X.columns]

print(f"\nFeature means: Confident Good vs Boundary vs Confident Bad")
print(f"{'Feature':<22} {'Good (<0.2)':>12} {'Boundary':>12} {'Bad (>0.8)':>12}")
print("-" * 62)
for feat in compare_feats:
    vals = X[feat].values
    g = vals[confident_good].mean() if confident_good.sum() > 0 else float("nan")
    b = vals[boundary_mask].mean() if boundary_mask.sum() > 0 else float("nan")
    d = vals[confident_bad].mean() if confident_bad.sum() > 0 else float("nan")
    print(f"{feat:<22} {g:>12.2f} {b:>12.2f} {d:>12.2f}")

# ---------------------------------------------------------------------------
# 9. Impact of New Features on Classifier AUC
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("9. ABLATION: NEW FEATURES IMPACT ON CLASSIFIER AUC")
print("=" * 70)

new_features = ["shelf_life_months", "retire_quarter", "retires_before_q4"]
new_available = [f for f in new_features if f in X.columns]

if new_available:
    # Baseline: original features without new ones
    old_features = [f for f in tier1_candidates if f not in new_features]
    X_old = X_raw[old_features].fillna(X_raw[old_features].median())
    X_old_clipped = clip_outliers(X_old)

    s_old = StandardScaler()
    X_old_s = s_old.fit_transform(X_old_clipped.values)

    probs_old = cross_val_predict(
        _build_classifier(), X_old_s, y_avoid,
        cv=StratifiedKFold(5, shuffle=True, random_state=42),
        method="predict_proba",
    )[:, 1]
    auc_old = roc_auc_score(y_avoid, probs_old)
    brier_old = brier_score_loss(y_avoid, probs_old)

    # New: all features including new ones
    probs_new = cross_val_predict(
        _build_classifier(), X_scaled, y_avoid,
        cv=StratifiedKFold(5, shuffle=True, random_state=42),
        method="predict_proba",
    )[:, 1]
    auc_new = roc_auc_score(y_avoid, probs_new)
    brier_new = brier_score_loss(y_avoid, probs_new)

    print(f"\n{'Model':<25} {'N_feat':>7} {'AUC':>8} {'Brier':>8}")
    print("-" * 52)
    print(f"{'Baseline (no lifecycle)':<25} {len(old_features):>7} {auc_old:>7.4f} {brier_old:>7.4f}")
    print(f"{'+ lifecycle features':<25} {len(tier1_candidates):>7} {auc_new:>7.4f} {brier_new:>7.4f}")
    print(f"{'Delta':<25} {'+' + str(len(new_available)):>7} {auc_new - auc_old:>+7.4f} {brier_new - brier_old:>+7.4f}")

    # Per-new-feature marginal contribution
    print(f"\nMarginal contribution of each new feature:")
    for feat in new_available:
        feats_minus_one = [f for f in tier1_candidates if f != feat]
        X_m1 = X_raw[feats_minus_one].fillna(X_raw[feats_minus_one].median())
        X_m1_c = clip_outliers(X_m1)
        s_m1 = StandardScaler()
        X_m1_s = s_m1.fit_transform(X_m1_c.values)
        probs_m1 = cross_val_predict(
            _build_classifier(), X_m1_s, y_avoid,
            cv=StratifiedKFold(5, shuffle=True, random_state=42),
            method="predict_proba",
        )[:, 1]
        auc_m1 = roc_auc_score(y_avoid, probs_m1)
        delta = auc_new - auc_m1
        print(f"  {feat:<25}: AUC without={auc_m1:.4f}, delta={delta:>+.4f}")
else:
    print("  New features not available in dataset")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"""
Dataset: {len(df_raw)} sets, {y_avoid.sum()} avoid ({y_avoid.mean():.1%})
Overall AUC: {roc_auc_score(y_avoid, avoid_probs):.4f}
Brier score: {brier_score_loss(y_avoid, avoid_probs):.4f}
False negatives (P<0.3, actually avoid): {fn_mask.sum()} ({fn_mask.sum() / y_avoid.sum():.1%} of all losers)
False positives (P>0.7, not avoid): {fp_mask.sum()} ({fp_mask.sum() / (1 - y_avoid).sum():.1%} of all keepers)
Uncertainty zone (P=0.35-0.65): {n_boundary} sets ({n_boundary / len(y_all):.1%})
New features available: {', '.join(new_available) if new_available else 'none'}
""")

# Save detailed results
results = df_feat[["set_number", "title", "theme", "subtheme"]].copy()
results["actual_growth"] = y_all
results["is_avoid"] = y_avoid
results["avoid_prob"] = avoid_probs
results["shelf_life_months"] = df_feat.get("shelf_life_months")
results["retire_quarter"] = df_feat.get("retire_quarter")
results["retires_before_q4"] = df_feat.get("retires_before_q4")
results.to_csv(RESULTS_DIR / "05_diagnostics.csv", index=False)

print(f"Detailed results saved to {RESULTS_DIR / '05_diagnostics.csv'}")
print("\nDone.")
