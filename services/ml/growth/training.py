"""Growth model training pipeline.

Architecture:
  - Regressor: LightGBM on ALL sets — predicts growth % (ranking signal)
  - Classifier: LightGBM on ALL sets — P(avoid) confidence signal
  The regressor ranks sets. The classifier provides downside confidence.
  Combined at prediction time, not training time.

Also trains Tier 2 (+ Keepa features) when Amazon data is available.
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from config.ml import FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT, MLPipelineConfig
from services.ml.growth.classifier import (
    TrainedClassifier,
    train_classifier,
)
from services.ml.growth.evaluation import CIRCULAR_FEATURES
from services.ml.growth.feature_selection import select_features
from services.ml.growth.features import (
    TIER1_FEATURES,
    TIER2_FEATURES,
    engineer_intrinsic_features,
    engineer_keepa_features,
)
from services.ml.growth.model_selection import (
    CVResult,
    _get_monotonic_constraints,
    build_model,
    clip_outliers,
    compute_recency_weights,
    cross_validate_model,
    temporal_cross_validate,
    tune_and_select,
    winsorize_targets,
)
from services.ml.growth.types import KellyCalibration, TrainedEnsemble, TrainedGrowthModel
from services.ml.helpers import compute_cutoff_dates

logger = logging.getLogger(__name__)

_cfg = MLPipelineConfig()

# Kelly parameters
KELLY_HURDLE = 8.0  # minimum return to call a "win"
KELLY_FRACTION = 0.5  # half-Kelly (conservative)
KELLY_MAX_POSITION = 0.25  # max 25% in one set
N_KELLY_SIMS = 10_000


def _compute_kelly_calibration(
    y_actual: np.ndarray,
    y_cv_pred: np.ndarray,
    hurdle: float = KELLY_HURDLE,
) -> KellyCalibration:
    """Compute Kelly calibration from CV residuals.

    Builds a lookup table: for each predicted growth level, what's the
    win probability and optimal Kelly fraction?
    """
    residuals = y_actual - y_cv_pred
    res_std = float(np.std(residuals))
    res_mean = float(np.mean(residuals))

    # Pre-compute Kelly table at growth levels 0-40%
    rng = np.random.default_rng(42)
    table: list[tuple[float, float, float]] = []

    for pred_growth in range(0, 41, 2):
        # Simulate actual returns: predicted + noise from residual distribution
        sims = pred_growth + rng.normal(res_mean, res_std, N_KELLY_SIMS)

        wins = sims[sims > hurdle]
        losses = sims[sims <= hurdle]

        win_prob = len(wins) / N_KELLY_SIMS
        avg_win = float(np.mean(wins - hurdle)) if len(wins) > 0 else 0.0
        avg_loss = float(np.mean(hurdle - losses)) if len(losses) > 0 else 0.001

        # Kelly: f* = (b*p - q) / b where b = avg_win/avg_loss
        if avg_loss > 0 and avg_win > 0:
            b = avg_win / avg_loss
            q = 1.0 - win_prob
            raw_kelly = max(0.0, (b * win_prob - q) / b)
        elif avg_win > 0:
            raw_kelly = 1.0
        else:
            raw_kelly = 0.0

        half_kelly = min(raw_kelly * KELLY_FRACTION, KELLY_MAX_POSITION)
        table.append((float(pred_growth), round(win_prob, 4), round(half_kelly, 4)))

    logger.info(
        "Kelly calibration: residual_std=%.1f%%, table entries=%d",
        res_std, len(table),
    )
    # Log a few key points
    for g, wp, kf in table:
        if g in (0, 8, 12, 20, 30):
            logger.info("  growth=%d%%: win_prob=%.2f, kelly=%.3f", g, wp, kf)

    return KellyCalibration(
        residual_std=res_std,
        residual_mean=res_mean,
        hurdle_rate=hurdle,
        n_samples=len(y_actual),
        kelly_table=tuple(table),
    )


def kelly_for_prediction(
    predicted_growth: float,
    kelly_cal: KellyCalibration,
    avoid_probability: float | None = None,
) -> tuple[float, float]:
    """Look up Kelly fraction for a predicted growth level.

    Returns (win_probability, kelly_fraction).
    Modulates by avoid_probability if available.
    """
    if not kelly_cal.kelly_table:
        return 0.5, 0.0

    # Find nearest entry in pre-computed table
    best = min(kelly_cal.kelly_table, key=lambda t: abs(t[0] - predicted_growth))
    win_prob, kelly_frac = best[1], best[2]

    # Modulate by classifier confidence
    if avoid_probability is not None:
        # High avoid prob → shrink Kelly (less confident)
        confidence_mult = 1.0 - avoid_probability * 0.5
        kelly_frac = kelly_frac * confidence_mult

    return win_prob, round(kelly_frac, 4)


# ---------------------------------------------------------------------------
# Tier model training
# ---------------------------------------------------------------------------


def _select_and_train(
    X: pd.DataFrame,
    y: np.ndarray,
    tier_name: str,
    feature_names: list[str],
    *,
    groups: np.ndarray | None = None,
    sample_weight: np.ndarray | None = None,
) -> tuple[object, StandardScaler, dict, CVResult | None, object | None, object | None]:
    """Tune, train, and evaluate a single tier regressor.

    Returns (model, scaler, best_params, cv_result, target_transformer,
             conformal_calibration).
    """
    from sklearn.preprocessing import PowerTransformer

    X_clipped = clip_outliers(X)
    X_arr = X_clipped.values

    # Winsorize extreme target values (P1/P99) to reduce outlier pull
    y = winsorize_targets(y, lower_pct=1.0, upper_pct=99.0)

    logger.info(
        "%s target: n=%d, mean=%.1f%%, median=%.1f%%, std=%.1f%%, range=[%.1f%%, %.1f%%]",
        tier_name, len(y), np.mean(y), np.median(y), np.std(y), np.min(y), np.max(y),
    )

    # Monotonic constraints
    mono = _get_monotonic_constraints(feature_names)

    # Optuna tuning
    if _cfg.tuning_trials > 0:
        best_params, cv_result = tune_and_select(
            X_arr, y,
            n_trials=_cfg.tuning_trials,
            n_splits=_cfg.n_cv_splits,
            n_repeats=_cfg.n_cv_repeats,
            target_transform=_cfg.target_transform,
            sample_weight=sample_weight,
            monotonic_constraints=mono,
        )
    else:
        best_params, cv_result = {}, None

    # Temporal CV
    if groups is not None and len(groups) == len(y):
        tcv = temporal_cross_validate(
            X_arr, y, groups,
            lambda: build_model(best_params),
            target_transform=_cfg.target_transform,
            sample_weight=sample_weight,
            monotonic_constraints=mono,
        )
        logger.info(
            "%s temporal CV: R2=%.3f +/-%.3f (%d folds)",
            tier_name, tcv.r2_mean, tcv.r2_std, tcv.n_folds,
        )

    logger.info("%s best params: %s", tier_name, best_params)
    if cv_result:
        logger.info("  %s", cv_result.summary())

    # Fit target transformer
    target_transformer = None
    y_fit = y
    if _cfg.target_transform == "yeo-johnson":
        target_transformer = PowerTransformer(method="yeo-johnson", standardize=False)
        y_fit = target_transformer.fit_transform(y.reshape(-1, 1)).ravel()

    # Fit final model on all data
    model = build_model(best_params)
    if mono:
        model.set_params(monotone_constraints=mono)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_arr)
    model.fit(X_scaled, y_fit, sample_weight=sample_weight)

    # Conformal calibration
    conformal_cal = _fit_conformal(
        X_arr, y, groups, best_params, target_transformer, mono,
    )

    return model, scaler, best_params, cv_result, target_transformer, conformal_cal


def _fit_conformal(
    X_arr: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray | None,
    best_params: dict,
    target_transformer: object | None,
    mono: list[int],
) -> object | None:
    """Fit conformal calibration on held-out temporal cohort."""
    if groups is None or len(groups) != len(y):
        return None

    from services.ml.growth.conformal import calibrate_conformal

    finite_mask = np.isfinite(groups)
    unique_years = sorted(set(groups[finite_mask].astype(int)))
    if len(unique_years) < 3:
        return None

    cal_year = unique_years[-1]
    groups_safe = np.full(len(groups), -9999, dtype=int)
    groups_safe[finite_mask] = groups[finite_mask].astype(int)
    cal_mask = groups_safe == cal_year
    train_mask = ~cal_mask

    if cal_mask.sum() < 5 or train_mask.sum() < 20:
        return None

    cal_model = build_model(best_params)
    if mono:
        cal_model.set_params(monotone_constraints=mono)

    cal_scaler = StandardScaler()
    X_train_s = cal_scaler.fit_transform(X_arr[train_mask])
    X_cal_s = cal_scaler.transform(X_arr[cal_mask])

    y_train = y[train_mask]
    pt = None
    if target_transformer is not None:
        from sklearn.preprocessing import PowerTransformer

        pt = PowerTransformer(method="yeo-johnson", standardize=False)
        y_train = pt.fit_transform(y_train.reshape(-1, 1)).ravel()

    cal_model.fit(X_train_s, y_train)
    y_pred_cal = cal_model.predict(X_cal_s)

    if pt is not None:
        y_pred_cal = pt.inverse_transform(y_pred_cal.reshape(-1, 1)).ravel()

    return calibrate_conformal(y[cal_mask], y_pred_cal, calibration_year=cal_year)


def _build_tier_model(
    tier_num: int,
    X: pd.DataFrame,
    y: np.ndarray,
    feature_names: list[str],
    fill_values: pd.Series,
    *,
    groups: np.ndarray | None = None,
    sample_weight: np.ndarray | None = None,
) -> TrainedGrowthModel:
    """Train a single tier regressor (can run in a subprocess)."""
    from sklearn.base import BaseEstimator, RegressorMixin
    from sklearn.model_selection import KFold, cross_val_predict

    from services.ml.growth.calibration import fit_isotonic_calibrator

    model, scaler, params, cv, tt, cc = _select_and_train(
        X, y, f"Tier {tier_num}", feature_names,
        groups=groups, sample_weight=sample_weight,
    )

    # Train R2
    X_clipped = clip_outliers(X)
    X_eval = scaler.transform(X_clipped)
    y_pred = model.predict(X_eval)
    if tt is not None:
        y_pred = tt.inverse_transform(y_pred.reshape(-1, 1)).ravel()
    r2 = float(1 - np.sum((y - y_pred) ** 2) / np.sum((y - y.mean()) ** 2))

    # Isotonic calibration (fixed: wrapper ensures raw-scale CV predictions)
    iso_cal = None
    if len(y) >= 50 and not np.any(np.isnan(X_eval)):
        try:
            class _InverseWrapper(BaseEstimator, RegressorMixin):
                """Wraps model + target transform for raw-scale cross_val_predict."""

                def __init__(self, base_params, mono_c, transform):
                    self.base_params = base_params
                    self.mono_c = mono_c
                    self.transform = transform
                    self._model = None
                    self._pt = None

                def fit(self, X_fit, y_fit):
                    self._model = build_model(self.base_params)
                    if self.mono_c:
                        self._model.set_params(monotone_constraints=self.mono_c)
                    if self.transform == "yeo-johnson":
                        from sklearn.preprocessing import PowerTransformer
                        self._pt = PowerTransformer(method="yeo-johnson", standardize=False)
                        y_t = self._pt.fit_transform(y_fit.reshape(-1, 1)).ravel()
                    else:
                        self._pt = None
                        y_t = y_fit
                    self._model.fit(X_fit, y_t)
                    return self

                def predict(self, X_p):
                    raw = self._model.predict(X_p)
                    if self._pt is not None:
                        raw = self._pt.inverse_transform(raw.reshape(-1, 1)).ravel()
                    return raw

            mono = _get_monotonic_constraints(feature_names)
            wrapper = _InverseWrapper(params, mono, _cfg.target_transform)
            y_cv_pred = cross_val_predict(
                wrapper, X_eval, y,
                cv=KFold(5, shuffle=True, random_state=42),
            )
            iso_cal = fit_isotonic_calibrator(y, y_cv_pred)
        except Exception:
            logger.warning("Tier %d isotonic calibration failed", tier_num, exc_info=True)

    # Kelly calibration from CV residuals
    kelly_cal = None
    if iso_cal is not None or (len(y) >= 50 and not np.any(np.isnan(X_eval))):
        try:
            # Use y_cv_pred from isotonic section (already computed above)
            if 'y_cv_pred' in dir():
                kelly_cal = _compute_kelly_calibration(y, y_cv_pred)
        except Exception:
            pass
    # Fallback: compute CV predictions if not already done
    if kelly_cal is None and len(y) >= 50 and not np.any(np.isnan(X_eval)):
        try:
            mono = _get_monotonic_constraints(feature_names)
            wrapper = _InverseWrapper(params, mono, _cfg.target_transform)
            y_cv_pred = cross_val_predict(
                wrapper, X_eval, y,
                cv=KFold(5, shuffle=True, random_state=42),
            )
            kelly_cal = _compute_kelly_calibration(y, y_cv_pred)
        except Exception:
            pass

    # Overfit diagnostic
    gap = r2 - (cv.r2_mean if cv else 0)
    gap_status = "OK" if gap < 0.15 else "WARNING" if gap < 0.30 else "OVERFIT"
    logger.info(
        "Tier %d overfit: train=%.3f, cv=%.3f, gap=%.3f (%s)",
        tier_num, r2, cv.r2_mean if cv else 0, gap, gap_status,
    )

    result = TrainedGrowthModel(
        tier=tier_num,
        model=model,
        scaler=scaler,
        feature_names=tuple(feature_names),
        fill_values=tuple((f, float(fill_values[f])) for f in feature_names),
        n_train=len(y),
        train_r2=r2,
        trained_at=datetime.now().isoformat(),
        model_name="lightgbm",
        cv_r2_mean=cv.r2_mean if cv else None,
        cv_r2_std=cv.r2_std if cv else None,
        target_transformer=tt,
        conformal_calibration=cc,
        isotonic_calibrator=iso_cal,
        kelly_calibration=kelly_cal,
    )
    logger.info(
        "Tier %d: %d sets, %d features, train R2=%.3f, CV R2=%.3f%s%s",
        tier_num, len(y), len(feature_names), r2,
        cv.r2_mean if cv else float("nan"),
        f", isotonic: MAE {iso_cal.pre_mae:.2f}->{iso_cal.post_mae:.2f}" if iso_cal else "",
        f", kelly: std={kelly_cal.residual_std:.1f}%" if kelly_cal else "",
    )
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def train_growth_models(
    *,
    df_raw: pd.DataFrame,
    keepa_df: pd.DataFrame | None = None,
) -> tuple[
    TrainedGrowthModel,
    TrainedGrowthModel | None,
    dict,
    dict,
    TrainedClassifier | None,
    TrainedEnsemble | None,
]:
    """Train regressor + classifier on ALL data.

    The regressor ranks sets by predicted growth.
    The classifier provides P(avoid) as a confidence signal.
    They are NOT combined during training — only at prediction time.

    Returns:
        (tier1, tier2, theme_stats, subtheme_stats, classifier, ensemble)
    """
    import multiprocessing
    from concurrent.futures import Future, ProcessPoolExecutor

    mp_ctx = multiprocessing.get_context("spawn")

    if keepa_df is None:
        keepa_df = pd.DataFrame()

    y_all = df_raw["annual_growth_pct"].values.astype(float)

    # Temporal groups
    year_retired = np.asarray(
        pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float,
    )
    groups = year_retired if np.isfinite(year_retired).sum() > len(y_all) * 0.5 else None

    # Recency weights
    sample_weight = None
    if groups is not None:
        sample_weight = compute_recency_weights(year_retired)
        logger.info(
            "Recency weights: min=%.2f, max=%.2f, mean=%.2f",
            sample_weight.min(), sample_weight.max(), sample_weight.mean(),
        )

    # -- Phase 1: Feature engineering --

    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y_all),
    )
    tier1_candidates = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X1_raw = df_feat[tier1_candidates].copy()
    for c in X1_raw.columns:
        X1_raw[c] = pd.to_numeric(X1_raw[c], errors="coerce")

    # Feature selection
    tier1_features = select_features(X1_raw, y_all, min_mi_score=0.005, max_correlation=0.90)
    if len(tier1_features) < 5:
        logger.warning("Feature selection kept only %d, using all candidates", len(tier1_features))
        tier1_features = tier1_candidates

    X1 = X1_raw[tier1_features].copy()
    fill1 = X1.median()
    X1 = X1.fillna(fill1)

    # -- Phase 2: Classifier (advisory P(avoid) on BL ground truth) --

    logger.info("=" * 60)
    logger.info("Training avoid classifier (BrickLink ground truth)")
    logger.info("=" * 60)

    # Use BrickLink annualized returns as ground truth for the classifier.
    # Only includes retired sets with known retirement dates.
    from services.ml.growth.classifier import compute_avoid_sample_weights

    try:
        from db.pg.engine import get_engine
        from services.ml.pg_queries import load_bl_ground_truth
        _engine = get_engine()
        bl_target = load_bl_ground_truth(_engine)
    except Exception as exc:
        logger.warning("Could not load BL ground truth: %s", exc)
        bl_target = {}

    if bl_target:
        # Filter to sets with BL ground truth
        set_numbers = df_feat["set_number"].values if "set_number" in df_feat.columns else df_raw["set_number"].values
        bl_mask = np.array([sn in bl_target for sn in set_numbers])
        y_classifier = np.array([bl_target.get(sn, 0.0) for sn in set_numbers[bl_mask]])
        X1_classifier = clip_outliers(X1).values[bl_mask]

        logger.info(
            "BL ground truth: %d sets (%.1f%% of total), avoid rate %.1f%%",
            len(y_classifier), len(y_classifier) / len(y_all) * 100,
            (y_classifier < 10.0).mean() * 100,
        )

        # Asymmetric weights: penalize missing severe losers more
        avoid_weights = compute_avoid_sample_weights(y_classifier)
    else:
        # Fallback to BE target if no BL data (e.g., no DB connection)
        logger.warning("No BL ground truth available, falling back to BE annual_growth_pct")
        y_classifier = y_all
        X1_classifier = clip_outliers(X1).values
        avoid_weights = compute_avoid_sample_weights(y_classifier)

    classifier = train_classifier(
        X1_classifier, y_classifier, tier1_features,
        tuple((f, float(fill1[f])) for f in tier1_features),
        threshold=10.0,  # 10% hurdle rate for buy decision (Exp 36)
        tuning_trials=_cfg.classifier_tuning_trials,
        sample_weight=avoid_weights,
    )

    # -- Phase 3: Tier 2 features (Keepa) --

    cutoff_dates: dict[str, str] = {}
    df_kp = engineer_keepa_features(df_feat, keepa_df, cutoff_dates=cutoff_dates)
    # Phase 3b: calendar-aware Q4 seasonality features (same cutoff_dates)
    from services.ml.growth.seasonality_features import engineer_q4_seasonal_features
    df_kp = engineer_q4_seasonal_features(df_kp, keepa_df, cutoff_dates=cutoff_dates)
    has_keepa = df_kp["kp_bb_premium"].notna() | df_kp["kp_below_rrp_pct"].notna()
    df_kp_sub = df_kp[has_keepa].copy()
    y_kp = df_kp_sub["annual_growth_pct"].values.astype(float)

    can_train_t2 = len(y_kp) >= 50
    X2, fill2, tier2_features, groups_kp, weight_kp = None, None, None, None, None
    if can_train_t2:
        # Apply feature selection to Tier 2 as well
        tier2_candidates = [f for f in TIER2_FEATURES if f in df_kp_sub.columns]
        X2_raw = df_kp_sub[tier2_candidates].copy()
        for c in X2_raw.columns:
            X2_raw[c] = pd.to_numeric(X2_raw[c], errors="coerce")
        tier2_features = select_features(
            X2_raw, y_kp, min_mi_score=0.005, max_correlation=0.90, lofo_prune=False,
        )
        if len(tier2_features) < 5:
            tier2_features = tier2_candidates
        X2 = X2_raw[tier2_features].copy()
        fill2 = X2.median()
        X2 = X2.fillna(fill2)
        groups_kp = year_retired[has_keepa.values] if groups is not None else None
        weight_kp = sample_weight[has_keepa.values] if sample_weight is not None else None
    else:
        logger.info("Tier 2 skipped: only %d Keepa sets (need 50+)", len(y_kp))

    # -- Phase 4: Parallel regressor training on ALL data --

    logger.info("=" * 60)
    logger.info("Training regressors on ALL %d sets", len(y_all))
    logger.info("=" * 60)

    with ProcessPoolExecutor(max_workers=2, mp_context=mp_ctx) as pool:
        fut_t1: Future = pool.submit(
            _build_tier_model, 1, X1, y_all, tier1_features, fill1,
            groups=groups, sample_weight=sample_weight,
        )
        fut_t2: Future | None = None
        if can_train_t2:
            fut_t2 = pool.submit(
                _build_tier_model, 2, X2, y_kp, tier2_features, fill2,
                groups=groups_kp, sample_weight=weight_kp,
            )

        tier1 = fut_t1.result()
        tier2 = fut_t2.result() if fut_t2 else None

    logger.info("All tiers trained.")

    # -- Phase 5: Ensemble --
    base_models = [m for m in (tier1, tier2) if m is not None]
    ensemble = (
        _train_ensemble(df_raw, df_feat, df_kp, base_models)
        if len(base_models) >= 2
        else None
    )

    return tier1, tier2, theme_stats, subtheme_stats, classifier, ensemble


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------


def _train_ensemble(
    df_raw: pd.DataFrame,
    df_feat_t1: pd.DataFrame,
    df_feat_t2: pd.DataFrame,
    base_models: list[TrainedGrowthModel],
) -> TrainedEnsemble | None:
    """Stacked ensemble from OOF base model predictions."""
    from sklearn.linear_model import ElasticNet, Ridge
    from sklearn.model_selection import GroupKFold, KFold

    y_all = df_raw["annual_growth_pct"].values.astype(float)
    n = len(y_all)
    if n < 50:
        return None

    year_retired = np.asarray(
        pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float,
    )
    has_groups = np.isfinite(year_retired).sum() > n * 0.5

    if has_groups:
        median_year = int(np.nanmedian(year_retired))
        finite_mask = np.isfinite(year_retired)
        groups_arr = np.full(n, median_year, dtype=int)
        groups_arr[finite_mask] = year_retired[finite_mask].astype(int)
        n_unique = len(set(groups_arr))
        n_splits = min(5, n_unique)
        splitter = GroupKFold(n_splits=n_splits)
        split_args = (np.arange(n), y_all, groups_arr)
    else:
        splitter = KFold(n_splits=5, shuffle=True, random_state=42)
        split_args = (np.arange(n),)

    oof_preds: dict[int, np.ndarray] = {}

    for m in base_models:
        tier = m.tier
        oof = np.full(n, np.nan)
        feat_df = df_feat_t1 if tier == 1 else df_feat_t2
        feat_cols = [f for f in m.feature_names if f in feat_df.columns]
        X_full = feat_df[feat_cols].copy()
        for c in X_full.columns:
            X_full[c] = pd.to_numeric(X_full[c], errors="coerce")
        X_full = X_full.fillna(X_full.median())

        if len(X_full) != n:
            X_full = X_full.reindex(df_raw.index)

        for train_idx, val_idx in splitter.split(*split_args):
            X_tr, X_va = X_full.iloc[train_idx], X_full.iloc[val_idx]
            y_tr = y_all[train_idx]

            pt = None
            if m.target_transformer is not None:
                from sklearn.preprocessing import PowerTransformer
                pt = PowerTransformer(method="yeo-johnson", standardize=False)
                y_tr_fit = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()
            else:
                y_tr_fit = y_tr

            s = StandardScaler()
            X_tr_s, X_va_s = s.fit_transform(X_tr), s.transform(X_va)
            fold_model = build_model()
            fold_model.fit(X_tr_s, y_tr_fit)
            preds_raw = fold_model.predict(X_va_s)
            if pt is not None:
                preds_raw = pt.inverse_transform(preds_raw.reshape(-1, 1)).ravel()
            oof[val_idx] = preds_raw

        oof_preds[tier] = oof

    valid_tiers = [t for t in sorted(oof_preds) if not np.all(np.isnan(oof_preds[t]))]
    if len(valid_tiers) < 2:
        return None

    meta_X = np.column_stack([oof_preds[t] for t in valid_tiers])
    valid_rows = ~np.any(np.isnan(meta_X), axis=1)
    meta_X_clean, y_clean = meta_X[valid_rows], y_all[valid_rows]

    if len(y_clean) < 30:
        return None

    best_meta_cv: CVResult | None = None
    best_meta_cls = Ridge
    for meta_cls, name in [(Ridge, "Ridge"), (ElasticNet, "ElasticNet")]:
        meta_cv = cross_validate_model(
            meta_X_clean, y_clean,
            lambda cls=meta_cls: cls(alpha=1.0, random_state=42)
            if hasattr(cls(), "random_state") else cls(alpha=1.0),
            n_splits=_cfg.n_cv_splits, n_repeats=_cfg.n_cv_repeats,
        )
        logger.info("  Ensemble (%s): CV R2=%.3f +/-%.3f", name, meta_cv.r2_mean, meta_cv.r2_std)
        if best_meta_cv is None or meta_cv.r2_mean > best_meta_cv.r2_mean:
            best_meta_cv = meta_cv
            best_meta_cls = meta_cls

    meta_scaler = StandardScaler()
    meta_X_s = meta_scaler.fit_transform(meta_X_clean)
    meta_model = best_meta_cls(alpha=1.0)
    meta_model.fit(meta_X_s, y_clean)

    tier_names = [f"tier{t}" for t in valid_tiers]
    weights = tuple(zip(tier_names, meta_model.coef_.tolist()))

    ensemble = TrainedEnsemble(
        base_models=tuple(base_models),
        meta_model=meta_model,
        meta_scaler=meta_scaler,
        n_train=len(y_clean),
        oos_r2=best_meta_cv.r2_mean if best_meta_cv else 0.0,
        trained_at=datetime.now().isoformat(),
        weights=weights,
        cv_scores=best_meta_cv.r2_folds if best_meta_cv else (),
    )
    logger.info("Ensemble: %d sets, CV R2=%.3f", len(y_clean), ensemble.oos_r2)
    for name, w in weights:
        logger.info("  %s: weight=%.3f", name, w)
    return ensemble
