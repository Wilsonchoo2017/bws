"""Apply and validate ML improvements from Exp 24 + BrickTalk gap analysis.

Tests:
1. Quick wins: depth=5, P1/P99 winsorization
2. BrickTalk: never_discounted binary from Keepa
3. Combined: all improvements together
4. Quantile intervals alongside best model

Run: python -m scripts.apply_improvements
"""
from __future__ import annotations

import logging
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer, StandardScaler

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main():
    t0 = time.time()

    from db.pg.engine import get_engine
    from services.ml.growth.features import (
        TIER1_FEATURES,
        engineer_intrinsic_features,
        engineer_keepa_features,
    )
    from services.ml.growth.feature_selection import select_features
    from services.ml.growth.model_selection import _get_monotonic_constraints
    from services.ml.pg_queries import load_growth_training_data, load_keepa_timelines

    engine = get_engine()
    df_raw = load_growth_training_data(engine)
    keepa_df = load_keepa_timelines(engine)

    y_all = df_raw["annual_growth_pct"].values.astype(float)
    year_retired = np.asarray(
        pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float
    )
    finite = np.isfinite(year_retired)
    groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
    groups[finite] = year_retired[finite].astype(int)

    # Feature engineering
    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y_all)
    )

    # Add Keepa features for never_discounted
    df_kp = engineer_keepa_features(df_feat, keepa_df)
    has_keepa = df_kp["kp_bb_premium"].notna() | df_kp["kp_below_rrp_pct"].notna()

    # Compute never_discounted binary
    shelf_life = pd.to_numeric(df_kp.get("shelf_life_months"), errors="coerce")
    max_discount = pd.to_numeric(df_kp.get("kp_max_discount"), errors="coerce")
    df_kp["never_discounted"] = np.where(
        has_keepa & shelf_life.notna() & (shelf_life > 6),
        (max_discount < 5).astype(float),
        np.nan,
    )
    # Also: was it discounted but only briefly?
    below_rrp_pct = pd.to_numeric(df_kp.get("kp_below_rrp_pct"), errors="coerce")
    df_kp["rarely_discounted"] = np.where(
        has_keepa,
        (below_rrp_pct < 10).astype(float),
        np.nan,
    )

    logger.info("=" * 70)
    logger.info("ML IMPROVEMENT VALIDATION")
    logger.info("=" * 70)
    logger.info("Sets: %d, Keepa: %d", len(y_all), has_keepa.sum())

    # Check never_discounted signal
    nd = df_kp["never_discounted"]
    nd_valid = nd.notna()
    if nd_valid.sum() > 50:
        nd_yes = (nd == 1) & nd_valid
        nd_no = (nd == 0) & nd_valid
        logger.info("")
        logger.info("never_discounted signal check:")
        logger.info("  Never discounted: n=%d, avg growth=%.1f%%",
                     nd_yes.sum(), y_all[nd_yes.values].mean())
        logger.info("  Was discounted:   n=%d, avg growth=%.1f%%",
                     nd_no.sum(), y_all[nd_no.values].mean())
        logger.info("  Coverage: %d / %d (%.0f%%)",
                     nd_valid.sum(), len(y_all), nd_valid.mean() * 100)
        corr = pd.Series(y_all[nd_valid.values]).corr(nd[nd_valid].astype(float))
        logger.info("  Correlation with growth: %.3f", corr)

    rd = df_kp["rarely_discounted"]
    rd_valid = rd.notna()
    if rd_valid.sum() > 50:
        rd_yes = (rd == 1) & rd_valid
        rd_no = (rd == 0) & rd_valid
        logger.info("")
        logger.info("rarely_discounted signal check (below_rrp < 10%%):")
        logger.info("  Rarely discounted: n=%d, avg growth=%.1f%%",
                     rd_yes.sum(), y_all[rd_yes.values].mean())
        logger.info("  Frequently discounted: n=%d, avg growth=%.1f%%",
                     rd_no.sum(), y_all[rd_no.values].mean())
        corr = pd.Series(y_all[rd_valid.values]).corr(rd[rd_valid].astype(float))
        logger.info("  Correlation with growth: %.3f", corr)

    # T1 features
    t1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X_raw = df_feat[t1_candidates].copy()
    for c in X_raw.columns:
        X_raw[c] = pd.to_numeric(X_raw[c], errors="coerce")
    t1_features = select_features(X_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
    if len(t1_features) < 5:
        t1_features = t1_candidates

    X_base = X_raw[t1_features].fillna(X_raw[t1_features].median())
    mono = _get_monotonic_constraints(t1_features)

    # Also build extended feature set with never_discounted
    t1_plus = list(t1_features)
    X_plus = X_base.copy()
    if nd_valid.sum() > 50:
        X_plus["never_discounted"] = df_kp["never_discounted"].values
        X_plus["never_discounted"] = X_plus["never_discounted"].fillna(
            X_plus["never_discounted"].median()
        )
        t1_plus.append("never_discounted")
    if rd_valid.sum() > 50:
        X_plus["rarely_discounted"] = df_kp["rarely_discounted"].values
        X_plus["rarely_discounted"] = X_plus["rarely_discounted"].fillna(
            X_plus["rarely_discounted"].median()
        )
        t1_plus.append("rarely_discounted")

    mono_plus = _get_monotonic_constraints(t1_plus)

    logger.info("")
    logger.info("Base features: %d", len(t1_features))
    logger.info("Extended features: %d (+never_discounted, +rarely_discounted)", len(t1_plus))

    # CV helper
    n_unique = len(set(groups))
    n_splits = min(5, n_unique)
    splitter = GroupKFold(n_splits=n_splits)

    def _cv(X_vals, y, name, depth=4, leaves=15, lr=0.05, n_est=300,
            winsorize_pct=None, mono_c=None, extra_params=None):
        import lightgbm as lgb
        r2s, maes = [], []
        oof = np.full(len(y), np.nan)

        for train_idx, val_idx in splitter.split(np.arange(len(y)), y, groups):
            X_tr, X_va = X_vals[train_idx], X_vals[val_idx]
            y_tr, y_va = y[train_idx], y[val_idx]

            if winsorize_pct:
                lo, hi = np.percentile(y_tr, [winsorize_pct[0], winsorize_pct[1]])
                y_tr = np.clip(y_tr, lo, hi)

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_va_s = scaler.transform(X_va)

            pt = PowerTransformer(method="yeo-johnson", standardize=False)
            y_tr_t = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()

            params = {
                "verbosity": -1, "random_state": 42, "n_jobs": 1,
                "objective": "huber", "n_estimators": n_est,
                "max_depth": depth, "num_leaves": leaves,
                "learning_rate": lr,
                "reg_alpha": 0.1, "reg_lambda": 1.0,
                "min_child_samples": 10,
            }
            if extra_params:
                params.update(extra_params)
            model = lgb.LGBMRegressor(**params)
            if mono_c:
                model.set_params(monotone_constraints=mono_c)
            model.fit(X_tr_s, y_tr_t)

            preds = model.predict(X_va_s)
            preds = pt.inverse_transform(preds.reshape(-1, 1)).ravel()
            preds = np.clip(preds, 0, 50)

            oof[val_idx] = preds
            ss_res = np.sum((y_va - preds) ** 2)
            ss_tot = np.sum((y_va - y_va.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            r2s.append(r2)
            maes.append(mean_absolute_error(y_va, preds))

        r2_mean, r2_std = np.mean(r2s), np.std(r2s)
        mae_mean = np.mean(maes)
        logger.info("  %-45s R2=%.3f +/-%.3f  MAE=%.1f%%",
                     name, r2_mean, r2_std, mae_mean)
        return {"r2": r2_mean, "r2_std": r2_std, "mae": mae_mean, "oof": oof, "folds": r2s}

    # -----------------------------------------------------------------------
    # A. BASELINE
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("A. BASELINE vs QUICK WINS")
    logger.info("=" * 70)

    baseline = _cv(X_base.values, y_all, "Baseline (d=4, P5/P95, current)",
                   depth=4, winsorize_pct=(5, 95), mono_c=mono)

    # Quick win 1: depth=5
    d5 = _cv(X_base.values, y_all, "depth=5, P5/P95",
             depth=5, leaves=31, winsorize_pct=(5, 95), mono_c=mono)

    # Quick win 2: P1/P99
    p1 = _cv(X_base.values, y_all, "depth=4, P1/P99",
             depth=4, winsorize_pct=(1, 99), mono_c=mono)

    # Combined quick wins
    combined_qw = _cv(X_base.values, y_all, "depth=5 + P1/P99 (combined)",
                      depth=5, leaves=31, winsorize_pct=(1, 99), mono_c=mono)

    # depth=6 for reference
    d6 = _cv(X_base.values, y_all, "depth=6, P1/P99",
             depth=6, leaves=63, winsorize_pct=(1, 99), mono_c=mono)

    # -----------------------------------------------------------------------
    # B. BRICKTALK FEATURES
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("B. BRICKTALK FEATURES (never_discounted, rarely_discounted)")
    logger.info("=" * 70)

    # Extended features with best config
    ext = _cv(X_plus.values, y_all, "depth=5 + P1/P99 + BrickTalk features",
              depth=5, leaves=31, winsorize_pct=(1, 99), mono_c=mono_plus)

    # Just never_discounted
    X_nd_only = X_base.copy()
    if nd_valid.sum() > 50:
        X_nd_only["never_discounted"] = df_kp["never_discounted"].values
        X_nd_only["never_discounted"] = X_nd_only["never_discounted"].fillna(
            X_nd_only["never_discounted"].median()
        )
        t1_nd = list(t1_features) + ["never_discounted"]
        mono_nd = _get_monotonic_constraints(t1_nd)
        _cv(X_nd_only.values, y_all, "depth=5 + P1/P99 + never_discounted only",
            depth=5, leaves=31, winsorize_pct=(1, 99), mono_c=mono_nd)

    # -----------------------------------------------------------------------
    # C. ADDITIONAL MODEL TWEAKS
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("C. ADDITIONAL TWEAKS")
    logger.info("=" * 70)

    # More trees + lower LR (reduce overfit)
    _cv(X_base.values, y_all, "d=5, P1/P99, lr=0.03, n=500",
        depth=5, leaves=31, lr=0.03, n_est=500,
        winsorize_pct=(1, 99), mono_c=mono)

    _cv(X_base.values, y_all, "d=5, P1/P99, lr=0.02, n=800",
        depth=5, leaves=31, lr=0.02, n_est=800,
        winsorize_pct=(1, 99), mono_c=mono)

    # Feature sampling to reduce overfit
    _cv(X_base.values, y_all, "d=5, P1/P99, colsample=0.7",
        depth=5, leaves=31, winsorize_pct=(1, 99), mono_c=mono,
        extra_params={"colsample_bytree": 0.7})

    _cv(X_base.values, y_all, "d=5, P1/P99, subsample=0.8",
        depth=5, leaves=31, winsorize_pct=(1, 99), mono_c=mono,
        extra_params={"subsample": 0.8, "subsample_freq": 1})

    # Combined anti-overfit
    _cv(X_base.values, y_all, "d=5, P1/P99, col=0.7+sub=0.8+lr=0.03",
        depth=5, leaves=31, lr=0.03, n_est=500,
        winsorize_pct=(1, 99), mono_c=mono,
        extra_params={"colsample_bytree": 0.7, "subsample": 0.8, "subsample_freq": 1})

    # -----------------------------------------------------------------------
    # D. BEST CONFIG: RESIDUAL ANALYSIS
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("D. RESIDUAL ANALYSIS (best config)")
    logger.info("=" * 70)

    # Use the best result so far
    best_oof = combined_qw["oof"]
    valid = ~np.isnan(best_oof)

    logger.info("")
    logger.info("  Errors by growth bucket (depth=5 + P1/P99):")
    for lo, hi, label in [(0, 5, "0-5% (losers)"), (5, 10, "5-10%"),
                           (10, 15, "10-15%"), (15, 20, "15-20%"),
                           (20, 100, "20%+ (winners)")]:
        mask = (y_all[valid] >= lo) & (y_all[valid] < hi)
        if mask.sum() < 5:
            continue
        mae_b = np.mean(np.abs(y_all[valid][mask] - best_oof[valid][mask]))
        bias = np.mean(best_oof[valid][mask] - y_all[valid][mask])
        logger.info("    %-18s n=%3d  MAE=%.1f%%  bias=%+.1f%%",
                     label, mask.sum(), mae_b, bias)

    # -----------------------------------------------------------------------
    # E. QUANTILE INTERVALS (best config)
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("E. QUANTILE INTERVALS (alongside best model)")
    logger.info("=" * 70)

    import lightgbm as lgb
    quantiles = [0.10, 0.50, 0.90]
    oof_q = {q: np.full(len(y_all), np.nan) for q in quantiles}

    for train_idx, val_idx in splitter.split(np.arange(len(y_all)), y_all, groups):
        X_tr, X_va = X_base.values[train_idx], X_base.values[val_idx]
        y_tr, y_va = y_all[train_idx], y_all[val_idx]

        lo_w, hi_w = np.percentile(y_tr, [1, 99])
        y_tr_w = np.clip(y_tr, lo_w, hi_w)

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_va_s = scaler.transform(X_va)

        for q in quantiles:
            model = lgb.LGBMRegressor(
                objective="quantile", alpha=q,
                verbosity=-1, random_state=42, n_jobs=1,
                n_estimators=300, max_depth=5, num_leaves=31,
                learning_rate=0.05, reg_alpha=0.1, reg_lambda=1.0,
                min_child_samples=10,
            )
            model.fit(X_tr_s, y_tr_w)
            oof_q[q][val_idx] = model.predict(X_va_s)

    # Calibration
    logger.info("  Quantile calibration:")
    for q in quantiles:
        v = ~np.isnan(oof_q[q])
        actual_below = np.mean(y_all[v] < oof_q[q][v])
        logger.info("    P%02d: expected=%.0f%%, actual=%.1f%%",
                     int(q * 100), q * 100, actual_below * 100)

    # Coverage
    v = ~np.isnan(oof_q[0.10]) & ~np.isnan(oof_q[0.90])
    p10, p90 = oof_q[0.10][v], oof_q[0.90][v]
    y_v = y_all[v]
    coverage = np.mean((y_v >= p10) & (y_v <= p90))
    width = np.mean(p90 - p10)
    logger.info("")
    logger.info("  80%% interval: coverage=%.1f%%, avg width=%.1f%%", coverage * 100, width)

    # Example intervals
    logger.info("")
    logger.info("  Example predictions (best model + intervals):")
    sample_idx = np.random.RandomState(42).choice(np.where(v)[0], 10, replace=False)
    logger.info("  %-8s %-30s %8s %8s %8s %8s", "Set", "Title", "Actual", "Pred", "P10", "P90")
    logger.info("  " + "-" * 88)
    for i in sorted(sample_idx, key=lambda x: -best_oof[x]):
        title = str(df_raw.iloc[i].get("title", ""))[:29]
        sn = str(df_raw.iloc[i]["set_number"])
        logger.info("  %-8s %-30s %7.1f%% %7.1f%% %7.1f%% %7.1f%%",
                     sn, title, y_all[i], best_oof[i], oof_q[0.10][i], oof_q[0.90][i])

    # -----------------------------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    logger.info("")
    logger.info("  %-40s %8s %8s %8s", "Config", "R2", "vs Base", "MAE")
    logger.info("  " + "-" * 70)
    configs = [
        ("Baseline (d=4, P5/P95)", baseline),
        ("+ depth=5", d5),
        ("+ P1/P99", p1),
        ("depth=5 + P1/P99", combined_qw),
        ("depth=6 + P1/P99", d6),
        ("depth=5 + P1/P99 + BrickTalk", ext),
    ]
    for name, r in configs:
        delta = r["r2"] - baseline["r2"]
        logger.info("  %-40s %7.3f  %+7.3f  %6.1f%%", name, r["r2"], delta, r["mae"])

    elapsed = time.time() - t0
    logger.info("")
    logger.info("Done in %.0f seconds", elapsed)


if __name__ == "__main__":
    main()
