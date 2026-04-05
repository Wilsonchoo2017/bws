"""Growth model training.

Trains Tier 1 (intrinsics), Tier 2 (intrinsics + Keepa), and
Tier 3 (all available features from plugin extractors) models.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from config.ml import FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT, MLPipelineConfig
from services.ml.extractors import extract_all as _extract_all_plugin
from services.ml.growth.evaluation import CIRCULAR_FEATURES
from services.ml.growth.features import (
    TIER1_FEATURES,
    TIER2_FEATURES,
    engineer_intrinsic_features,
    engineer_keepa_features,
)
from services.ml.growth.model_selection import (
    CVResult,
    build_model,
    clip_outliers,
    cross_validate_model,
    select_best_model,
    temporal_cross_validate,
)
from services.ml.growth.types import TrainedEnsemble, TrainedGrowthModel
from services.ml.helpers import compute_cutoff_dates
from services.ml.queries import (
    load_base_metadata,
    load_growth_training_data,
    load_keepa_timelines,
)

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

_cfg = MLPipelineConfig()


def _select_and_train(
    X: pd.DataFrame,
    y: np.ndarray,
    tier_name: str,
    *,
    groups: np.ndarray | None = None,
) -> tuple[object, StandardScaler, str, dict, CVResult | None, object | None, object | None]:
    """Select best model via Optuna tuning + CV, then fit on all data.

    Args:
        groups: Optional year_retired array for temporal CV.

    Returns (fitted_model, fitted_scaler, model_name, best_params,
             cv_result, target_transformer).
    """
    from sklearn.preprocessing import PowerTransformer

    X_clipped = clip_outliers(X)
    X_arr = X_clipped.values

    # Log target distribution
    logger.info(
        "%s target: mean=%.1f%%, median=%.1f%%, std=%.1f%%, range=[%.1f%%, %.1f%%]",
        tier_name, np.mean(y), np.median(y), np.std(y), np.min(y), np.max(y),
    )
    extreme = np.sum(np.abs(y - np.mean(y)) > 3 * np.std(y))
    if extreme > len(y) * 0.05:
        logger.warning("%s: %d extreme targets (>3 std)", tier_name, extreme)

    # Tune and select (CV uses per-fold target transform to avoid leakage)
    if _cfg.tuning_trials > 0:
        model_name, best_params, cv_result = select_best_model(
            X_arr, y,
            candidates=_cfg.model_candidates,
            n_trials=_cfg.tuning_trials,
            n_splits=_cfg.n_cv_splits,
            n_repeats=_cfg.n_cv_repeats,
            min_improvement=_cfg.min_improvement_for_complex,
            target_transform=_cfg.target_transform,
        )
    else:
        model_name, best_params, cv_result = "gbm", {}, None

    # Run temporal CV for a more honest OOS estimate (if groups available)
    temporal_cv = None
    if groups is not None and len(groups) == len(y):
        temporal_cv = temporal_cross_validate(
            X_arr, y, groups,
            lambda: build_model(model_name, best_params),
            target_transform=_cfg.target_transform,
        )
        logger.info(
            "%s temporal CV: R2=%.3f +/-%.3f (%d folds)",
            tier_name, temporal_cv.r2_mean, temporal_cv.r2_std, temporal_cv.n_folds,
        )

    logger.info("%s selected: %s", tier_name, model_name)
    if cv_result:
        logger.info("  %s", cv_result.summary())

    # Fit target transformer on all training data
    target_transformer = None
    y_fit = y
    if _cfg.target_transform == "yeo-johnson":
        target_transformer = PowerTransformer(method="yeo-johnson", standardize=False)
        y_fit = target_transformer.fit_transform(y.reshape(-1, 1)).ravel()
        logger.info("%s target transform: yeo-johnson applied", tier_name)

    # Fit final model on all data
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_arr)
    model = build_model(model_name, best_params)
    model.fit(X_scaled, y_fit)

    # Conformal calibration using most recent temporal cohort as holdout.
    # A separate model is trained EXCLUDING the calibration year to avoid
    # data leakage (the production model above sees all data).
    conformal_cal = None
    if groups is not None and len(groups) == len(y):
        from services.ml.growth.conformal import calibrate_conformal

        finite_mask = np.isfinite(groups)
        unique_years = sorted(set(groups[finite_mask].astype(int)))
        if len(unique_years) >= 3:
            cal_year = unique_years[-1]
            groups_safe = np.full(len(groups), -9999, dtype=int)
            groups_safe[finite_mask] = groups[finite_mask].astype(int)
            cal_mask = groups_safe == cal_year
            train_mask = ~cal_mask
            if cal_mask.sum() >= 5 and train_mask.sum() >= 20:
                # Train a held-out model for unbiased residuals
                cal_scaler = StandardScaler()
                X_train_s = cal_scaler.fit_transform(X_arr[train_mask])
                y_train = y_fit[train_mask] if target_transformer is not None else y[train_mask]
                cal_model = build_model(model_name, best_params)
                cal_model.fit(X_train_s, y_train)

                X_cal_s = cal_scaler.transform(X_arr[cal_mask])
                y_pred_cal = cal_model.predict(X_cal_s)
                if target_transformer is not None:
                    y_pred_cal = target_transformer.inverse_transform(
                        y_pred_cal.reshape(-1, 1)
                    ).ravel()
                conformal_cal = calibrate_conformal(
                    y[cal_mask], y_pred_cal, calibration_year=cal_year,
                )

    return (model, scaler, model_name, best_params, cv_result,
            target_transformer, conformal_cal)


def _build_tier_model(
    tier_num: int,
    X: pd.DataFrame,
    y: np.ndarray,
    feature_names: list[str],
    fill_values: pd.Series,
    *,
    groups: np.ndarray | None = None,
) -> TrainedGrowthModel:
    """Train a single tier model (can run in parallel)."""
    model, scaler, m_name, _, cv, tt, cc = _select_and_train(
        X, y, f"Tier {tier_num}", groups=groups,
    )
    y_pred = model.predict(scaler.transform(clip_outliers(X)))
    if tt is not None:
        y_pred = tt.inverse_transform(y_pred.reshape(-1, 1)).ravel()
    r2 = float(1 - np.sum((y - y_pred) ** 2) / np.sum((y - y.mean()) ** 2))

    result = TrainedGrowthModel(
        tier=tier_num,
        model=model,
        scaler=scaler,
        feature_names=tuple(feature_names),
        fill_values=tuple((f, float(fill_values[f])) for f in feature_names),
        n_train=len(y),
        train_r2=r2,
        trained_at=datetime.now().isoformat(),
        model_name=m_name,
        cv_r2_mean=cv.r2_mean if cv else None,
        cv_r2_std=cv.r2_std if cv else None,
        target_transformer=tt,
        conformal_calibration=cc,
    )
    logger.info(
        "Tier %d trained: %d sets, %d features, train R2=%.3f, CV R2=%.3f",
        tier_num, len(y), len(feature_names), r2,
        cv.r2_mean if cv else float("nan"),
    )
    return result


def train_growth_models(
    conn: DuckDBPyConnection,
) -> tuple[TrainedGrowthModel, TrainedGrowthModel | None, dict, dict, TrainedGrowthModel | None, TrainedEnsemble | None]:
    """Train Tier 1, 2, 3, and ensemble growth models.

    Tiers are trained in parallel using separate processes (avoids GIL contention).
    Feature engineering is sequential (uses DB), model tuning is parallel.

    Returns:
        (tier1, tier2_or_none, theme_stats, subtheme_stats, tier3_or_none, ensemble_or_none)
    """
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor, Future

    # Use 'spawn' to avoid fork-safety issues on macOS (threads + fork = deadlocks)
    mp_ctx = multiprocessing.get_context("spawn")

    # -- Phase 1: Load data (sequential, uses DB connection) --
    df_raw = load_growth_training_data(conn)
    keepa_df = load_keepa_timelines(conn)

    y = df_raw["annual_growth_pct"].values.astype(float)

    # Temporal groups for walk-forward CV
    year_retired = np.asarray(pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float)
    groups = year_retired if np.isfinite(year_retired).sum() > len(y) * 0.5 else None

    # -- Phase 2: Feature engineering (sequential, fast) --

    # Tier 1 features
    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y),
    )
    tier1_features = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X1 = df_feat[tier1_features].copy()
    for c in X1.columns:
        X1[c] = pd.to_numeric(X1[c], errors="coerce")
    fill1 = X1.median()
    X1 = X1.fillna(fill1)

    # Tier 2 features
    base_meta = load_base_metadata(conn, df_raw["set_number"].tolist())
    base_meta = compute_cutoff_dates(base_meta, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT)
    cutoff_dates: dict[str, str] = {}
    for _, row in base_meta.iterrows():
        cy, cm = row.get("cutoff_year"), row.get("cutoff_month")
        if pd.notna(cy) and pd.notna(cm):
            cutoff_dates[row["set_number"]] = f"{int(cy)}-{int(cm):02d}"

    df_kp = engineer_keepa_features(df_feat, keepa_df, cutoff_dates=cutoff_dates)
    has_keepa = df_kp["kp_bb_premium"].notna() | df_kp["kp_below_rrp_pct"].notna()
    df_kp_sub = df_kp[has_keepa].copy()
    y_kp = df_kp_sub["annual_growth_pct"].values.astype(float)

    can_train_t2 = len(y_kp) >= 50
    X2, fill2, tier2_features, groups_kp = None, None, None, None
    if can_train_t2:
        tier2_features = [f for f in TIER2_FEATURES if f in df_kp_sub.columns]
        X2 = df_kp_sub[tier2_features].copy()
        for c in X2.columns:
            X2[c] = pd.to_numeric(X2[c], errors="coerce")
        fill2 = X2.median()
        X2 = X2.fillna(fill2)
        groups_kp = year_retired[has_keepa.values] if groups is not None else None
    else:
        logger.info("Tier 2 skipped: only %d Keepa sets (need 50+)", len(y_kp))

    # Tier 3 features (uses DB for extractors)
    tier3_data = _prepare_tier3_features(conn, df_raw)

    # -- Phase 3: Model tuning (PARALLEL -- the expensive part) --
    logger.info("Starting parallel tier training...")

    with ProcessPoolExecutor(max_workers=3, mp_context=mp_ctx) as pool:
        # Submit Tier 1
        fut_t1: Future = pool.submit(
            _build_tier_model, 1, X1, y, tier1_features, fill1, groups=groups,
        )

        # Submit Tier 2
        fut_t2: Future | None = None
        if can_train_t2:
            fut_t2 = pool.submit(
                _build_tier_model, 2, X2, y_kp, tier2_features, fill2,
                groups=groups_kp,
            )

        # Submit Tier 3
        fut_t3: Future | None = None
        tier3_X, tier3_y = None, None
        if tier3_data is not None:
            t3_X, t3_y, t3_features, t3_fill = tier3_data
            tier3_X, tier3_y = t3_X, t3_y
            fut_t3 = pool.submit(
                _build_tier_model, 3, t3_X, t3_y, t3_features, t3_fill,
            )

        # Collect results
        tier1 = fut_t1.result()
        tier2 = fut_t2.result() if fut_t2 else None
        tier3 = fut_t3.result() if fut_t3 else None

    logger.info("All tiers trained.")

    # -- Phase 4: Ensemble (sequential, fast) --
    base_models = [m for m in (tier1, tier2, tier3) if m is not None]
    ensemble = _train_ensemble(
        df_raw, df_feat, df_kp, base_models,
        tier3_X=tier3_X, tier3_y=tier3_y,
    ) if len(base_models) >= 2 else None

    return tier1, tier2, theme_stats, subtheme_stats, tier3, ensemble


def _prepare_tier3_features(
    conn: DuckDBPyConnection,
    df_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, np.ndarray, list[str], pd.Series] | None:
    """Prepare Tier 3 feature matrix (DB access, runs before parallel phase).

    Returns (X, y, feature_cols, fill_values) or None if insufficient data.
    """
    set_numbers = df_raw["set_number"].tolist()
    base = load_base_metadata(conn, set_numbers)
    if base.empty:
        logger.info("Tier 3 skipped: no base metadata")
        return None

    base = compute_cutoff_dates(base, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT)
    extractor_features = _extract_all_plugin(conn, base)
    if extractor_features.empty:
        logger.info("Tier 3 skipped: no extractor features")
        return None

    target_df = df_raw[["set_number", "annual_growth_pct"]].drop_duplicates(subset=["set_number"])
    ext_cols = [c for c in extractor_features.columns if c != "annual_growth_pct"]
    merged = target_df.merge(extractor_features[ext_cols], on="set_number", how="inner")

    if len(merged) < 30:
        logger.info("Tier 3 skipped: only %d sets with features (need 30+)", len(merged))
        return None

    y = merged["annual_growth_pct"].values.astype(float)
    exclude_cols = {"set_number", "annual_growth_pct"} | CIRCULAR_FEATURES
    feature_cols = [
        c for c in merged.columns
        if c not in exclude_cols
        and merged[c].dtype in ("float64", "int64", "float32", "int32")
    ]

    min_coverage = 0.10
    feature_cols = [
        c for c in feature_cols
        if merged[c].notna().sum() / len(merged) >= min_coverage
    ]

    if len(feature_cols) < 5:
        logger.info("Tier 3 skipped: only %d features with coverage (need 5+)", len(feature_cols))
        return None

    X = merged[feature_cols].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    fill = X.median()
    X = X.fillna(fill)

    # Drop highly correlated features
    corr_matrix = X.corr().abs()
    upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape, dtype=bool), k=1))
    to_drop = set()
    for col in upper.columns:
        highly_corr = upper.index[upper[col] > _cfg.correlation_threshold].tolist()
        for hc in highly_corr:
            if hc not in to_drop:
                if X[col].var() >= X[hc].var():
                    to_drop.add(hc)
                else:
                    to_drop.add(col)

    feature_cols = [c for c in feature_cols if c not in to_drop]
    X = X[feature_cols]

    logger.info(
        "Tier 3: %d sets, %d features after filtering (excluded %d circular)",
        len(y), len(feature_cols),
        sum(1 for c in merged.columns if c in CIRCULAR_FEATURES),
    )

    return X, y, feature_cols, fill




def _train_ensemble(
    df_raw: pd.DataFrame,
    df_feat_t1: pd.DataFrame,
    df_feat_t2: pd.DataFrame,
    base_models: list[TrainedGrowthModel],
    *,
    tier3_X: pd.DataFrame | None = None,
    tier3_y: np.ndarray | None = None,
) -> TrainedEnsemble | None:
    """Train a stacked ensemble from cross-validated base model predictions.

    Uses 5-fold cross-validation to generate out-of-fold predictions from
    each base model, then fits a Ridge meta-learner on those predictions.
    Final OOS metric uses a temporal holdout of the 20% newest sets.
    """
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GroupKFold, KFold

    y_all = df_raw["annual_growth_pct"].values.astype(float)
    n = len(y_all)
    if n < 50:
        logger.info("Ensemble skipped: only %d sets", n)
        return None

    # Use temporal grouping if year_retired is available
    year_retired = np.asarray(pd.to_numeric(df_raw.get("year_retired"), errors="coerce"), dtype=float)
    has_groups = np.isfinite(year_retired).sum() > n * 0.5

    if has_groups:
        # Fill missing years with median so GroupKFold works
        median_year = int(np.nanmedian(year_retired))
        finite_mask = np.isfinite(year_retired)
        groups_arr = np.full(n, median_year, dtype=int)
        groups_arr[finite_mask] = year_retired[finite_mask].astype(int)
        n_unique = len(set(groups_arr))
        n_splits = min(5, n_unique)
        splitter = GroupKFold(n_splits=n_splits)
        split_args = (np.arange(n), y_all, groups_arr)
        logger.info("Ensemble OOF: GroupKFold with %d year groups", n_unique)
    else:
        splitter = KFold(n_splits=5, shuffle=True, random_state=42)
        split_args = (np.arange(n),)

    # Generate out-of-fold predictions for each base model
    oof_preds: dict[int, np.ndarray] = {}

    for m in base_models:
        tier = m.tier
        oof = np.full(n, np.nan)

        # Select the right feature DataFrame for this tier
        if tier == 1:
            feat_cols = [f for f in m.feature_names if f in df_feat_t1.columns]
            X_full = df_feat_t1[feat_cols].copy()
        elif tier == 2:
            feat_cols = [f for f in m.feature_names if f in df_feat_t2.columns]
            X_full = df_feat_t2[feat_cols].copy()
            if len(X_full) != n:
                X_full = X_full.reindex(df_raw.index)
        elif tier == 3 and tier3_X is not None and tier3_y is not None:
            feat_cols = [f for f in m.feature_names if f in tier3_X.columns]
            X_full = tier3_X[feat_cols].copy()
            if len(X_full) != n:
                X_full = X_full.reindex(df_raw.index)
        else:
            oof_preds[tier] = np.full(n, np.nan)
            continue

        for c in X_full.columns:
            X_full[c] = pd.to_numeric(X_full[c], errors="coerce")
        fill = X_full.median()
        X_full = X_full.fillna(fill)

        for train_idx, val_idx in splitter.split(*split_args):
            X_tr = X_full.iloc[train_idx]
            y_tr = y_all[train_idx]
            X_va = X_full.iloc[val_idx]

            # Per-fold target transform
            if m.target_transformer is not None:
                from sklearn.preprocessing import PowerTransformer
                pt = PowerTransformer(method="yeo-johnson", standardize=False)
                y_tr_fit = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()
            else:
                pt = None
                y_tr_fit = y_tr

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_va_s = scaler.transform(X_va)

            fold_model = build_model(m.model_name)
            fold_model.fit(X_tr_s, y_tr_fit)
            preds_raw = fold_model.predict(X_va_s)

            if pt is not None:
                preds_raw = pt.inverse_transform(preds_raw.reshape(-1, 1)).ravel()
            oof[val_idx] = preds_raw

        oof_preds[tier] = oof

    # Build meta-features matrix (only tiers with actual OOF predictions)
    valid_tiers = [t for t in sorted(oof_preds) if not np.all(np.isnan(oof_preds[t]))]
    if len(valid_tiers) < 2:
        logger.info("Ensemble skipped: only %d tiers with OOF predictions", len(valid_tiers))
        return None

    meta_X = np.column_stack([oof_preds[t] for t in valid_tiers])

    # Handle rows where some tiers have NaN (e.g. Tier 2 missing Keepa data)
    valid_rows = ~np.any(np.isnan(meta_X), axis=1)
    meta_X_clean = meta_X[valid_rows]
    y_clean = y_all[valid_rows]

    if len(y_clean) < 30:
        logger.info("Ensemble skipped: only %d sets with all tier predictions", len(y_clean))
        return None

    # CV evaluation of meta-learner (try Ridge and ElasticNet)
    from sklearn.linear_model import ElasticNet

    best_meta_cv: CVResult | None = None
    best_meta_cls = Ridge

    for meta_cls, meta_name in [(Ridge, "Ridge"), (ElasticNet, "ElasticNet")]:
        meta_cv = cross_validate_model(
            meta_X_clean, y_clean,
            lambda cls=meta_cls: cls(alpha=1.0, random_state=42) if hasattr(cls, "random_state") else cls(alpha=1.0),
            n_splits=_cfg.n_cv_splits,
            n_repeats=_cfg.n_cv_repeats,
        )
        logger.info("  Ensemble meta (%s): CV R2=%.3f +/-%.3f", meta_name, meta_cv.r2_mean, meta_cv.r2_std)
        if best_meta_cv is None or meta_cv.r2_mean > best_meta_cv.r2_mean:
            best_meta_cv = meta_cv
            best_meta_cls = meta_cls

    # Fit final meta-model on ALL clean data
    meta_scaler_final = StandardScaler()
    meta_X_all_s = meta_scaler_final.fit_transform(meta_X_clean)
    meta_model_final = best_meta_cls(alpha=1.0)
    meta_model_final.fit(meta_X_all_s, y_clean)

    # Extract weights
    tier_names = [f"tier{t}" for t in valid_tiers]
    weights = tuple(zip(tier_names, meta_model_final.coef_.tolist()))

    ensemble = TrainedEnsemble(
        base_models=tuple(base_models),
        meta_model=meta_model_final,
        meta_scaler=meta_scaler_final,
        n_train=len(y_clean),
        oos_r2=best_meta_cv.r2_mean if best_meta_cv else 0.0,
        trained_at=datetime.now().isoformat(),
        weights=weights,
        cv_scores=best_meta_cv.r2_folds if best_meta_cv else (),
    )

    logger.info(
        "Ensemble trained: %d sets, %d tiers, CV R2=%.3f +/-%.3f",
        len(y_clean), len(valid_tiers),
        best_meta_cv.r2_mean if best_meta_cv else 0.0,
        best_meta_cv.r2_std if best_meta_cv else 0.0,
    )
    for name, w in weights:
        logger.info("  Ensemble weight: %-10s  %.3f", name, w)

    return ensemble
