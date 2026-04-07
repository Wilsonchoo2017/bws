"""Fast ML improvement scan — test ideas cheaply before committing.

Tests: overfit/underfit diagnosis, preprocessing variants, quantile regression,
theme-specific models, post-processing, residual analysis.

All use simple 5-fold GroupKFold with NO Optuna tuning.
Run: python -m scripts.ml_improvement_scan
"""
from __future__ import annotations

import logging
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold, KFold, learning_curve
from sklearn.preprocessing import PowerTransformer, QuantileTransformer, StandardScaler

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup():
    """Load data and prepare features. Returns everything needed."""
    from db.pg.engine import get_engine
    from services.ml.growth.features import (
        TIER1_FEATURES,
        engineer_intrinsic_features,
    )
    from services.ml.growth.feature_selection import select_features
    from services.ml.growth.model_selection import build_model

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

    # Groups
    finite = np.isfinite(year_retired)
    groups = np.full(len(y_all), int(np.nanmedian(year_retired)), dtype=int)
    groups[finite] = year_retired[finite].astype(int)

    return df_raw, df_feat, X, y_all, groups, t1_features


def _cv_score(X_vals, y, groups, model_factory, target_transform=None,
              clip_range=None, winsorize=None, name=""):
    """Quick 5-fold GroupKFold CV. Returns dict with R2, MAE, per-fold."""
    from services.ml.growth.model_selection import _get_monotonic_constraints
    n_unique = len(set(groups))
    n_splits = min(5, n_unique)
    splitter = GroupKFold(n_splits=n_splits)

    r2s, maes = [], []
    oof = np.full(len(y), np.nan)

    for train_idx, val_idx in splitter.split(np.arange(len(y)), y, groups):
        X_tr, X_va = X_vals[train_idx], X_vals[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]

        # Winsorize training target
        if winsorize:
            lo, hi = np.percentile(y_tr, [winsorize[0], winsorize[1]])
            y_tr = np.clip(y_tr, lo, hi)

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_va_s = scaler.transform(X_va)

        # Target transform
        pt = None
        if target_transform == "yeo-johnson":
            pt = PowerTransformer(method="yeo-johnson", standardize=False)
            y_tr_t = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()
        elif target_transform == "quantile":
            pt = QuantileTransformer(output_distribution="normal", random_state=42)
            y_tr_t = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()
        elif target_transform == "log1p":
            y_tr_t = np.log1p(np.clip(y_tr, 0, None))
        else:
            y_tr_t = y_tr

        model = model_factory()
        model.fit(X_tr_s, y_tr_t)
        preds = model.predict(X_va_s)

        # Inverse transform
        if pt is not None:
            preds = pt.inverse_transform(preds.reshape(-1, 1)).ravel()
        elif target_transform == "log1p":
            preds = np.expm1(preds)

        if clip_range:
            preds = np.clip(preds, clip_range[0], clip_range[1])

        oof[val_idx] = preds
        ss_res = np.sum((y_va - preds) ** 2)
        ss_tot = np.sum((y_va - y_va.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        maes.append(mean_absolute_error(y_va, preds))
        r2s.append(r2)

    return {
        "name": name,
        "r2_mean": np.mean(r2s), "r2_std": np.std(r2s),
        "mae_mean": np.mean(maes), "mae_std": np.std(maes),
        "folds": r2s, "oof": oof,
    }


def _print_result(r):
    logger.info(
        "  %-40s R2=%.3f +/-%.3f  MAE=%.1f%% +/-%.1f%%",
        r["name"], r["r2_mean"], r["r2_std"], r["mae_mean"], r["mae_std"],
    )


# ---------------------------------------------------------------------------
# 1. OVERFIT / UNDERFIT DIAGNOSIS
# ---------------------------------------------------------------------------

def diagnose_overfit_underfit(X, y, groups, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("1. OVERFIT / UNDERFIT DIAGNOSIS")
    logger.info("=" * 70)

    from services.ml.growth.model_selection import build_model, _get_monotonic_constraints

    mono = _get_monotonic_constraints(t1_features)

    # Train R2 vs CV R2
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X.values)

    pt = PowerTransformer(method="yeo-johnson", standardize=False)
    y_t = pt.fit_transform(y.reshape(-1, 1)).ravel()

    model = build_model()
    if mono:
        model.set_params(monotone_constraints=mono)
    model.fit(X_s, y_t)
    train_preds = pt.inverse_transform(model.predict(X_s).reshape(-1, 1)).ravel()
    ss_res = np.sum((y - train_preds) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    train_r2 = 1 - ss_res / ss_tot

    baseline = _cv_score(
        X.values, y, groups,
        lambda: _build_with_mono(t1_features),
        target_transform="yeo-johnson", name="Baseline (current)",
    )

    gap = train_r2 - baseline["r2_mean"]
    logger.info("  Train R2:     %.3f", train_r2)
    logger.info("  CV R2:        %.3f +/-%.3f", baseline["r2_mean"], baseline["r2_std"])
    logger.info("  Gap:          %.3f", gap)
    logger.info("")

    if gap > 0.25:
        logger.info("  DIAGNOSIS: OVERFITTING (gap > 0.25)")
        logger.info("  -> More regularization, fewer features, more data would help")
    elif gap < 0.10 and baseline["r2_mean"] < 0.5:
        logger.info("  DIAGNOSIS: UNDERFITTING (low R2, small gap)")
        logger.info("  -> More features, more complex model, or better features needed")
    elif gap < 0.15:
        logger.info("  DIAGNOSIS: GOOD FIT (gap < 0.15)")
        logger.info("  -> Model is well-calibrated, focus on feature engineering")
    else:
        logger.info("  DIAGNOSIS: MILD OVERFIT (gap 0.15-0.25)")
        logger.info("  -> Some regularization might help but not critical")

    # Learning curve (sample sizes)
    logger.info("")
    logger.info("  Learning curve (how much does more data help?):")
    fractions = [0.2, 0.4, 0.6, 0.8, 1.0]
    for frac in fractions:
        n = int(len(y) * frac)
        idx = np.random.RandomState(42).choice(len(y), n, replace=False)
        sub_r = _cv_score(
            X.values[idx], y[idx], groups[idx],
            lambda: _build_with_mono(t1_features),
            target_transform="yeo-johnson", name=f"n={n}",
        )
        logger.info("    n=%4d: R2=%.3f  MAE=%.1f%%", n, sub_r["r2_mean"], sub_r["mae_mean"])

    return baseline


def _build_with_mono(features):
    from services.ml.growth.model_selection import build_model, _get_monotonic_constraints
    mono = _get_monotonic_constraints(features)
    m = build_model()
    if mono:
        m.set_params(monotone_constraints=mono)
    return m


# ---------------------------------------------------------------------------
# 2. PREPROCESSING EXPERIMENTS
# ---------------------------------------------------------------------------

def test_preprocessing(X, y, groups, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("2. PREPROCESSING EXPERIMENTS")
    logger.info("=" * 70)

    factory = lambda: _build_with_mono(t1_features)
    results = []

    # Baseline
    r = _cv_score(X.values, y, groups, factory, target_transform="yeo-johnson",
                  name="Baseline (Yeo-Johnson)")
    results.append(r)
    _print_result(r)

    # No target transform
    r = _cv_score(X.values, y, groups, factory, target_transform=None,
                  name="No target transform")
    results.append(r)
    _print_result(r)

    # log1p target
    r = _cv_score(X.values, y, groups, factory, target_transform="log1p",
                  name="log1p target")
    results.append(r)
    _print_result(r)

    # Quantile target transform
    r = _cv_score(X.values, y, groups, factory, target_transform="quantile",
                  name="Quantile target transform")
    results.append(r)
    _print_result(r)

    # Winsorize variants
    for lo, hi in [(1, 99), (2, 98), (5, 95), (10, 90)]:
        r = _cv_score(X.values, y, groups, factory, target_transform="yeo-johnson",
                      winsorize=(lo, hi), name=f"Winsorize P{lo}/P{hi} + YJ")
        results.append(r)
        _print_result(r)

    # Clip predictions
    r = _cv_score(X.values, y, groups, factory, target_transform="yeo-johnson",
                  clip_range=(0, 40), name="Clip preds [0, 40]")
    results.append(r)
    _print_result(r)

    r = _cv_score(X.values, y, groups, factory, target_transform="yeo-johnson",
                  clip_range=(0, 30), name="Clip preds [0, 30]")
    results.append(r)
    _print_result(r)

    return results


# ---------------------------------------------------------------------------
# 3. MODEL COMPLEXITY EXPERIMENTS
# ---------------------------------------------------------------------------

def test_model_complexity(X, y, groups, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("3. MODEL COMPLEXITY (quick sweep)")
    logger.info("=" * 70)

    from services.ml.growth.model_selection import _get_monotonic_constraints
    mono = _get_monotonic_constraints(t1_features)
    results = []

    configs = [
        ("depth=3, leaf=8 (simpler)", {"max_depth": 3, "num_leaves": 8, "n_estimators": 300}),
        ("depth=4, leaf=15 (current)", {"max_depth": 4, "num_leaves": 15, "n_estimators": 300}),
        ("depth=5, leaf=31 (deeper)", {"max_depth": 5, "num_leaves": 31, "n_estimators": 300}),
        ("depth=6, leaf=63 (complex)", {"max_depth": 6, "num_leaves": 63, "n_estimators": 300}),
        ("depth=4, lr=0.01 (slower)", {"max_depth": 4, "num_leaves": 15, "n_estimators": 500, "learning_rate": 0.01}),
        ("depth=4, lr=0.1 (faster)", {"max_depth": 4, "num_leaves": 15, "n_estimators": 200, "learning_rate": 0.1}),
        ("depth=4, reg_high", {"max_depth": 4, "num_leaves": 15, "reg_alpha": 1.0, "reg_lambda": 5.0}),
        ("depth=4, min_child=20", {"max_depth": 4, "num_leaves": 15, "min_child_samples": 20}),
        ("depth=4, min_child=30", {"max_depth": 4, "num_leaves": 15, "min_child_samples": 30}),
    ]

    for name, params in configs:
        def _factory(p=params):
            import lightgbm as lgb
            defaults = {
                "verbosity": -1, "random_state": 42, "n_jobs": 1,
                "objective": "huber", "n_estimators": 300,
                "max_depth": 4, "num_leaves": 15, "learning_rate": 0.05,
                "reg_alpha": 0.1, "reg_lambda": 1.0, "min_child_samples": 10,
            }
            defaults.update(p)
            m = lgb.LGBMRegressor(**defaults)
            if mono:
                m.set_params(monotone_constraints=mono)
            return m

        r = _cv_score(X.values, y, groups, _factory,
                      target_transform="yeo-johnson", name=name)
        results.append(r)
        _print_result(r)

    return results


# ---------------------------------------------------------------------------
# 4. QUANTILE REGRESSION
# ---------------------------------------------------------------------------

def test_quantile_regression(X, y, groups, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("4. QUANTILE REGRESSION (P10/P50/P90)")
    logger.info("=" * 70)

    from services.ml.growth.model_selection import _get_monotonic_constraints
    mono = _get_monotonic_constraints(t1_features)

    n_unique = len(set(groups))
    n_splits = min(5, n_unique)
    splitter = GroupKFold(n_splits=n_splits)

    quantiles = [0.10, 0.25, 0.50, 0.75, 0.90]
    oof_quantiles = {q: np.full(len(y), np.nan) for q in quantiles}

    for train_idx, val_idx in splitter.split(np.arange(len(y)), y, groups):
        X_tr, X_va = X.values[train_idx], X.values[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_va_s = scaler.transform(X_va)

        for q in quantiles:
            try:
                import lightgbm as lgb
                # Note: monotone_constraints not supported with quantile objective
                model = lgb.LGBMRegressor(
                    objective="quantile", alpha=q,
                    verbosity=-1, random_state=42, n_jobs=1,
                    n_estimators=300, max_depth=4, num_leaves=15,
                    learning_rate=0.05, reg_alpha=0.1, reg_lambda=1.0,
                    min_child_samples=10,
                )
            except ImportError:
                from sklearn.ensemble import GradientBoostingRegressor
                model = GradientBoostingRegressor(
                    loss="quantile", alpha=q, n_estimators=300,
                    max_depth=4, random_state=42,
                )

            model.fit(X_tr_s, y_tr)
            preds = model.predict(X_va_s)
            oof_quantiles[q][val_idx] = preds

    # Evaluate quantile calibration
    logger.info("")
    logger.info("  Quantile calibration (% of actuals below predicted quantile):")
    for q in quantiles:
        valid = ~np.isnan(oof_quantiles[q])
        actual_below = np.mean(y[valid] < oof_quantiles[q][valid])
        logger.info("    P%02d: expected=%.0f%%, actual=%.1f%% (delta=%.1f%%)",
                     int(q * 100), q * 100, actual_below * 100, (actual_below - q) * 100)

    # Interval coverage
    valid = ~np.isnan(oof_quantiles[0.10]) & ~np.isnan(oof_quantiles[0.90])
    p10 = oof_quantiles[0.10][valid]
    p90 = oof_quantiles[0.90][valid]
    y_v = y[valid]
    coverage_80 = np.mean((y_v >= p10) & (y_v <= p90))
    avg_width = np.mean(p90 - p10)

    logger.info("")
    logger.info("  80%% prediction interval (P10-P90):")
    logger.info("    Coverage: %.1f%% (target: 80%%)", coverage_80 * 100)
    logger.info("    Avg width: %.1f%%", avg_width)

    # P50 as point estimate vs mean regression
    p50_preds = oof_quantiles[0.50]
    valid50 = ~np.isnan(p50_preds)
    ss_res = np.sum((y[valid50] - p50_preds[valid50]) ** 2)
    ss_tot = np.sum((y[valid50] - y[valid50].mean()) ** 2)
    p50_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    p50_mae = mean_absolute_error(y[valid50], p50_preds[valid50])

    logger.info("")
    logger.info("  P50 as point estimate:")
    logger.info("    R2=%.3f, MAE=%.1f%%", p50_r2, p50_mae)
    logger.info("    (Compare with mean regression baseline for R2 delta)")

    return oof_quantiles


# ---------------------------------------------------------------------------
# 5. THEME-SPECIFIC MODELS
# ---------------------------------------------------------------------------

def test_theme_models(df_raw, df_feat, X, y, groups, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("5. THEME-SPECIFIC MODELS")
    logger.info("=" * 70)

    themes = df_raw["theme"].values
    unique_themes, counts = np.unique(themes, return_counts=True)
    big_themes = unique_themes[counts >= 30]

    logger.info("  Themes with 30+ sets: %d / %d", len(big_themes), len(unique_themes))

    from services.ml.growth.model_selection import _get_monotonic_constraints
    mono = _get_monotonic_constraints(t1_features)

    results = []

    # Global model baseline on each theme
    global_baseline = _cv_score(
        X.values, y, groups,
        lambda: _build_with_mono(t1_features),
        target_transform="yeo-johnson", name="Global (all themes)",
    )

    for theme in sorted(big_themes):
        mask = themes == theme
        n = mask.sum()
        y_theme = y[mask]

        if np.std(y_theme) < 0.5:
            continue

        # Can we even do GroupKFold?
        g_theme = groups[mask]
        n_unique_g = len(set(g_theme))
        if n_unique_g < 3:
            continue

        # Theme-specific model
        try:
            theme_r = _cv_score(
                X.values[mask], y_theme, g_theme,
                lambda: _build_with_mono(t1_features),
                target_transform="yeo-johnson",
                name=f"{theme} (n={n})",
            )
        except Exception:
            continue

        # Global model evaluated on this theme's sets only
        oof_global = global_baseline["oof"][mask]
        valid = ~np.isnan(oof_global)
        if valid.sum() < 5:
            continue
        ss_res = np.sum((y_theme[valid] - oof_global[valid]) ** 2)
        ss_tot = np.sum((y_theme[valid] - y_theme[valid].mean()) ** 2)
        global_r2_theme = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        delta = theme_r["r2_mean"] - global_r2_theme
        winner = "THEME" if delta > 0.05 else "GLOBAL" if delta < -0.05 else "TIE"

        logger.info(
            "  %-22s n=%3d  theme_R2=%.3f  global_R2=%.3f  delta=%+.3f  %s",
            theme, n, theme_r["r2_mean"], global_r2_theme, delta, winner,
        )
        results.append({
            "theme": theme, "n": n,
            "theme_r2": theme_r["r2_mean"],
            "global_r2": global_r2_theme,
            "delta": delta,
        })

    # Summary
    if results:
        theme_wins = sum(1 for r in results if r["delta"] > 0.05)
        global_wins = sum(1 for r in results if r["delta"] < -0.05)
        ties = len(results) - theme_wins - global_wins
        logger.info("")
        logger.info("  Summary: Theme wins=%d, Global wins=%d, Ties=%d", theme_wins, global_wins, ties)
        avg_delta = np.mean([r["delta"] for r in results])
        logger.info("  Avg delta: %+.3f", avg_delta)
        if avg_delta < 0:
            logger.info("  VERDICT: Theme-specific models HURT — not enough data per theme")
        elif avg_delta > 0.05:
            logger.info("  VERDICT: Theme-specific models HELP — consider hierarchical approach")
        else:
            logger.info("  VERDICT: Theme-specific models are NEUTRAL — not worth the complexity")

    return results


# ---------------------------------------------------------------------------
# 6. RESIDUAL ANALYSIS
# ---------------------------------------------------------------------------

def analyze_residuals(df_raw, X, y, groups, t1_features, baseline_oof):
    logger.info("")
    logger.info("=" * 70)
    logger.info("6. RESIDUAL ANALYSIS (where does the model fail?)")
    logger.info("=" * 70)

    valid = ~np.isnan(baseline_oof)
    residuals = y[valid] - baseline_oof[valid]
    abs_res = np.abs(residuals)

    logger.info("  Residual stats:")
    logger.info("    Mean: %.2f%%", np.mean(residuals))
    logger.info("    Std:  %.2f%%", np.std(residuals))
    logger.info("    MAE:  %.2f%%", np.mean(abs_res))
    logger.info("    P90 error: %.2f%%", np.percentile(abs_res, 90))

    # By growth bucket
    logger.info("")
    logger.info("  Errors by actual growth bucket:")
    y_v = y[valid]
    pred_v = baseline_oof[valid]
    for lo, hi, label in [(0, 5, "0-5% (losers)"), (5, 10, "5-10%"),
                           (10, 15, "10-15%"), (15, 20, "15-20%"),
                           (20, 100, "20%+ (winners)")]:
        mask = (y_v >= lo) & (y_v < hi)
        if mask.sum() < 5:
            continue
        mae_b = np.mean(np.abs(y_v[mask] - pred_v[mask]))
        bias = np.mean(pred_v[mask] - y_v[mask])
        logger.info("    %-18s n=%3d  MAE=%.1f%%  bias=%+.1f%%", label, mask.sum(), mae_b, bias)

    # By theme (biggest errors)
    themes = df_raw["theme"].values[valid]
    theme_errors = {}
    for theme in set(themes):
        t_mask = themes == theme
        if t_mask.sum() < 5:
            continue
        theme_errors[theme] = {
            "n": t_mask.sum(),
            "mae": np.mean(np.abs(residuals[t_mask])),
            "bias": np.mean(pred_v[t_mask] - y_v[t_mask]),
        }

    logger.info("")
    logger.info("  Worst themes by MAE:")
    for theme, stats in sorted(theme_errors.items(), key=lambda x: -x[1]["mae"])[:10]:
        logger.info("    %-22s n=%3d  MAE=%.1f%%  bias=%+.1f%%",
                     theme, stats["n"], stats["mae"], stats["bias"])


# ---------------------------------------------------------------------------
# 7. POST-PROCESSING IDEAS
# ---------------------------------------------------------------------------

def test_postprocessing(X, y, groups, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("7. POST-PROCESSING IDEAS")
    logger.info("=" * 70)

    factory = lambda: _build_with_mono(t1_features)

    # Baseline OOF predictions
    baseline = _cv_score(X.values, y, groups, factory,
                         target_transform="yeo-johnson", name="Baseline")
    oof = baseline["oof"]
    valid = ~np.isnan(oof)

    # a) Isotonic regression (already in production, but let's measure impact)
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import cross_val_predict, KFold

    iso = IsotonicRegression(out_of_bounds="clip")
    # Nested CV for isotonic: use inner CV to avoid leakage
    oof_iso = np.full(len(y), np.nan)
    kf = KFold(5, shuffle=True, random_state=42)
    for tr_i, va_i in kf.split(np.arange(valid.sum())):
        valid_idx = np.where(valid)[0]
        iso_tr = valid_idx[tr_i]
        iso_va = valid_idx[va_i]
        iso.fit(oof[iso_tr], y[iso_tr])
        oof_iso[iso_va] = iso.predict(oof[iso_va])

    valid_iso = ~np.isnan(oof_iso)
    if valid_iso.sum() > 0:
        ss_res = np.sum((y[valid_iso] - oof_iso[valid_iso]) ** 2)
        ss_tot = np.sum((y[valid_iso] - y[valid_iso].mean()) ** 2)
        iso_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        iso_mae = mean_absolute_error(y[valid_iso], oof_iso[valid_iso])
        logger.info("  Isotonic calibration:   R2=%.3f  MAE=%.1f%%", iso_r2, iso_mae)

    # b) Shrink toward theme mean
    logger.info("")
    logger.info("  Shrinkage toward theme mean (blend prediction with theme prior):")
    # This needs theme info - skip if complex
    logger.info("    (Would require theme mapping in this context - conceptual only)")
    logger.info("    Idea: pred_final = alpha * model_pred + (1-alpha) * theme_avg_growth")
    logger.info("    Worth testing if theme-specific models are neutral")

    # c) Prediction clipping at percentile-based bounds
    for clip_pct in [(1, 99), (5, 95)]:
        lo_clip = np.percentile(y, clip_pct[0])
        hi_clip = np.percentile(y, clip_pct[1])
        oof_clipped = np.clip(oof[valid], lo_clip, hi_clip)
        ss_res = np.sum((y[valid] - oof_clipped) ** 2)
        ss_tot = np.sum((y[valid] - y[valid].mean()) ** 2)
        clip_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        clip_mae = mean_absolute_error(y[valid], oof_clipped)
        logger.info("  Clip to P%d/P%d [%.1f, %.1f]: R2=%.3f  MAE=%.1f%%",
                     clip_pct[0], clip_pct[1], lo_clip, hi_clip, clip_r2, clip_mae)


# ---------------------------------------------------------------------------
# 8. ALTERNATIVE LOSS FUNCTIONS
# ---------------------------------------------------------------------------

def test_loss_functions(X, y, groups, t1_features):
    logger.info("")
    logger.info("=" * 70)
    logger.info("8. LOSS FUNCTION COMPARISON")
    logger.info("=" * 70)

    from services.ml.growth.model_selection import _get_monotonic_constraints
    mono = _get_monotonic_constraints(t1_features)

    losses = [
        ("huber (current)", "huber"),
        ("mse", "regression"),
        ("mae", "mae"),
        ("poisson", "poisson"),
        ("gamma", "gamma"),
    ]

    for name, objective in losses:
        def _factory(obj=objective):
            import lightgbm as lgb
            m = lgb.LGBMRegressor(
                verbosity=-1, random_state=42, n_jobs=1,
                objective=obj, n_estimators=300,
                max_depth=4, num_leaves=15, learning_rate=0.05,
                reg_alpha=0.1, reg_lambda=1.0, min_child_samples=10,
            )
            if mono:
                m.set_params(monotone_constraints=mono)
            return m

        try:
            # Poisson/gamma need positive targets
            y_adj = y
            if objective in ("poisson", "gamma"):
                y_adj = np.clip(y, 0.01, None)

            r = _cv_score(X.values, y_adj, groups, _factory,
                          target_transform="yeo-johnson", name=name)
            _print_result(r)
        except Exception as e:
            logger.info("  %-40s FAILED: %s", name, str(e)[:60])


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    logger.info("ML Improvement Scan — fast diagnostics before committing")
    logger.info("=" * 70)

    df_raw, df_feat, X, y, groups, t1_features = _setup()
    logger.info("Data: %d sets, %d features", len(y), len(t1_features))
    logger.info("Target: mean=%.1f%%, median=%.1f%%, std=%.1f%%",
                np.mean(y), np.median(y), np.std(y))

    # Run all diagnostics
    baseline = diagnose_overfit_underfit(X, y, groups, t1_features)
    test_preprocessing(X, y, groups, t1_features)
    test_model_complexity(X, y, groups, t1_features)
    test_quantile_regression(X, y, groups, t1_features)
    test_theme_models(df_raw, df_feat, X, y, groups, t1_features)
    analyze_residuals(df_raw, X, y, groups, t1_features, baseline["oof"])
    test_postprocessing(X, y, groups, t1_features)
    test_loss_functions(X, y, groups, t1_features)

    elapsed = time.time() - t0
    logger.info("")
    logger.info("=" * 70)
    logger.info("DONE in %.0f seconds", elapsed)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
