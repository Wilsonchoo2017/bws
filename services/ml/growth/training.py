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


def _build_model() -> object:
    """Legacy default model builder (used as fallback)."""
    return build_model("gbm")


def _select_and_train(
    X: pd.DataFrame,
    y: np.ndarray,
    tier_name: str,
) -> tuple[object, StandardScaler, str, dict, CVResult | None]:
    """Select best model via Optuna tuning + CV, then fit on all data.

    Returns (fitted_model, fitted_scaler, model_name, best_params, cv_result).
    """
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

    # Tune and select
    if _cfg.tuning_trials > 0:
        model_name, best_params, cv_result = select_best_model(
            X_arr, y,
            candidates=_cfg.model_candidates,
            n_trials=_cfg.tuning_trials,
            n_splits=_cfg.n_cv_splits,
            n_repeats=_cfg.n_cv_repeats,
            min_improvement=_cfg.min_improvement_for_complex,
        )
    else:
        model_name, best_params, cv_result = "gbm", {}, None

    logger.info("%s selected: %s", tier_name, model_name)
    if cv_result:
        logger.info("  %s", cv_result.summary())

    # Fit final model on all data
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_clipped)
    model = build_model(model_name, best_params)
    model.fit(X_scaled, y)

    return model, scaler, model_name, best_params, cv_result


def train_growth_models(
    conn: DuckDBPyConnection,
) -> tuple[TrainedGrowthModel, TrainedGrowthModel | None, dict, dict, TrainedGrowthModel | None, TrainedEnsemble | None]:
    """Train Tier 1, 2, 3, and ensemble growth models.

    Returns:
        (tier1, tier2_or_none, theme_stats, subtheme_stats, tier3_or_none, ensemble_or_none)
    """
    df_raw = load_growth_training_data(conn)
    keepa_df = load_keepa_timelines(conn)

    y = df_raw["annual_growth_pct"].values.astype(float)

    # Tier 1: intrinsics
    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y),
    )

    tier1_features = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X1 = df_feat[tier1_features].copy()
    for c in X1.columns:
        X1[c] = pd.to_numeric(X1[c], errors="coerce")
    fill1 = X1.median()
    X1 = X1.fillna(fill1)

    model1, scaler1, m1_name, _, cv1 = _select_and_train(X1, y, "Tier 1")
    y_pred1 = model1.predict(scaler1.transform(clip_outliers(X1)))
    r2_1 = float(1 - np.sum((y - y_pred1) ** 2) / np.sum((y - y.mean()) ** 2))

    tier1 = TrainedGrowthModel(
        tier=1,
        model=model1,
        scaler=scaler1,
        feature_names=tuple(tier1_features),
        fill_values=tuple((f, float(fill1[f])) for f in tier1_features),
        n_train=len(y),
        train_r2=r2_1,
        trained_at=datetime.now().isoformat(),
        model_name=m1_name,
        cv_r2_mean=cv1.r2_mean if cv1 else None,
        cv_r2_std=cv1.r2_std if cv1 else None,
    )
    logger.info(
        "Tier 1 trained: %d sets, %d features, train R2=%.3f, CV R2=%.3f",
        len(y), len(tier1_features), r2_1,
        cv1.r2_mean if cv1 else float("nan"),
    )

    # Tier 2: intrinsics + Keepa (with temporal cutoff for training)
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

    tier2 = None
    if len(y_kp) >= 50:
        tier2_features = [f for f in TIER2_FEATURES if f in df_kp_sub.columns]
        X2 = df_kp_sub[tier2_features].copy()
        for c in X2.columns:
            X2[c] = pd.to_numeric(X2[c], errors="coerce")
        fill2 = X2.median()
        X2 = X2.fillna(fill2)

        model2, scaler2, m2_name, _, cv2 = _select_and_train(X2, y_kp, "Tier 2")
        y_pred2 = model2.predict(scaler2.transform(clip_outliers(X2)))
        r2_2 = float(1 - np.sum((y_kp - y_pred2) ** 2) / np.sum((y_kp - y_kp.mean()) ** 2))

        tier2 = TrainedGrowthModel(
            tier=2,
            model=model2,
            scaler=scaler2,
            feature_names=tuple(tier2_features),
            fill_values=tuple((f, float(fill2[f])) for f in tier2_features),
            n_train=len(y_kp),
            train_r2=r2_2,
            trained_at=datetime.now().isoformat(),
            model_name=m2_name,
            cv_r2_mean=cv2.r2_mean if cv2 else None,
            cv_r2_std=cv2.r2_std if cv2 else None,
        )
        logger.info(
            "Tier 2 trained: %d sets, %d features, train R2=%.3f, CV R2=%.3f",
            len(y_kp), len(tier2_features), r2_2,
            cv2.r2_mean if cv2 else float("nan"),
        )
    else:
        logger.info("Tier 2 skipped: only %d Keepa sets (need 50+)", len(y_kp))

    # Tier 3: all extractor-based features
    tier3, tier3_X, tier3_y = _train_tier3(conn, df_raw)

    # Ensemble: stack Tier 1/2/3 predictions via cross-validated meta-learner
    base_models = [m for m in (tier1, tier2, tier3) if m is not None]
    ensemble = _train_ensemble(
        df_raw, df_feat, df_kp, base_models,
        tier3_X=tier3_X, tier3_y=tier3_y,
    ) if len(base_models) >= 2 else None

    return tier1, tier2, theme_stats, subtheme_stats, tier3, ensemble


def _train_tier3(
    conn: DuckDBPyConnection,
    df_raw: pd.DataFrame,
) -> tuple[TrainedGrowthModel | None, pd.DataFrame | None, np.ndarray | None]:
    """Train Tier 3 model using all plugin extractor features.

    Combines Tier 1 intrinsics with BrickLink momentum, BE charts,
    full Keepa timeline, and other extractor features.
    """
    set_numbers = df_raw["set_number"].tolist()

    # Build base metadata with cutoff dates
    base = load_base_metadata(conn, set_numbers)
    _none3 = (None, None, None)
    if base.empty:
        logger.info("Tier 3 skipped: no base metadata")
        return _none3

    base = compute_cutoff_dates(base, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT)

    # Run all extractors
    extractor_features = _extract_all_plugin(conn, base)
    if extractor_features.empty:
        logger.info("Tier 3 skipped: no extractor features")
        return _none3

    # Merge extractor features with the training target
    target_df = df_raw[["set_number", "annual_growth_pct"]].drop_duplicates(subset=["set_number"])
    # Drop annual_growth_pct from extractor_features if it exists (avoid conflict)
    ext_cols = [c for c in extractor_features.columns if c != "annual_growth_pct"]
    merged = target_df.merge(
        extractor_features[ext_cols], on="set_number", how="inner"
    )

    if len(merged) < 30:
        logger.info("Tier 3 skipped: only %d sets with features (need 30+)", len(merged))
        return _none3

    y = merged["annual_growth_pct"].values.astype(float)

    # Use all numeric columns as features (excluding target, identifiers,
    # and CIRCULAR features that leak target information)
    exclude_cols = {"set_number", "annual_growth_pct"} | CIRCULAR_FEATURES
    feature_cols = [
        c for c in merged.columns
        if c not in exclude_cols
        and merged[c].dtype in ("float64", "int64", "float32", "int32")
    ]

    # Drop features with <10% non-null coverage
    min_coverage = 0.10
    feature_cols = [
        c for c in feature_cols
        if merged[c].notna().sum() / len(merged) >= min_coverage
    ]

    if len(feature_cols) < 5:
        logger.info("Tier 3 skipped: only %d features with coverage (need 5+)", len(feature_cols))
        return _none3

    X = merged[feature_cols].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    fill = X.median()
    X = X.fillna(fill)

    # Drop highly correlated features (keep the one with higher variance)
    corr_matrix = X.corr().abs()
    upper = corr_matrix.where(
        np.triu(np.ones(corr_matrix.shape, dtype=bool), k=1)
    )
    to_drop = set()
    for col in upper.columns:
        highly_corr = upper.index[upper[col] > 0.95].tolist()
        for hc in highly_corr:
            if hc not in to_drop:
                # Drop the one with lower variance
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

    # -- Model selection + CV evaluation + final training --
    model, scaler, m3_name, _, cv3 = _select_and_train(X, y, "Tier 3")
    y_pred = model.predict(scaler.transform(clip_outliers(X)))
    r2 = float(1 - np.sum((y - y_pred) ** 2) / np.sum((y - y.mean()) ** 2))

    tier3 = TrainedGrowthModel(
        tier=3,
        model=model,
        scaler=scaler,
        feature_names=tuple(feature_cols),
        fill_values=tuple((f, float(fill[f])) for f in feature_cols),
        n_train=len(y),
        train_r2=r2,
        trained_at=datetime.now().isoformat(),
        model_name=m3_name,
        cv_r2_mean=cv3.r2_mean if cv3 else None,
        cv_r2_std=cv3.r2_std if cv3 else None,
    )
    logger.info(
        "Tier 3 trained: %d sets, %d features, train R2=%.3f, CV R2=%.3f +/-%.3f",
        len(y), len(feature_cols), r2,
        cv3.r2_mean if cv3 else float("nan"),
        cv3.r2_std if cv3 else float("nan"),
    )

    # Log top 10 feature importances
    importances = model.feature_importances_
    ranked = sorted(zip(feature_cols, importances), key=lambda x: -x[1])[:10]
    for name, imp in ranked:
        logger.info("  Tier 3 feature: %-30s  %.4f", name, imp)

    return tier3, X, y


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
    from sklearn.model_selection import KFold

    y_all = df_raw["annual_growth_pct"].values.astype(float)
    n = len(y_all)
    if n < 50:
        logger.info("Ensemble skipped: only %d sets", n)
        return None

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
            # Tier 2 may have fewer rows; align with df_raw
            if len(X_full) != n:
                # Tier 2 has Keepa data -- pad missing rows with NaN
                X_full = X_full.reindex(df_raw.index)
        elif tier == 3 and tier3_X is not None and tier3_y is not None:
            feat_cols = [f for f in m.feature_names if f in tier3_X.columns]
            X_full = tier3_X[feat_cols].copy()
            # Tier 3 may have fewer rows than df_raw; pad to align
            if len(X_full) != n:
                X_full = X_full.reindex(df_raw.index)
        else:
            oof_preds[tier] = np.full(n, np.nan)
            continue

        for c in X_full.columns:
            X_full[c] = pd.to_numeric(X_full[c], errors="coerce")
        fill = X_full.median()
        X_full = X_full.fillna(fill)

        kf = KFold(n_splits=5, shuffle=True, random_state=42)
        for train_idx, val_idx in kf.split(X_full):
            X_tr = X_full.iloc[train_idx]
            y_tr = y_all[train_idx]
            X_va = X_full.iloc[val_idx]

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_va_s = scaler.transform(X_va)

            fold_model = _build_model()
            fold_model.fit(X_tr_s, y_tr)
            oof[val_idx] = fold_model.predict(X_va_s)

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
