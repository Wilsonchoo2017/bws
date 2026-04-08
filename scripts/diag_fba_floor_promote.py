"""Diagnostic: promote kp_fba_floor_above_rrp from T2 to T1.

Tests whether adding this single binary Keepa feature to the T1 feature set
improves or hurts CV on the full 1701-set training data.

Exp 30 showed +0.017 R2 on 642 Keepa-only sets.
Question: does it help on full dataset (where ~40% won't have the feature)?

Run: python -m scripts.diag_fba_floor_promote
"""
from __future__ import annotations

import logging
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer, StandardScaler

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main():
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("Diagnostic: Promote kp_fba_floor_above_rrp to T1")
    logger.info("=" * 70)

    from db.pg.engine import get_engine
    from services.ml.growth.features import (
        TIER1_FEATURES,
        engineer_intrinsic_features,
        engineer_keepa_features,
    )
    from services.ml.growth.feature_selection import select_features
    from services.ml.growth.model_selection import build_model, _get_monotonic_constraints
    from services.ml.pg_queries import load_growth_training_data, load_keepa_timelines

    engine = get_engine()
    df_raw = load_growth_training_data(engine)
    keepa_df = load_keepa_timelines(engine)

    y_all = df_raw["annual_growth_pct"].values.astype(float)
    year_retired = np.asarray(
        pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float
    )
    groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
    finite = np.isfinite(year_retired)
    groups[finite] = year_retired[finite].astype(int)

    # Engineer features
    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y_all),
    )
    cutoff_dates: dict[str, str] = {}
    df_kp = engineer_keepa_features(df_feat, keepa_df, cutoff_dates=cutoff_dates)

    # --- Baseline: current T1 features ---
    t1_candidates = [f for f in TIER1_FEATURES if f in df_kp.columns]
    X_raw = df_kp[t1_candidates].copy()
    for c in X_raw.columns:
        X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
    t1_selected = select_features(X_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
    if len(t1_selected) < 5:
        t1_selected = t1_candidates

    logger.info("T1 candidates: %d, selected: %d", len(t1_candidates), len(t1_selected))
    logger.info("T1 features: %s", t1_selected)

    # --- Test: T1 + kp_fba_floor_above_rrp ---
    new_feature = "kp_fba_floor_above_rrp"
    coverage = df_kp[new_feature].notna().sum() if new_feature in df_kp.columns else 0
    logger.info("")
    logger.info("Feature: %s", new_feature)
    logger.info("Coverage: %d / %d (%.1f%%)", coverage, len(df_kp), coverage / len(df_kp) * 100)

    if new_feature in df_kp.columns:
        vals = df_kp[new_feature].dropna()
        logger.info("Value dist: %.1f%% = 1 (floor above RRP), %.1f%% = 0",
                     (vals == 1).mean() * 100, (vals == 0).mean() * 100)

    # Also test the other Exp 30 features individually
    exp30_features = [
        "kp_fba_floor_above_rrp",
        "kp_fba_floor_vs_rrp",
        "kp_fbm_mean_vs_rrp",
        "kp_fba_never_below_rrp",
    ]

    def _cv_regressor(feature_list, name):
        X = df_kp[feature_list].copy()
        for c in X.columns:
            X[c] = pd.to_numeric(X[c], errors="coerce")
        X = X.fillna(X.median())

        mono = _get_monotonic_constraints(feature_list)
        n_splits = min(5, len(set(groups)))
        splitter = GroupKFold(n_splits=n_splits)
        r2s, maes = [], []

        for train_idx, val_idx in splitter.split(np.arange(len(y_all)), y_all, groups):
            X_tr, X_va = X.values[train_idx], X.values[val_idx]
            y_tr, y_va = y_all[train_idx], y_all[val_idx]

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

        r2_mean, r2_std = np.mean(r2s), np.std(r2s)
        mae_mean = np.mean(maes)
        logger.info("  %-45s R2=%.3f +/-%.3f  MAE=%.1f%%", name, r2_mean, r2_std, mae_mean)
        return r2_mean

    # Run CV comparisons
    logger.info("")
    logger.info("=" * 70)
    logger.info("CV COMPARISON (full %d sets, GroupKFold)", len(y_all))
    logger.info("=" * 70)

    r2_baseline = _cv_regressor(t1_selected, "T1 baseline (current)")

    # Test each Exp 30 feature individually
    logger.info("")
    logger.info("--- Individual Exp 30 features added to T1 ---")
    for feat in exp30_features:
        if feat in df_kp.columns and feat not in t1_selected:
            feat_list = t1_selected + [feat]
            r2 = _cv_regressor(feat_list, f"T1 + {feat}")
            logger.info("    Delta: %+.4f", r2 - r2_baseline)
        elif feat in t1_selected:
            logger.info("  %s already in T1 selected", feat)
        else:
            logger.info("  %s not in dataframe", feat)

    # Test with feature selection re-run (would it survive MI + LOFO?)
    logger.info("")
    logger.info("--- Feature selection test ---")
    from sklearn.feature_selection import mutual_info_regression

    if new_feature in df_kp.columns:
        feat_vals = df_kp[new_feature].fillna(0).values.reshape(-1, 1)
        mi = mutual_info_regression(feat_vals, y_all, random_state=42)[0]
        logger.info("  MI(%s, growth) = %.4f (threshold=0.005)", new_feature, mi)

        # Correlation with existing T1 features
        logger.info("")
        logger.info("--- Correlation with T1 features ---")
        X_check = df_kp[t1_selected + [new_feature]].copy()
        for c in X_check.columns:
            X_check[c] = pd.to_numeric(X_check[c], errors="coerce")
        corrs = X_check.corr()[new_feature].drop(new_feature).abs().sort_values(ascending=False)
        for feat_name, corr_val in corrs.head(5).items():
            logger.info("  |corr(%s, %s)| = %.3f", new_feature, feat_name, corr_val)

    # Test promoting to T1 with re-run of feature selection
    logger.info("")
    logger.info("--- T1 + fba_floor with feature selection re-run ---")
    extended_candidates = t1_candidates + [f for f in exp30_features if f in df_kp.columns and f not in t1_candidates]
    X_ext = df_kp[extended_candidates].copy()
    for c in X_ext.columns:
        X_ext[c] = pd.to_numeric(X_ext[c], errors="coerce")
    ext_selected = select_features(X_ext, y_all, min_mi_score=0.005, max_correlation=0.90)
    if len(ext_selected) < 5:
        ext_selected = extended_candidates

    survived = [f for f in exp30_features if f in ext_selected]
    logger.info("  Extended candidates: %d, selected: %d", len(extended_candidates), len(ext_selected))
    logger.info("  Exp 30 features that survived selection: %s", survived or "NONE")

    if ext_selected != t1_selected:
        r2_ext = _cv_regressor(ext_selected, "T1 + Exp30 (after selection)")
        logger.info("    Delta vs baseline: %+.4f", r2_ext - r2_baseline)

    elapsed = time.time() - t0
    logger.info("")
    logger.info("=" * 70)
    logger.info("DONE in %.0f seconds", elapsed)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
