"""Head-to-head evaluation: T1 vs T2 vs Ensemble on the SAME test sets.

Run: python -m scripts.eval_tiers
"""
from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import KFold, GroupKFold
from sklearn.preprocessing import PowerTransformer, StandardScaler

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    from db.pg.engine import get_engine
    from services.ml.growth.features import (
        TIER1_FEATURES,
        TIER2_FEATURES,
        engineer_intrinsic_features,
        engineer_keepa_features,
    )
    from services.ml.growth.feature_selection import select_features
    from services.ml.growth.model_selection import (
        _get_monotonic_constraints,
        build_model,
        clip_outliers,
        compute_recency_weights,
    )
    from services.ml.pg_queries import load_growth_training_data, load_keepa_timelines

    engine = get_engine()
    df_raw = load_growth_training_data(engine)
    keepa_df = load_keepa_timelines(engine)
    logger.info("Loaded %d training sets, %d keepa rows", len(df_raw), len(keepa_df))

    y_all = df_raw["annual_growth_pct"].values.astype(float)

    # Temporal groups
    year_retired = np.asarray(
        pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float
    )
    has_groups = np.isfinite(year_retired).sum() > len(y_all) * 0.5

    # Feature engineering
    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y_all)
    )

    # T1 features
    t1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X1_raw = df_feat[t1_candidates].copy()
    for c in X1_raw.columns:
        X1_raw[c] = pd.to_numeric(X1_raw[c], errors="coerce")
    t1_features = select_features(X1_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
    if len(t1_features) < 5:
        t1_features = t1_candidates

    # T2 features (Keepa)
    df_kp = engineer_keepa_features(df_feat, keepa_df)
    has_keepa = df_kp["kp_bb_premium"].notna() | df_kp["kp_below_rrp_pct"].notna()
    keepa_mask = has_keepa.values

    t2_candidates = [f for f in TIER2_FEATURES if f in df_kp.columns]
    X2_raw = df_kp[t2_candidates].copy()
    for c in X2_raw.columns:
        X2_raw[c] = pd.to_numeric(X2_raw[c], errors="coerce")

    logger.info("")
    logger.info("=" * 70)
    logger.info("DATA SUMMARY")
    logger.info("=" * 70)
    logger.info("Total sets: %d", len(y_all))
    logger.info("Sets with Keepa data: %d", keepa_mask.sum())
    logger.info("T1 features (%d): %s", len(t1_features), t1_features)
    logger.info("T2 candidate features (%d): %s", len(t2_candidates), t2_candidates)
    logger.info(
        "Target: mean=%.1f%%, median=%.1f%%, std=%.1f%%",
        np.mean(y_all), np.median(y_all), np.std(y_all),
    )

    # -----------------------------------------------------------------------
    # HEAD-TO-HEAD: Evaluate T1 vs T2 on the SAME Keepa subset
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("HEAD-TO-HEAD: T1 vs T2 on Keepa subset (%d sets)", keepa_mask.sum())
    logger.info("=" * 70)

    df_keepa_sub = df_kp[has_keepa].copy()
    y_keepa = df_keepa_sub["annual_growth_pct"].values.astype(float)

    # Prepare T1 features for Keepa subset
    X1_keepa = df_feat.loc[has_keepa, t1_features].copy()
    for c in X1_keepa.columns:
        X1_keepa[c] = pd.to_numeric(X1_keepa[c], errors="coerce")
    X1_keepa = X1_keepa.fillna(X1_keepa.median())

    # Prepare T2 features for Keepa subset
    t2_feats_avail = [f for f in t2_candidates if f in df_keepa_sub.columns]
    X2_keepa = df_keepa_sub[t2_feats_avail].copy()
    for c in X2_keepa.columns:
        X2_keepa[c] = pd.to_numeric(X2_keepa[c], errors="coerce")
    X2_keepa = X2_keepa.fillna(X2_keepa.median())

    # Groups for Keepa subset
    groups_keepa = year_retired[keepa_mask] if has_groups else None

    n_keepa = len(y_keepa)
    if n_keepa < 30:
        logger.info("Only %d Keepa sets - too few for reliable comparison", n_keepa)
        return

    # CV setup
    if groups_keepa is not None and np.isfinite(groups_keepa).sum() > n_keepa * 0.5:
        finite = np.isfinite(groups_keepa)
        g = np.full(n_keepa, int(np.nanmedian(groups_keepa)), dtype=int)
        g[finite] = groups_keepa[finite].astype(int)
        n_unique = len(set(g))
        n_splits = min(5, n_unique)
        splitter = GroupKFold(n_splits=n_splits)
        split_args = (np.arange(n_keepa), y_keepa, g)
        cv_type = f"GroupKFold({n_splits})"
    else:
        splitter = KFold(n_splits=5, shuffle=True, random_state=42)
        split_args = (np.arange(n_keepa),)
        cv_type = "KFold(5)"

    logger.info("CV strategy: %s", cv_type)

    def _cv_eval(X: pd.DataFrame, y: np.ndarray, name: str, features: list[str]) -> dict:
        """Run CV and return metrics."""
        mono = _get_monotonic_constraints(features)
        r2s, maes = [], []
        oof_pred = np.full(len(y), np.nan)

        for train_idx, val_idx in splitter.split(*split_args):
            X_tr, X_va = X.values[train_idx], X.values[val_idx]
            y_tr, y_va = y[train_idx], y[val_idx]

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_va_s = scaler.transform(X_va)

            # Target transform
            pt = PowerTransformer(method="yeo-johnson", standardize=False)
            y_tr_t = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()

            model = build_model()
            if mono:
                model.set_params(monotone_constraints=mono)
            model.fit(X_tr_s, y_tr_t)

            preds = model.predict(X_va_s)
            preds = pt.inverse_transform(preds.reshape(-1, 1)).ravel()
            preds = np.clip(preds, 0, 50)

            oof_pred[val_idx] = preds

            ss_res = np.sum((y_va - preds) ** 2)
            ss_tot = np.sum((y_va - y_va.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            mae = mean_absolute_error(y_va, preds)

            r2s.append(r2)
            maes.append(mae)

        r2_mean, r2_std = np.mean(r2s), np.std(r2s)
        mae_mean, mae_std = np.mean(maes), np.std(maes)

        logger.info(
            "  %s: R2=%.3f +/-%.3f  MAE=%.1f%% +/-%.1f%%  (%d folds)",
            name, r2_mean, r2_std, mae_mean, mae_std, len(r2s),
        )
        return {
            "r2_mean": r2_mean, "r2_std": r2_std,
            "mae_mean": mae_mean, "mae_std": mae_std,
            "oof_pred": oof_pred, "folds": r2s,
        }

    t1_result = _cv_eval(X1_keepa, y_keepa, "T1 (intrinsic only)", t1_features)
    t2_result = _cv_eval(X2_keepa, y_keepa, "T2 (Keepa features)", t2_feats_avail)

    # Combined T1+T2 features
    t12_features = t1_features + [f for f in t2_feats_avail if f not in t1_features]
    X12_keepa = pd.concat([X1_keepa, X2_keepa[[f for f in t2_feats_avail if f not in t1_features]]], axis=1)
    X12_keepa = X12_keepa.fillna(X12_keepa.median())
    t12_result = _cv_eval(X12_keepa, y_keepa, "T1+T2 combined", t12_features)

    # Simple ensemble: average of T1 and T2 OOF predictions
    oof_avg = (t1_result["oof_pred"] + t2_result["oof_pred"]) / 2
    valid = ~np.isnan(oof_avg)
    if valid.sum() > 0:
        ss_res = np.sum((y_keepa[valid] - oof_avg[valid]) ** 2)
        ss_tot = np.sum((y_keepa[valid] - y_keepa[valid].mean()) ** 2)
        avg_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        avg_mae = mean_absolute_error(y_keepa[valid], oof_avg[valid])
        logger.info("  AVG(T1,T2): R2=%.3f  MAE=%.1f%%  (simple average)", avg_r2, avg_mae)

    # -----------------------------------------------------------------------
    # T1 on ALL sets (for reference)
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("T1 ON ALL SETS (%d sets) - for reference", len(y_all))
    logger.info("=" * 70)

    X1_all = df_feat[t1_features].copy()
    for c in X1_all.columns:
        X1_all[c] = pd.to_numeric(X1_all[c], errors="coerce")
    X1_all = X1_all.fillna(X1_all.median())

    if has_groups:
        finite_all = np.isfinite(year_retired)
        g_all = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
        g_all[finite_all] = year_retired[finite_all].astype(int)
        n_unique_all = len(set(g_all))
        n_splits_all = min(5, n_unique_all)
        splitter_all = GroupKFold(n_splits=n_splits_all)
        split_args_all = (np.arange(len(y_all)), y_all, g_all)
    else:
        splitter_all = KFold(n_splits=5, shuffle=True, random_state=42)
        split_args_all = (np.arange(len(y_all)),)

    # Temporarily swap splitter for this eval
    orig_splitter, orig_split_args = splitter, split_args
    splitter, split_args = splitter_all, split_args_all
    _cv_eval(X1_all, y_all, "T1 (all sets)", t1_features)
    splitter, split_args = orig_splitter, orig_split_args

    # -----------------------------------------------------------------------
    # VERDICT
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("VERDICT")
    logger.info("=" * 70)

    results = {
        "T1": t1_result,
        "T2": t2_result,
        "T1+T2": t12_result,
    }
    best_name = max(results, key=lambda k: results[k]["r2_mean"])
    best = results[best_name]

    logger.info("Winner: %s (R2=%.3f, MAE=%.1f%%)", best_name, best["r2_mean"], best["mae_mean"])
    for name, res in results.items():
        delta_r2 = res["r2_mean"] - best["r2_mean"]
        marker = " <-- BEST" if name == best_name else ""
        logger.info(
            "  %s: R2=%.3f (delta=%.3f)  MAE=%.1f%%%s",
            name, res["r2_mean"], delta_r2, res["mae_mean"], marker,
        )

    # Per-fold comparison
    logger.info("")
    logger.info("Per-fold R2:")
    for i in range(len(t1_result["folds"])):
        t1_f = t1_result["folds"][i]
        t2_f = t2_result["folds"][i]
        t12_f = t12_result["folds"][i]
        winner = "T1" if t1_f >= t2_f and t1_f >= t12_f else "T2" if t2_f >= t12_f else "T1+T2"
        logger.info(
            "  Fold %d: T1=%.3f  T2=%.3f  T1+T2=%.3f  -> %s",
            i + 1, t1_f, t2_f, t12_f, winner,
        )


if __name__ == "__main__":
    main()
