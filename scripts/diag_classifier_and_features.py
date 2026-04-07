"""Quick diagnostic: classifier tuning + new BrickTalk features.

Tests:
1. Baseline classifier AUC (hardcoded params) vs Optuna-tuned
2. New features (high_price_barrier, shelf_life_x_reviews) impact on regressor
3. Feature importance of new features

Run: python -m scripts.diag_classifier_and_features
"""
from __future__ import annotations

import logging
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, RepeatedStratifiedKFold
from sklearn.preprocessing import PowerTransformer, StandardScaler

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _setup():
    """Load data and prepare features."""
    from db.pg.engine import get_engine
    from services.ml.growth.features import TIER1_FEATURES, engineer_intrinsic_features
    from services.ml.growth.feature_selection import select_features

    engine = get_engine()
    from services.ml.pg_queries import load_growth_training_data
    df_raw = load_growth_training_data(engine)

    y_all = df_raw["annual_growth_pct"].values.astype(float)
    year_retired = np.asarray(
        pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float
    )

    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y_all)
    )

    t1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X_raw = df_feat[t1_candidates].copy()
    for c in X_raw.columns:
        X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
    t1_features = select_features(X_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
    if len(t1_features) < 5:
        t1_features = t1_candidates

    X = X_raw[t1_features].fillna(X_raw[t1_features].median())

    groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
    finite = np.isfinite(year_retired)
    groups[finite] = year_retired[finite].astype(int)

    return df_raw, df_feat, X, y_all, groups, t1_features


# ---------------------------------------------------------------------------
# 1. CLASSIFIER: HARDCODED vs OPTUNA
# ---------------------------------------------------------------------------

def diag_classifier(X, y_all, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("1. CLASSIFIER: HARDCODED vs OPTUNA-TUNED")
    logger.info("=" * 70)

    from services.ml.growth.classifier import (
        _build_classifier,
        _cross_validate,
        make_avoid_labels,
        tune_classifier,
    )

    X_arr = X.values
    y_binary = make_avoid_labels(y_all, threshold=8.0)
    n_avoid = int(y_binary.sum())
    logger.info("  Avoid labels: %d avoid / %d keep (%.1f%%)",
                n_avoid, len(y_binary) - n_avoid, n_avoid / len(y_binary) * 100)

    # Baseline (hardcoded)
    logger.info("")
    logger.info("  --- Baseline (hardcoded params) ---")
    cv_base = _cross_validate(X_arr, y_binary, n_splits=5, n_repeats=3, params=None)
    logger.info("  AUC=%.4f +/-%.4f  F1=%.3f  Recall=%.3f",
                cv_base.auc_mean, cv_base.auc_std, cv_base.f1_mean, cv_base.recall_mean)

    # Optuna-tuned (10 trials for speed, then 30)
    for n_trials in [10, 30]:
        logger.info("")
        logger.info("  --- Optuna (%d trials) ---", n_trials)
        t0 = time.time()
        best_params = tune_classifier(X_arr, y_binary, n_trials=n_trials, n_splits=5, n_repeats=3)
        elapsed = time.time() - t0
        logger.info("  Best params: %s", {k: round(v, 4) if isinstance(v, float) else v for k, v in best_params.items()})

        cv_tuned = _cross_validate(X_arr, y_binary, n_splits=5, n_repeats=3, params=best_params)
        logger.info("  AUC=%.4f +/-%.4f  F1=%.3f  Recall=%.3f  (%.1fs)",
                    cv_tuned.auc_mean, cv_tuned.auc_std, cv_tuned.f1_mean, cv_tuned.recall_mean, elapsed)

        delta = cv_tuned.auc_mean - cv_base.auc_mean
        logger.info("  Delta AUC: %+.4f", delta)

    return cv_base, cv_tuned


# ---------------------------------------------------------------------------
# 2. NEW FEATURES IMPACT ON REGRESSOR
# ---------------------------------------------------------------------------

def diag_new_features(X, y, groups, t1_features, df_feat):
    logger.info("")
    logger.info("=" * 70)
    logger.info("2. NEW FEATURES IMPACT ON REGRESSOR")
    logger.info("=" * 70)

    from services.ml.growth.model_selection import build_model, _get_monotonic_constraints

    new_features = ["high_price_barrier", "shelf_life_x_reviews"]
    old_features = [f for f in t1_features if f not in new_features]

    mono_old = _get_monotonic_constraints(old_features)
    mono_all = _get_monotonic_constraints(t1_features)

    # Prepare old feature set
    X_old_raw = df_feat[old_features].copy()
    for c in X_old_raw.columns:
        X_old_raw[c] = pd.to_numeric(X_old_raw[c], errors="coerce")
    X_old = X_old_raw.fillna(X_old_raw.median())

    def _cv_regressor(X_vals, features, mono, name):
        n_unique = len(set(groups))
        n_splits = min(5, n_unique)
        splitter = GroupKFold(n_splits=n_splits)
        r2s, maes = [], []

        for train_idx, val_idx in splitter.split(np.arange(len(y)), y, groups):
            X_tr, X_va = X_vals[train_idx], X_vals[val_idx]
            y_tr, y_va = y[train_idx], y[val_idx]

            lo, hi = np.percentile(y_tr, [1, 99])
            y_tr = np.clip(y_tr, lo, hi)

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_va_s = scaler.transform(X_va)

            pt = PowerTransformer(method="yeo-johnson", standardize=False)
            y_tr_t = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()

            model = build_model()
            if mono:
                model.set_params(monotone_constraints=mono)
            model.fit(X_tr_s, y_tr_t)
            preds = pt.inverse_transform(model.predict(X_va_s).reshape(-1, 1)).ravel()

            ss_res = np.sum((y_va - preds) ** 2)
            ss_tot = np.sum((y_va - y_va.mean()) ** 2)
            r2s.append(1 - ss_res / ss_tot if ss_tot > 0 else 0)
            maes.append(float(np.mean(np.abs(y_va - preds))))

        logger.info("  %-35s R2=%.3f +/-%.3f  MAE=%.1f%%",
                    name, np.mean(r2s), np.std(r2s), np.mean(maes))
        return np.mean(r2s)

    r2_old = _cv_regressor(X_old.values, old_features, mono_old, "Without new features")
    r2_new = _cv_regressor(X.values, t1_features, mono_all, "With new features")

    logger.info("")
    logger.info("  Delta R2: %+.4f", r2_new - r2_old)

    # Individual feature contribution
    logger.info("")
    logger.info("  --- Individual new feature contribution ---")
    for feat in new_features:
        if feat in df_feat.columns:
            feat_list = old_features + [feat]
            X_plus = df_feat[feat_list].copy()
            for c in X_plus.columns:
                X_plus[c] = pd.to_numeric(X_plus[c], errors="coerce")
            X_plus = X_plus.fillna(X_plus.median())
            mono_plus = _get_monotonic_constraints(feat_list)
            r2_plus = _cv_regressor(X_plus.values, feat_list, mono_plus, f"+ {feat}")
            logger.info("    %s: delta R2=%+.4f", feat, r2_plus - r2_old)

    return r2_old, r2_new


# ---------------------------------------------------------------------------
# 3. FEATURE IMPORTANCE
# ---------------------------------------------------------------------------

def diag_feature_importance(X, y, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("3. FEATURE IMPORTANCE (LightGBM gain)")
    logger.info("=" * 70)

    from services.ml.growth.model_selection import build_model, _get_monotonic_constraints

    mono = _get_monotonic_constraints(t1_features)

    lo, hi = np.percentile(y, [1, 99])
    y_w = np.clip(y, lo, hi)

    scaler = StandardScaler()
    X_s = scaler.fit_transform(X.values)

    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_t = pt.fit_transform(y_w.reshape(-1, 1)).ravel()

    model = build_model()
    if mono:
        model.set_params(monotone_constraints=mono)
    model.fit(X_s, y_t)

    importances = model.feature_importances_
    pairs = sorted(zip(t1_features, importances), key=lambda x: -x[1])

    for feat, imp in pairs:
        marker = " <-- NEW" if feat in ("high_price_barrier", "shelf_life_x_reviews") else ""
        logger.info("  %-30s %6.1f%s", feat, imp, marker)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    logger.info("Classifier Tuning + New Features Diagnostic")
    logger.info("=" * 70)

    df_raw, df_feat, X, y, groups, t1_features = _setup()
    logger.info("Data: %d sets, %d features", len(y), len(t1_features))
    logger.info("Features: %s", t1_features)
    logger.info("New features present: high_price_barrier=%s, shelf_life_x_reviews=%s",
                "high_price_barrier" in t1_features, "shelf_life_x_reviews" in t1_features)

    diag_classifier(X, y, t1_features)
    diag_new_features(X, y, groups, t1_features, df_feat)
    diag_feature_importance(X, y, t1_features)

    elapsed = time.time() - t0
    logger.info("")
    logger.info("=" * 70)
    logger.info("DONE in %.0f seconds", elapsed)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
