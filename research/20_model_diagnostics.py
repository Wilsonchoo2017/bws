"""
20 - Model Diagnostics: Overfitting, Importance, Calibration
=============================================================
Runs on PostgreSQL. No model training -- uses pre-computed LOO predictions.

Diagnostics:
1. Learning curve (n_train vs CV R2)
2. Permutation importance
3. LOFO importance (Leave One Feature Out)
4. Residual analysis
5. Calibration plot (predicted vs actual by decile)
6. Adversarial validation (train/test distribution shift)

Run with: python research/20_model_diagnostics.py
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
warnings.filterwarnings("ignore")


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def main() -> None:
    from db.pg.engine import get_engine
    from services.ml.pg_queries import load_growth_training_data, load_keepa_timelines
    from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
    from services.ml.growth.feature_selection import select_features
    from services.ml.growth.model_selection import build_model, cross_validate_model

    engine = get_engine()
    df_raw = load_growth_training_data(engine)
    y = df_raw["annual_growth_pct"].values.astype(float)
    print(f"Dataset: {len(df_raw)} sets")

    # Engineer features
    df_feat, ts, ss = engineer_intrinsic_features(df_raw, training_target=pd.Series(y))
    candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X_raw = df_feat[candidates].copy()
    for c in X_raw.columns:
        X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")

    selected = select_features(X_raw, y, min_mi_score=0.005, max_correlation=0.90)
    X = X_raw[selected].fillna(X_raw[selected].median())
    feature_names = selected
    print(f"Features: {len(feature_names)}")

    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # ----------------------------------------------------------------
    # 1. LEARNING CURVE
    # ----------------------------------------------------------------
    section("1. LEARNING CURVE")

    from sklearn.model_selection import ShuffleSplit

    train_sizes = [50, 100, 150, 200, 300, 400, 500, len(y)]
    train_sizes = [s for s in train_sizes if s <= len(y)]

    print(f"{'n_train':>8} {'CV R2':>8} {'Train R2':>9} {'Gap':>8}")
    print("-" * 38)

    for n in train_sizes:
        if n == len(y):
            # Use all data
            X_sub, y_sub = X_scaled, y
        else:
            rng = np.random.RandomState(42)
            idx = rng.choice(len(y), size=n, replace=False)
            X_sub, y_sub = X_scaled[idx], y[idx]

        cv = cross_validate_model(
            X_sub, y_sub,
            lambda: build_model("lightgbm"),
            n_splits=5, n_repeats=1,
        )
        # Train R2
        m = build_model("lightgbm")
        m.fit(X_sub, y_sub)
        y_pred_train = m.predict(X_sub)
        ss_res = np.sum((y_sub - y_pred_train) ** 2)
        ss_tot = np.sum((y_sub - y_sub.mean()) ** 2)
        train_r2 = 1 - ss_res / ss_tot

        gap = train_r2 - cv.r2_mean
        print(f"{n:>8} {cv.r2_mean:>8.3f} {train_r2:>9.3f} {gap:>8.3f}")

    # ----------------------------------------------------------------
    # 2. PERMUTATION IMPORTANCE
    # ----------------------------------------------------------------
    section("2. PERMUTATION IMPORTANCE")

    from sklearn.inspection import permutation_importance

    m = build_model("lightgbm")
    m.fit(X_scaled, y)

    perm = permutation_importance(m, X_scaled, y, n_repeats=10, random_state=42)
    perm_df = pd.DataFrame({
        "feature": feature_names,
        "importance_mean": perm.importances_mean,
        "importance_std": perm.importances_std,
    }).sort_values("importance_mean", ascending=False)

    print(f"{'Feature':<30} {'Mean':>8} {'Std':>8}")
    print("-" * 50)
    for _, row in perm_df.iterrows():
        print(f"{row['feature']:<30} {row['importance_mean']:>8.4f} {row['importance_std']:>8.4f}")

    # ----------------------------------------------------------------
    # 3. LOFO IMPORTANCE
    # ----------------------------------------------------------------
    section("3. LOFO IMPORTANCE (Leave One Feature Out)")

    baseline_cv = cross_validate_model(
        X_scaled, y,
        lambda: build_model("lightgbm"),
        n_splits=5, n_repeats=2,
    )
    baseline_r2 = baseline_cv.r2_mean
    print(f"Baseline R2 (all features): {baseline_r2:.4f}\n")

    lofo_results = []
    for i, fname in enumerate(feature_names):
        X_drop = np.delete(X_scaled, i, axis=1)
        cv = cross_validate_model(
            X_drop, y,
            lambda: build_model("lightgbm"),
            n_splits=5, n_repeats=2,
        )
        delta = baseline_r2 - cv.r2_mean
        lofo_results.append((delta, fname, cv.r2_mean))

    lofo_results.sort(reverse=True)
    print(f"{'Feature':<30} {'R2 drop':>8} {'R2 without':>11}")
    print("-" * 53)
    for delta, fname, r2_without in lofo_results:
        marker = " ***" if delta > 0.01 else " *" if delta > 0.005 else ""
        print(f"{fname:<30} {delta:>+8.4f} {r2_without:>11.4f}{marker}")

    # ----------------------------------------------------------------
    # 4. RESIDUAL ANALYSIS
    # ----------------------------------------------------------------
    section("4. RESIDUAL ANALYSIS")

    from sklearn.model_selection import cross_val_predict, KFold

    y_pred_cv = cross_val_predict(m, X_scaled, y, cv=KFold(5, shuffle=True, random_state=42))
    residuals = y - y_pred_cv

    print(f"Residual stats:")
    print(f"  Mean:   {np.mean(residuals):+.3f}% (should be ~0)")
    print(f"  Std:    {np.std(residuals):.3f}%")
    print(f"  Skew:   {float(pd.Series(residuals).skew()):.3f}")
    print(f"  Kurt:   {float(pd.Series(residuals).kurtosis()):.3f}")

    # Residuals by growth quintile
    print(f"\nResiduals by actual growth quintile:")
    quintiles = pd.qcut(y, q=5, duplicates="drop")
    for q, idx in pd.Series(range(len(y))).groupby(quintiles).groups.items():
        r = residuals[list(idx)]
        print(f"  {str(q):>20s}: mean_resid={np.mean(r):+.2f}%, std={np.std(r):.2f}%")

    # ----------------------------------------------------------------
    # 5. CALIBRATION PLOT (predicted vs actual by decile)
    # ----------------------------------------------------------------
    section("5. CALIBRATION (Predicted vs Actual by Decile)")

    deciles = pd.qcut(y_pred_cv, q=10, duplicates="drop")
    print(f"{'Predicted Range':<25} {'Pred Mean':>10} {'Actual Mean':>12} {'Bias':>8} {'n':>5}")
    print("-" * 65)
    for d, idx in pd.Series(range(len(y))).groupby(deciles).groups.items():
        pred_m = np.mean(y_pred_cv[list(idx)])
        act_m = np.mean(y[list(idx)])
        bias = pred_m - act_m
        print(f"{str(d):<25} {pred_m:>10.1f}% {act_m:>11.1f}% {bias:>+7.1f}% {len(idx):>5}")

    # ----------------------------------------------------------------
    # 6. ADVERSARIAL VALIDATION
    # ----------------------------------------------------------------
    section("6. ADVERSARIAL VALIDATION (Distribution Shift by Year)")

    year_retired = pd.to_numeric(df_raw.get("year_retired"), errors="coerce")
    valid_years = year_retired.dropna()

    if len(valid_years) > 100:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score

        # Can a classifier distinguish 2024 sets from earlier sets?
        latest_year = int(valid_years.max())
        mask = year_retired.notna()
        X_adv = X_scaled[mask.values]
        y_adv = (year_retired[mask] >= latest_year).astype(int).values

        if y_adv.sum() >= 10 and (1 - y_adv).sum() >= 10:
            clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=4)
            auc_scores = cross_val_score(clf, X_adv, y_adv, cv=5, scoring="roc_auc")
            print(f"Can we distinguish {latest_year} sets from earlier? AUC={np.mean(auc_scores):.3f}")
            print(f"  AUC=0.50 = no shift, AUC>0.70 = significant shift")

            # Which features drive the shift?
            clf.fit(X_adv, y_adv)
            shift_imp = sorted(
                zip(feature_names, clf.feature_importances_),
                key=lambda x: x[1], reverse=True,
            )
            print(f"\n  Top features driving distribution shift:")
            for fname, imp in shift_imp[:5]:
                print(f"    {fname:<30} {imp:.3f}")
    else:
        print("Insufficient year_retired data for adversarial validation")

    # ----------------------------------------------------------------
    # 7. OVERFIT SUMMARY
    # ----------------------------------------------------------------
    section("7. OVERFIT DIAGNOSTIC SUMMARY")

    # Recompute train R2 for summary
    m_final = build_model("lightgbm")
    m_final.fit(X_scaled, y)
    y_train_pred = m_final.predict(X_scaled)
    train_r2 = 1 - np.sum((y - y_train_pred)**2) / np.sum((y - y.mean())**2)

    cv_final = cross_validate_model(
        X_scaled, y, lambda: build_model("lightgbm"),
        n_splits=5, n_repeats=3,
    )

    gap = train_r2 - cv_final.r2_mean
    gap_status = "OK" if gap < 0.15 else "WARNING" if gap < 0.30 else "OVERFIT"

    print(f"  Train R2:          {train_r2:.3f}")
    print(f"  CV R2:             {cv_final.r2_mean:.3f} +/-{cv_final.r2_std:.3f}")
    print(f"  Train/CV Gap:      {gap:.3f} ({gap_status})")
    print(f"  CV Fold Variance:  {cv_final.r2_std:.3f} ({'OK' if cv_final.r2_std < 0.10 else 'HIGH'})")
    print(f"  Features:          {len(feature_names)}")
    print(f"  Samples/Feature:   {len(y) / len(feature_names):.0f}")

    print(f"\n{'=' * 60}")
    print("  DIAGNOSTICS COMPLETE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
