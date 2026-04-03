"""
02 - Munger Inversion Classifier: Predicting Which Sets to Avoid
================================================================
Train a binary classifier: should we AVOID this set?

Target: annual_growth_pct < 5% from BrickEconomy (bottom 20% of sets)

Uses the same feature engineering as the production growth model
(Tier 1 intrinsics + theme/subtheme LOO encoding) with 345 sets.

Key design choices:
- class_weight="balanced" to handle minority class (~20% losers)
- LeaveOneOut CV (small-ish dataset, maximizes training data)
- Optimize for PRECISION on "avoid" (minimize false alarms)
- Proper pre-processing: impute -> PowerTransform -> scale

Run with: python research/inversion/02_inversion_classifier.py
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.model_selection import LeaveOneOut, StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PowerTransformer, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.ml import InversionConfig
from services.ml.growth_model import (
    TIER1_FEATURES,
    _engineer_intrinsic_features,
    _load_training_data,
)

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "inversion"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

AVOID_THRESHOLD = 5.0  # annual_growth_pct below this = avoid

# ---------------------------------------------------------------------------
# 1. Load and prepare data
# ---------------------------------------------------------------------------

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

print("=" * 70)
print(f"INVERSION CLASSIFIER: Predict 'avoid' (growth < {AVOID_THRESHOLD}%)")
print("=" * 70)

raw_df = _load_training_data(db)
print(f"\nRaw sets loaded: {len(raw_df)}")

# Engineer features using the same pipeline as growth model
target = raw_df["annual_growth_pct"].astype(float)
feat_df, theme_stats, subtheme_stats = _engineer_intrinsic_features(
    raw_df, training_target=target,
)

# Create avoid label
feat_df["avoid"] = (target < AVOID_THRESHOLD).astype(int)
y = feat_df["avoid"].values
y_growth = target.values

print(f"Sets with features: {len(feat_df)}")
print(f"Avoid (positive class): {y.sum()} ({y.mean():.1%})")
print(f"Keep (negative class):  {(1 - y).sum()} ({(1 - y).mean():.1%})")

# Select Tier 1 features (available for all sets)
feature_cols = [c for c in TIER1_FEATURES if c in feat_df.columns]
X_raw = feat_df[feature_cols].copy()

# Fill NaN with median
for col in feature_cols:
    X_raw[col] = pd.to_numeric(X_raw[col], errors="coerce")
medians = X_raw.median()
X_raw = X_raw.fillna(medians)

print(f"Features: {len(feature_cols)}")
print(f"  {', '.join(feature_cols)}")

# ---------------------------------------------------------------------------
# 1b. Feature selection (classification-aware)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE SELECTION (classification-aware)")
print("=" * 70)

from services.ml.feature_selection import select_features

# Build a DataFrame for feature selection
sel_df = X_raw.copy()
sel_df["avoid"] = y

selection = select_features(sel_df, "avoid", feature_cols, task="inversion")
selected_cols = selection.selected_features

print(f"Selected: {len(selected_cols)} / {len(feature_cols)} features")
print(f"Dropped:  {selection.dropped_features}")

if selection.method_results.get("mutual_info"):
    mi_scores = selection.method_results["mutual_info"]
    mi_sorted = sorted(mi_scores.items(), key=lambda x: x[1], reverse=True)
    print("\nMutual Information ranking (classification):")
    for feat, score in mi_sorted:
        marker = " *" if feat in selected_cols else "  "
        print(f"  {marker} {feat:<25}: {score:.4f}")

X = X_raw[selected_cols]
print(f"\nFinal feature matrix: {X.shape}")

# ---------------------------------------------------------------------------
# 1c. Pre-processing analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PRE-PROCESSING: Feature Distribution Analysis")
print("=" * 70)

print(f"\n{'Feature':<25} {'Mean':>10} {'Std':>10} {'Skew':>8} {'Null%':>7}")
print("-" * 65)
for col in selected_cols:
    vals = X[col]
    skew = float(vals.skew()) if len(vals.dropna()) > 2 else 0
    null_pct = vals.isna().mean()
    print(f"{col:<25} {vals.mean():>10.2f} {vals.std():>10.2f} {skew:>7.2f} {null_pct:>6.1%}")

# ---------------------------------------------------------------------------
# 2. Cross-validation with multiple models
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CROSS-VALIDATION (with proper pre-processing)")
print("=" * 70)

# Use StratifiedKFold for faster iteration; LOO for final model
# With 345 sets, LOO = 345 fits per model -- feasible but slow
USE_LOO = len(X) <= 400

if USE_LOO:
    cv = LeaveOneOut()
    cv_name = "LeaveOneOut"
else:
    cv = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
    cv_name = "10-Fold Stratified"

print(f"CV strategy: {cv_name} ({len(X)} sets)")

models = {
    "LR_basic": Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(
            C=1.0, class_weight="balanced", max_iter=1000, random_state=42
        )),
    ]),
    "LR_power": Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("power", PowerTransformer(method="yeo-johnson", standardize=False)),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(
            C=1.0, class_weight="balanced", max_iter=1000, random_state=42
        )),
    ]),
    "LR_L1": Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("power", PowerTransformer(method="yeo-johnson", standardize=False)),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(
            solver="saga", C=0.5, l1_ratio=1.0,
            class_weight="balanced", max_iter=2000, random_state=42
        )),
    ]),
    "GBM_balanced": Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingClassifier(
            max_iter=200, max_depth=4, learning_rate=0.05,
            class_weight="balanced", random_state=42,
        )),
    ]),
    "RF_balanced": Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", RandomForestClassifier(
            n_estimators=200, max_depth=6, class_weight="balanced", random_state=42,
        )),
    ]),
}

results = {}

for name, model in models.items():
    print(f"\n--- {name} ---")

    y_prob = cross_val_predict(model, X.values, y, cv=cv, method="predict_proba")[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    try:
        auc = roc_auc_score(y, y_prob)
    except ValueError:
        auc = 0.0

    cm = confusion_matrix(y, y_pred)
    report = classification_report(y, y_pred, target_names=["keep", "avoid"], zero_division=0)

    print(f"  ROC-AUC: {auc:.4f}")
    print(f"  Confusion Matrix:\n{cm}")
    print(f"\n{report}")

    results[name] = {
        "auc": auc,
        "y_prob": y_prob,
        "y_pred": y_pred,
    }

# ---------------------------------------------------------------------------
# 3. Precision-Recall tradeoff analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("PRECISION-RECALL TRADEOFF (we want HIGH precision on 'avoid')")
print("=" * 70)

for name, res in results.items():
    print(f"\n--- {name} (AUC={res['auc']:.3f}) ---")
    print(f"{'Threshold':>10} {'Precision':>10} {'Recall':>10} {'N_flagged':>10}")
    print("-" * 45)
    for threshold in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        preds = (res["y_prob"] >= threshold).astype(int)
        n_flagged = int(preds.sum())
        if n_flagged > 0:
            precision = float((preds & y).sum()) / n_flagged
            recall = float((preds & y).sum()) / y.sum() if y.sum() > 0 else 0
        else:
            precision = 0.0
            recall = 0.0
        print(f"{threshold:>10.1f} {precision:>10.1%} {recall:>10.1%} {n_flagged:>10}")

# ---------------------------------------------------------------------------
# 4. Feature importance (best model)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FEATURE IMPORTANCE (GBM_balanced)")
print("=" * 70)

best_model = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("model", HistGradientBoostingClassifier(
        max_iter=200, max_depth=4, learning_rate=0.05,
        class_weight="balanced", random_state=42,
    )),
])
best_model.fit(X.values, y)

from sklearn.inspection import permutation_importance

perm_imp = permutation_importance(best_model, X.values, y, n_repeats=10, random_state=42)

importance_df = pd.DataFrame({
    "feature": selected_cols,
    "importance_mean": perm_imp.importances_mean,
    "importance_std": perm_imp.importances_std,
}).sort_values("importance_mean", ascending=False)

print(f"\n{'Feature':<25} {'Importance':>12} {'Std':>10}")
print("-" * 50)
for _, row in importance_df.iterrows():
    print(f"{row['feature']:<25} {row['importance_mean']:>12.4f} {row['importance_std']:>10.4f}")

# ---------------------------------------------------------------------------
# 5. Growth impact analysis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("GROWTH IMPACT ANALYSIS")
print("=" * 70)

best_probs = results.get("GBM_balanced", {}).get("y_prob", np.zeros(len(y)))

for threshold in [0.4, 0.5, 0.6]:
    flagged = best_probs >= threshold
    if not flagged.any():
        continue

    flagged_growth = y_growth[flagged]
    kept_growth = y_growth[~flagged]

    print(f"\n--- Threshold {threshold:.0%} ---")
    print(f"  Flagged as avoid:       {flagged.sum()} sets")
    print(f"  Avg growth of flagged:  {np.mean(flagged_growth):.1f}%")
    print(f"  Avg growth of kept:     {np.mean(kept_growth):.1f}%")
    print(f"  Growth improvement:     +{np.mean(kept_growth) - np.mean(y_growth):.1f}% vs baseline")

# ---------------------------------------------------------------------------
# 6. Per-set predictions
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TOP 15 SETS FLAGGED FOR AVOIDANCE (GBM)")
print("=" * 70)

pred_df = feat_df[["set_number", "title", "theme"]].copy()
pred_df["avoid_prob"] = best_probs
pred_df["actual_growth"] = y_growth
pred_df["actually_avoid"] = y
pred_df = pred_df.sort_values("avoid_prob", ascending=False)

print(f"\n{'Set':<10} {'Title':<25} {'Prob':>6} {'Growth':>7} {'Correct':>8}")
print("-" * 62)
for _, row in pred_df.head(15).iterrows():
    title = str(row["title"])[:24]
    correct = "Y" if (row["avoid_prob"] >= 0.5 and row["actually_avoid"]) else "N"
    print(f"{row['set_number']:<10} {title:<25} {row['avoid_prob']:>5.0%} {row['actual_growth']:>6.1f}% {correct:>8}")

# ---------------------------------------------------------------------------
# 7. Save results
# ---------------------------------------------------------------------------

pred_df.to_csv(RESULTS_DIR / "02_classifier_predictions.csv", index=False)
importance_df.to_csv(RESULTS_DIR / "02_feature_importance.csv", index=False)

summary = pd.DataFrame([
    {"model": name, "auc": res["auc"]}
    for name, res in results.items()
]).sort_values("auc", ascending=False)
summary.to_csv(RESULTS_DIR / "02_model_comparison.csv", index=False)

print(f"\nResults saved to {RESULTS_DIR}")

db.close()
print("\nDone.")
