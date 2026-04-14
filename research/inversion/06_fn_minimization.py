"""
06 - False Negative Minimization: Threshold, F2 Optuna, scale_pos_weight
========================================================================
Validate changes to aggressively reduce classifier false negatives.

Sections:
  A. Threshold sweep: recall/precision/F2/FN at thresholds [0.20..0.50]
  B. F2-tuned Optuna vs AUC-tuned Optuna
  C. scale_pos_weight sensitivity [1.5, 2.0, 3.0, 5.0]
  D. Per-theme FN analysis after changes
  E. Downstream impact on hurdle model predictions

Run with: python research/inversion/06_fn_minimization.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss,
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

AVOID_THRESHOLD = 5.0

# ---------------------------------------------------------------------------
# 0. Load data (same setup as 05_classifier_diagnostics.py)
# ---------------------------------------------------------------------------

print("=" * 70)
print("FALSE NEGATIVE MINIMIZATION EXPERIMENTS")
print("=" * 70)

from db.pg.engine import get_engine
from services.ml.growth.classifier import _build_classifier, make_avoid_labels
from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
from services.ml.growth.model_selection import clip_outliers

engine = get_engine()

from services.ml.pg_queries import load_growth_training_data

df_raw = load_growth_training_data(engine)
print(f"Loaded {len(df_raw)} sets")

y_all = df_raw["annual_growth_pct"].values.astype(float)
y_avoid = make_avoid_labels(y_all, AVOID_THRESHOLD)

df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
    df_raw, training_target=pd.Series(y_all),
)

tier1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
X_raw = df_feat[tier1_candidates].copy()
for c in X_raw.columns:
    X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
fill_values = X_raw.median()
X = X_raw.fillna(fill_values)
X_clipped = clip_outliers(X)

print(f"Features: {len(tier1_candidates)}")
print(f"Avoid class: {y_avoid.sum()} ({y_avoid.mean():.1%})")

# Cross-validated predictions (baseline)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_clipped.values)

baseline_probs = cross_val_predict(
    _build_classifier(), X_scaled, y_avoid, cv=cv, method="predict_proba",
)[:, 1]

themes = df_feat["theme"].values

# ---------------------------------------------------------------------------
# A. Threshold Sweep
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("A. THRESHOLD SWEEP")
print("   Find threshold that maximizes recall while keeping precision >= 40%")
print("=" * 70)

thresholds = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

print(f"\n{'Thresh':>7} {'Recall':>8} {'Prec':>8} {'F2':>8} {'FN':>6} {'FP':>6} {'Flagged':>8}")
print("-" * 60)

best_threshold = 0.5
best_f2 = 0.0

for t in thresholds:
    preds = (baseline_probs >= t).astype(int)
    rec = recall_score(y_avoid, preds, zero_division=0)
    prec = precision_score(y_avoid, preds, zero_division=0)
    f2 = fbeta_score(y_avoid, preds, beta=2, zero_division=0)

    fn = ((y_avoid == 1) & (preds == 0)).sum()
    fp = ((y_avoid == 0) & (preds == 1)).sum()
    flagged = preds.sum()

    marker = ""
    if rec >= 0.96 and prec >= 0.40:
        marker = " <-- TARGET"
        if f2 > best_f2:
            best_f2 = f2
            best_threshold = t

    print(f"  {t:.2f} {rec:>7.1%} {prec:>7.1%} {f2:>7.3f} {fn:>6} {fp:>6} {flagged:>8}{marker}")

print(f"\nBest threshold meeting recall>=96%, precision>=40%: {best_threshold:.2f}")

# Fine-grained sweep around best
fine_range = np.arange(
    max(0.15, best_threshold - 0.05),
    min(0.55, best_threshold + 0.06),
    0.01,
)

print(f"\nFine-grained sweep around {best_threshold:.2f}:")
print(f"{'Thresh':>7} {'Recall':>8} {'Prec':>8} {'F2':>8} {'FN':>6}")
print("-" * 42)

optimal_threshold = best_threshold
optimal_f2 = 0.0

for t in fine_range:
    preds = (baseline_probs >= t).astype(int)
    rec = recall_score(y_avoid, preds, zero_division=0)
    prec = precision_score(y_avoid, preds, zero_division=0)
    f2 = fbeta_score(y_avoid, preds, beta=2, zero_division=0)
    fn = ((y_avoid == 1) & (preds == 0)).sum()

    if rec >= 0.96 and prec >= 0.40 and f2 > optimal_f2:
        optimal_f2 = f2
        optimal_threshold = t

    print(f"  {t:.2f} {rec:>7.1%} {prec:>7.1%} {f2:>7.3f} {fn:>6}")

print(f"\nOptimal threshold (baseline): {optimal_threshold:.2f} (F2={optimal_f2:.3f})")

# ---------------------------------------------------------------------------
# A2. Threshold Sweep with F2-tuned model (after Section B runs)
#     Will be populated after Optuna experiments
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# B. F2-Tuned Optuna vs AUC-Tuned Optuna
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("B. F2-TUNED OPTUNA vs AUC-TUNED OPTUNA")
print("   Compare recall at threshold=0.35 with 15 trials each")
print("=" * 70)

import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

from sklearn.model_selection import RepeatedStratifiedKFold

from services.ml.growth.classifier import _get_classifier_search_space

N_OPTUNA_TRIALS = 15  # Keep fast for research; production uses 50
EVAL_THRESHOLD = optimal_threshold


def run_optuna_experiment(objective_name: str, n_trials: int = N_OPTUNA_TRIALS) -> dict:
    """Run Optuna with either AUC or F2 objective. Returns best params."""
    rskf = RepeatedStratifiedKFold(n_splits=5, n_repeats=2, random_state=42)
    best_params: dict = {}
    best_score: float = -1.0

    def objective(trial: optuna.Trial) -> float:
        nonlocal best_params, best_score
        params = _get_classifier_search_space(trial)
        scores: list[float] = []

        for train_idx, val_idx in rskf.split(X_scaled, y_avoid):
            s = StandardScaler()
            X_tr = s.fit_transform(X_clipped.values[train_idx])
            X_va = s.transform(X_clipped.values[val_idx])

            clf = _build_classifier(params)
            clf.fit(X_tr, y_avoid[train_idx])
            y_prob = clf.predict_proba(X_va)[:, 1]

            if objective_name == "auc":
                try:
                    scores.append(float(roc_auc_score(y_avoid[val_idx], y_prob)))
                except ValueError:
                    pass
            elif objective_name == "f2":
                y_pred = (y_prob >= EVAL_THRESHOLD).astype(int)
                scores.append(float(fbeta_score(
                    y_avoid[val_idx], y_pred, beta=2, zero_division=0,
                )))

        mean_score = float(np.mean(scores)) if scores else 0.0
        if mean_score > best_score:
            best_score = mean_score
            best_params = params
        return mean_score

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return best_params


def evaluate_params(params: dict, label: str) -> dict:
    """Evaluate params with CV, return metrics dict."""
    probs = cross_val_predict(
        _build_classifier(params), X_scaled, y_avoid,
        cv=StratifiedKFold(5, shuffle=True, random_state=42),
        method="predict_proba",
    )[:, 1]

    preds_opt = (probs >= optimal_threshold).astype(int)
    preds_50 = (probs >= 0.5).astype(int)

    auc = roc_auc_score(y_avoid, probs)
    rec_opt = recall_score(y_avoid, preds_opt, zero_division=0)
    prec_opt = precision_score(y_avoid, preds_opt, zero_division=0)
    f2_opt = fbeta_score(y_avoid, preds_opt, beta=2, zero_division=0)
    fn_opt = ((y_avoid == 1) & (preds_opt == 0)).sum()

    rec_50 = recall_score(y_avoid, preds_50, zero_division=0)
    fn_50 = ((y_avoid == 1) & (preds_50 == 0)).sum()

    result = {
        "label": label,
        "auc": auc,
        f"recall@{optimal_threshold:.2f}": rec_opt,
        f"prec@{optimal_threshold:.2f}": prec_opt,
        f"f2@{optimal_threshold:.2f}": f2_opt,
        f"fn@{optimal_threshold:.2f}": fn_opt,
        "recall@0.50": rec_50,
        "fn@0.50": fn_50,
    }
    return result, probs


print("\nRunning AUC-tuned Optuna...")
auc_params = run_optuna_experiment("auc")
auc_metrics, auc_probs = evaluate_params(auc_params, "AUC-tuned")
print(f"  Best params: {auc_params}")

print("\nRunning F2-tuned Optuna...")
f2_params = run_optuna_experiment("f2")
f2_metrics, f2_probs = evaluate_params(f2_params, "F2-tuned")
print(f"  Best params: {f2_params}")

# Baseline (default params)
baseline_metrics, _ = evaluate_params({}, "Baseline (defaults)")

print(f"\n{'Metric':<25} {'Baseline':>12} {'AUC-tuned':>12} {'F2-tuned':>12}")
print("-" * 65)
for key in baseline_metrics:
    if key == "label":
        continue
    b = baseline_metrics[key]
    a = auc_metrics[key]
    f = f2_metrics[key]
    if isinstance(b, float):
        print(f"{key:<25} {b:>12.4f} {a:>12.4f} {f:>12.4f}")
    else:
        print(f"{key:<25} {b:>12} {a:>12} {f:>12}")

# ---------------------------------------------------------------------------
# A2. Threshold Sweep on F2-tuned model
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("A2. THRESHOLD SWEEP ON F2-TUNED MODEL")
print("    Find optimal threshold for the recall-optimized model")
print("=" * 70)

print(f"\n{'Thresh':>7} {'Recall':>8} {'Prec':>8} {'F2':>8} {'FN':>6} {'FP':>6}")
print("-" * 50)

best_f2_threshold = 0.50
best_f2_score = 0.0

for t in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
    preds = (f2_probs >= t).astype(int)
    rec = recall_score(y_avoid, preds, zero_division=0)
    prec = precision_score(y_avoid, preds, zero_division=0)
    f2 = fbeta_score(y_avoid, preds, beta=2, zero_division=0)
    fn = ((y_avoid == 1) & (preds == 0)).sum()
    fp = ((y_avoid == 0) & (preds == 1)).sum()

    marker = ""
    if prec >= 0.40 and f2 > best_f2_score:
        best_f2_score = f2
        best_f2_threshold = t
        marker = " <-- BEST F2"

    print(f"  {t:.2f} {rec:>7.1%} {prec:>7.1%} {f2:>7.3f} {fn:>6} {fp:>6}{marker}")

print(f"\nF2-tuned model best threshold: {best_f2_threshold:.2f} (F2={best_f2_score:.3f})")

# Override optimal_threshold for downstream sections
optimal_threshold = best_f2_threshold

# ---------------------------------------------------------------------------
# C. scale_pos_weight Sensitivity
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("C. SCALE_POS_WEIGHT SENSITIVITY")
print("   Test explicit class weighting [1.0, 1.5, 2.0, 3.0, 5.0]")
print("=" * 70)

spw_values = [1.0, 1.5, 2.0, 3.0, 5.0]

print(f"\n{'SPW':>6} {'AUC':>8} {'Recall':>8} {'Prec':>8} {'F2':>8} {'FN':>6}")
print("-" * 50)

best_spw_f2 = 0.0
best_spw = 1.0

for spw in spw_values:
    # Build classifier without is_unbalance, with explicit scale_pos_weight
    def build_spw_classifier():
        try:
            import lightgbm as lgb
        except ImportError:
            from sklearn.ensemble import HistGradientBoostingClassifier
            return HistGradientBoostingClassifier(
                max_iter=200, max_depth=4, learning_rate=0.05,
                class_weight={0: 1.0, 1: spw}, random_state=42,
            )
        return lgb.LGBMClassifier(
            verbosity=-1, random_state=42, n_jobs=1,
            objective="binary",
            scale_pos_weight=spw,
            n_estimators=200, max_depth=4, num_leaves=15,
            learning_rate=0.05, reg_alpha=0.1, reg_lambda=1.0,
            min_child_samples=10,
        )

    probs = cross_val_predict(
        build_spw_classifier(), X_scaled, y_avoid,
        cv=StratifiedKFold(5, shuffle=True, random_state=42),
        method="predict_proba",
    )[:, 1]

    preds = (probs >= optimal_threshold).astype(int)
    auc = roc_auc_score(y_avoid, probs)
    rec = recall_score(y_avoid, preds, zero_division=0)
    prec = precision_score(y_avoid, preds, zero_division=0)
    f2 = fbeta_score(y_avoid, preds, beta=2, zero_division=0)
    fn = ((y_avoid == 1) & (preds == 0)).sum()

    marker = ""
    if f2 > best_spw_f2:
        best_spw_f2 = f2
        best_spw = spw
        marker = " <-- BEST"

    print(f"  {spw:>4.1f} {auc:>7.4f} {rec:>7.1%} {prec:>7.1%} {f2:>7.3f} {fn:>6}{marker}")

print(f"\nBest scale_pos_weight: {best_spw}")

# ---------------------------------------------------------------------------
# D. Per-Theme FN Analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("D. PER-THEME FN ANALYSIS (baseline vs F2-tuned)")
print("   Focus on weak themes: Minecraft, Harry Potter, Dots, Hidden Side")
print("=" * 70)

# Use F2-tuned probs for comparison
weak_themes = ["Minecraft", "Harry Potter", "Dots", "Hidden Side"]

print(f"\n{'Theme':<20} {'N':>5} {'Losers':>7} | {'Baseline FN':>12} {'F2 FN':>8} | {'BL Miss%':>9} {'F2 Miss%':>9}")
print("-" * 80)

for theme in sorted(set(themes)):
    mask = themes == theme
    n = mask.sum()
    n_avoid = y_avoid[mask].sum()
    if n < 5 or n_avoid < 2:
        continue

    # Baseline FN at optimal threshold
    bl_preds = (baseline_probs[mask] >= optimal_threshold).astype(int)
    bl_fn = ((y_avoid[mask] == 1) & (bl_preds == 0)).sum()
    bl_miss = bl_fn / n_avoid if n_avoid > 0 else 0

    # F2-tuned FN at optimal threshold
    f2_preds = (f2_probs[mask] >= optimal_threshold).astype(int)
    f2_fn = ((y_avoid[mask] == 1) & (f2_preds == 0)).sum()
    f2_miss = f2_fn / n_avoid if n_avoid > 0 else 0

    flag = " <-- WEAK" if theme in weak_themes else ""
    print(f"{str(theme)[:19]:<20} {n:>5} {n_avoid:>7} | {bl_fn:>12} {f2_fn:>8} | {bl_miss:>8.0%} {f2_miss:>8.0%}{flag}")

# ---------------------------------------------------------------------------
# E. Downstream Impact on Hurdle Model
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("E. DOWNSTREAM IMPACT ON HURDLE MODEL")
print("   How does lowered threshold affect final growth predictions?")
print("=" * 70)

# Simulate hurdle combination: P(good) * regressor + P(bad) * median_loser
median_loser = float(np.median(y_all[y_avoid == 1]))
mean_growth = float(y_all.mean())

print(f"\nMedian loser return: {median_loser:.1f}%")
print(f"Mean growth (all sets): {mean_growth:.1f}%")

# The hurdle model uses continuous P(avoid), not the threshold.
# But lowering threshold changes which sets are FLAGGED (binary avoid).
# The continuous predictions DON'T change -- only the binary flag does.
# So the impact is on filtering, not on predicted growth values.

print("\nIMPORTANT: The hurdle model uses continuous P(avoid) as a weight,")
print("not the binary threshold. Lowering the decision threshold only affects:")
print("  1. Which sets get RISK/WARN badges")
print("  2. Which sets the cart system blocks")
print("  3. It does NOT change the hurdle model's continuous growth predictions.")

# Show the distribution shift in flagged sets
for label, probs in [("Baseline", baseline_probs), ("F2-tuned", f2_probs)]:
    flagged = probs >= optimal_threshold
    n_flagged = flagged.sum()
    pct_flagged = n_flagged / len(probs)
    avg_growth_flagged = y_all[flagged].mean() if flagged.sum() > 0 else 0
    avg_growth_unflagged = y_all[~flagged].mean() if (~flagged).sum() > 0 else 0

    print(f"\n  {label} @ threshold={optimal_threshold:.2f}:")
    print(f"    Flagged: {n_flagged} ({pct_flagged:.1%})")
    print(f"    Avg growth (flagged): {avg_growth_flagged:.1f}%")
    print(f"    Avg growth (unflagged): {avg_growth_unflagged:.1f}%")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

# Best F2-tuned at optimal threshold
f2_preds_final = (f2_probs >= optimal_threshold).astype(int)
final_rec = recall_score(y_avoid, f2_preds_final, zero_division=0)
final_prec = precision_score(y_avoid, f2_preds_final, zero_division=0)
final_fn = ((y_avoid == 1) & (f2_preds_final == 0)).sum()
final_auc = roc_auc_score(y_avoid, f2_probs)

# Baseline at 0.50
bl_preds_50 = (baseline_probs >= 0.50).astype(int)
bl_rec_50 = recall_score(y_avoid, bl_preds_50, zero_division=0)
bl_fn_50 = ((y_avoid == 1) & (bl_preds_50 == 0)).sum()

print(f"""
BEFORE (baseline, threshold=0.50):
  Recall: {bl_rec_50:.1%}
  FN:     {bl_fn_50} / {y_avoid.sum()}
  AUC:    {roc_auc_score(y_avoid, baseline_probs):.4f}

AFTER (F2-tuned, threshold={optimal_threshold:.2f}):
  Recall: {final_rec:.1%}
  FN:     {final_fn} / {y_avoid.sum()}
  AUC:    {final_auc:.4f}
  Prec:   {final_prec:.1%}

RECOMMENDED:
  Optimal threshold: {optimal_threshold:.2f}
  Best scale_pos_weight: {best_spw}
  Use F2 objective for Optuna tuning
""")

# Save results
results_df = pd.DataFrame({
    "set_number": df_feat["set_number"].values,
    "theme": themes,
    "actual_growth": y_all,
    "is_avoid": y_avoid,
    "baseline_prob": baseline_probs,
    "f2_tuned_prob": f2_probs,
    "baseline_flagged": (baseline_probs >= 0.50).astype(int),
    "f2_flagged": (f2_probs >= optimal_threshold).astype(int),
})
results_df.to_csv(RESULTS_DIR / "06_fn_minimization.csv", index=False)
print(f"Results saved to {RESULTS_DIR / '06_fn_minimization.csv'}")
print("Done.")
