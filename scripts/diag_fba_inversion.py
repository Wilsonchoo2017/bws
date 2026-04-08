"""Diagnostic: inverted 3P FBA signal for the avoid classifier.

Inversion framing: sets where 3P FBA stays BELOW RRP = weak demand = avoid.
Tests both classifier (AUC) and regressor (R2) impact.

Run: python -m scripts.diag_fba_inversion
"""
from __future__ import annotations

import json
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


def main():
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("Diagnostic: Inverted 3P FBA Signal (below RRP = weak demand)")
    logger.info("=" * 70)

    from db.pg.engine import get_engine
    from services.ml.growth.features import (
        TIER1_FEATURES,
        engineer_intrinsic_features,
        engineer_keepa_features,
    )
    from services.ml.growth.feature_selection import select_features
    from services.ml.growth.model_selection import build_model, _get_monotonic_constraints
    from services.ml.growth.classifier import (
        _build_classifier,
        _cross_validate,
        make_avoid_labels,
    )
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

    # Current T1 baseline
    t1_candidates = [f for f in TIER1_FEATURES if f in df_kp.columns]
    X_raw = df_kp[t1_candidates].copy()
    for c in X_raw.columns:
        X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
    t1_selected = select_features(X_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
    if len(t1_selected) < 5:
        t1_selected = t1_candidates

    logger.info("T1 selected: %d features", len(t1_selected))

    # --- Build inverted features ---
    # Use existing Keepa data already in df_kp
    fba_floor = df_kp.get("kp_fba_floor_vs_rrp")  # continuous: (min_fba - rrp) / rrp * 100
    fba_above = df_kp.get("kp_fba_floor_above_rrp")  # binary: min >= 98% rrp
    fba_never = df_kp.get("kp_fba_never_below_rrp")  # binary: all >= 95% rrp

    # Inverted signals
    df_kp["kp_fba_always_below_rrp"] = np.where(
        fba_above.notna(), 1.0 - fba_above, np.nan
    )
    df_kp["kp_fba_ever_below_rrp"] = np.where(
        fba_never.notna(), 1.0 - fba_never, np.nan
    )
    # How far below RRP is the floor (negative = deeper discount = weaker demand)
    df_kp["kp_fba_floor_deficit"] = np.where(
        fba_floor.notna(),
        np.clip(-fba_floor, 0, None),  # positive = amount below RRP
        np.nan,
    )
    # Binary: deep discount floor (> 20% below RRP)
    df_kp["kp_fba_deep_discount"] = np.where(
        fba_floor.notna(),
        (fba_floor < -20).astype(float),
        np.nan,
    )
    # Binary: moderate discount floor (> 5% below RRP)
    df_kp["kp_fba_below_5pct"] = np.where(
        fba_floor.notna(),
        (fba_floor < -5).astype(float),
        np.nan,
    )

    inverted_features = [
        "kp_fba_always_below_rrp",
        "kp_fba_ever_below_rrp",
        "kp_fba_floor_deficit",
        "kp_fba_deep_discount",
        "kp_fba_below_5pct",
    ]

    # --- Coverage and distribution ---
    logger.info("")
    logger.info("--- Inverted feature coverage ---")
    y_binary = make_avoid_labels(y_all, threshold=8.0)
    for feat in inverted_features:
        vals = df_kp[feat].dropna()
        n_cov = len(vals)
        if n_cov == 0:
            logger.info("  %s: no coverage", feat)
            continue
        pct_1 = (vals == 1).mean() * 100 if vals.nunique() <= 2 else float("nan")

        # Avoid rate by feature value
        mask = df_kp[feat].notna()
        if vals.nunique() <= 2:
            mask_1 = mask & (df_kp[feat] == 1)
            mask_0 = mask & (df_kp[feat] == 0)
            avoid_1 = y_binary[mask_1].mean() * 100 if mask_1.sum() > 0 else 0
            avoid_0 = y_binary[mask_0].mean() * 100 if mask_0.sum() > 0 else 0
            growth_1 = y_all[mask_1].mean() if mask_1.sum() > 0 else 0
            growth_0 = y_all[mask_0].mean() if mask_0.sum() > 0 else 0
            logger.info("  %-30s cov=%d (%.0f%%)  =1: %.0f%% | =1 avoid=%.1f%% growth=%.1f%% | =0 avoid=%.1f%% growth=%.1f%%",
                        feat, n_cov, n_cov / len(df_kp) * 100, pct_1,
                        avoid_1, growth_1, avoid_0, growth_0)
        else:
            corr = np.corrcoef(df_kp[feat][mask].values, y_all[mask])[0, 1]
            logger.info("  %-30s cov=%d (%.0f%%)  corr=%.3f",
                        feat, n_cov, n_cov / len(df_kp) * 100, corr)

    # --- Classifier impact ---
    logger.info("")
    logger.info("=" * 70)
    logger.info("CLASSIFIER IMPACT (avoid AUC)")
    logger.info("=" * 70)

    X_base = df_kp[t1_selected].copy()
    for c in X_base.columns:
        X_base[c] = pd.to_numeric(X_base[c], errors="coerce")
    X_base = X_base.fillna(X_base.median())

    cv_base = _cross_validate(X_base.values, y_binary, n_splits=5, n_repeats=3, params=None)
    logger.info("  %-45s AUC=%.4f +/-%.4f  F1=%.3f  Recall=%.3f",
                "T1 baseline", cv_base.auc_mean, cv_base.auc_std, cv_base.f1_mean, cv_base.recall_mean)

    for feat in inverted_features:
        if feat not in df_kp.columns:
            continue
        feat_list = t1_selected + [feat]
        X_test = df_kp[feat_list].copy()
        for c in X_test.columns:
            X_test[c] = pd.to_numeric(X_test[c], errors="coerce")
        X_test = X_test.fillna(X_test.median())

        cv = _cross_validate(X_test.values, y_binary, n_splits=5, n_repeats=3, params=None)
        delta_auc = cv.auc_mean - cv_base.auc_mean
        delta_recall = cv.recall_mean - cv_base.recall_mean
        logger.info("  %-45s AUC=%.4f +/-%.4f  F1=%.3f  Recall=%.3f  dAUC=%+.4f  dRecall=%+.3f",
                    f"+ {feat}", cv.auc_mean, cv.auc_std, cv.f1_mean, cv.recall_mean,
                    delta_auc, delta_recall)

    # --- Regressor impact ---
    logger.info("")
    logger.info("=" * 70)
    logger.info("REGRESSOR IMPACT (CV R2)")
    logger.info("=" * 70)

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

        r2_mean = np.mean(r2s)
        logger.info("  %-45s R2=%.3f +/-%.3f  MAE=%.1f%%", name, r2_mean, np.std(r2s), np.mean(maes))
        return r2_mean

    r2_base = _cv_regressor(t1_selected, "T1 baseline")

    for feat in inverted_features:
        if feat not in df_kp.columns:
            continue
        feat_list = t1_selected + [feat]
        r2 = _cv_regressor(feat_list, f"+ {feat}")
        logger.info("    Delta R2: %+.4f", r2 - r2_base)

    elapsed = time.time() - t0
    logger.info("")
    logger.info("=" * 70)
    logger.info("DONE in %.0f seconds", elapsed)


if __name__ == "__main__":
    main()
