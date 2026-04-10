"""Keepa+BL growth model training pipeline.

Target: BrickLink current new price / RRP (real secondary market data).
Features: 26 Keepa+metadata features from Experiment 31.

Architecture:
  - Regressor: LightGBM predicting BL price / RRP ratio
  - Classifier: P(avoid) where avoid = BL price < RRP (set lost money)
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PowerTransformer

from services.ml.growth.keepa_features import (
    KEEPA_BL_FEATURES,
    engineer_keepa_bl_features,
)
from services.ml.growth.classifier import TrainedClassifier, train_classifier
from services.ml.growth.model_selection import (
    build_model,
    clip_outliers,
    compute_recency_weights,
)
from services.ml.growth.types import KellyCalibration, TrainedGrowthModel

logger = logging.getLogger(__name__)


def train_keepa_bl_models(
    *,
    base_df: pd.DataFrame,
    keepa_df: pd.DataFrame,
    target_series: pd.Series,
) -> tuple[
    TrainedGrowthModel,
    None,  # no tier2 in this architecture
    dict,  # theme_stats (empty -- not used)
    dict,  # subtheme_stats (empty)
    TrainedClassifier | None,
    None,  # no ensemble
]:
    """Train Keepa+BL regressor and classifier.

    Args:
        base_df: Metadata (set_number, theme, parts_count, rrp_usd_cents, etc.)
        keepa_df: Keepa timelines
        target_series: BL current price / RRP ratio (indexed by set_number)

    Returns:
        Same 6-tuple as legacy train_growth_models for compatibility.
    """
    logger.info("=" * 60)
    logger.info("KEEPA+BL MODEL TRAINING")
    logger.info("=" * 60)

    # Phase 1: Feature engineering
    logger.info("Phase 1: Feature engineering (%d base sets, %d keepa sets)",
                len(base_df), len(keepa_df))
    df_feat = engineer_keepa_bl_features(base_df, keepa_df)

    # Merge with target
    target_map = dict(zip(target_series.index, target_series.values))
    df_feat["target"] = df_feat["set_number"].map(target_map)
    df_feat = df_feat[df_feat["target"].notna()].copy()

    logger.info("Sets with features + target: %d", len(df_feat))

    if len(df_feat) < 50:
        raise ValueError(f"Too few training sets: {len(df_feat)} (need 50+)")

    y = df_feat["target"].values.astype(float)
    feature_names = [f for f in KEEPA_BL_FEATURES if f in df_feat.columns]
    X = df_feat[feature_names].fillna(0).copy()
    fill_values = X.median()
    X = X.fillna(fill_values)

    # Groups for CV: year_retired from base_df
    year_retired_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
    # Also try retired_date
    for _, row in base_df.iterrows():
        sn = str(row["set_number"])
        if sn not in year_retired_map or pd.isna(year_retired_map.get(sn)):
            rd = pd.to_datetime(str(row.get("retired_date", "")), errors="coerce")
            if rd is not pd.NaT:
                year_retired_map[sn] = rd.year

    yr_retired = df_feat["set_number"].map(year_retired_map)
    groups = yr_retired.fillna(2023).astype(int).values

    # Exclude 2025+ from training (barely retired)
    train_mask = groups <= 2024
    X_train = X[train_mask].copy()
    y_train = y[train_mask]
    groups_train = groups[train_mask]

    logger.info("Training on %d sets (retired <= 2024), excluded %d sets (2025+)",
                train_mask.sum(), (~train_mask).sum())

    # Winsorize target
    lo, hi = np.percentile(y_train, [2, 98])
    y_clipped = np.clip(y_train, lo, hi)

    # Recency weights
    sample_weight = compute_recency_weights(groups_train.astype(float))

    # Yeo-Johnson transform
    tt = PowerTransformer(method="yeo-johnson")
    y_transformed = tt.fit_transform(y_clipped.reshape(-1, 1)).ravel()

    # Phase 2: Cross-validation
    logger.info("Phase 2: 5-fold GroupKFold cross-validation")
    X_arr = clip_outliers(X_train).values.astype(float)

    n_splits = min(5, len(np.unique(groups_train)))
    gkf = GroupKFold(n_splits=n_splits)
    oof = np.full(len(y_clipped), np.nan)
    fold_r2s: list[float] = []

    for fold_i, (tr_idx, va_idx) in enumerate(gkf.split(X_arr, y_transformed, groups_train)):
        import lightgbm as lgb

        dtrain = lgb.Dataset(
            X_arr[tr_idx], label=y_transformed[tr_idx],
            feature_name=feature_names,
            weight=sample_weight[tr_idx] if sample_weight is not None else None,
        )
        dval = lgb.Dataset(
            X_arr[va_idx], label=y_transformed[va_idx],
            feature_name=feature_names, reference=dtrain,
        )

        model = lgb.train(
            {
                "objective": "huber", "metric": "mae",
                "learning_rate": 0.068, "num_leaves": 20, "max_depth": 8,
                "min_child_samples": 19, "subsample": 0.60,
                "colsample_bytree": 0.88, "reg_alpha": 0.35,
                "reg_lambda": 0.009, "verbosity": -1,
                "seed": 42 + fold_i,
            },
            dtrain, num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
        pred_t = model.predict(X_arr[va_idx])
        oof[va_idx] = tt.inverse_transform(pred_t.reshape(-1, 1)).ravel()

        fold_r2 = r2_score(y_clipped[va_idx], oof[va_idx])
        fold_r2s.append(fold_r2)
        yrs = sorted(np.unique(groups_train[va_idx]).tolist())
        logger.info("  Fold %d: R2=%.3f, years=%s", fold_i + 1, fold_r2, yrs)

    valid_mask = ~np.isnan(oof)
    cv_r2 = r2_score(y_clipped[valid_mask], oof[valid_mask])
    cv_r2_std = float(np.std(fold_r2s))

    from scipy.stats import spearmanr
    sp, _ = spearmanr(y_clipped[valid_mask], oof[valid_mask])
    logger.info("CV R2=%.3f +/- %.3f, Spearman=%.3f", cv_r2, cv_r2_std, sp)

    # Phase 3: Train final model on all training data
    logger.info("Phase 3: Final model on all %d training sets", len(y_clipped))

    import lightgbm as lgb

    dtrain_full = lgb.Dataset(
        X_arr, label=y_transformed, feature_name=feature_names,
        weight=sample_weight,
    )
    final_model = lgb.train(
        {
            "objective": "huber", "metric": "mae",
            "learning_rate": 0.068, "num_leaves": 20, "max_depth": 8,
            "min_child_samples": 19, "subsample": 0.60,
            "colsample_bytree": 0.88, "reg_alpha": 0.35,
            "reg_lambda": 0.009, "verbosity": -1,
        },
        dtrain_full, num_boost_round=300,
    )

    train_pred = tt.inverse_transform(final_model.predict(X_arr).reshape(-1, 1)).ravel()
    train_r2 = r2_score(y_clipped, train_pred)

    # Build Kelly calibration from CV residuals
    residuals = oof[valid_mask] - y_clipped[valid_mask]
    kelly_cal = KellyCalibration(
        residual_std=float(np.std(residuals)),
        residual_mean=float(np.mean(residuals)),
        hurdle_rate=0.10,  # 10% hurdle for BL price appreciation
        n_samples=int(valid_mask.sum()),
    )

    tier1 = TrainedGrowthModel(
        tier=1,
        model=final_model,
        scaler=None,
        feature_names=tuple(feature_names),
        fill_values=tuple((f, float(fill_values[f])) for f in feature_names),
        n_train=len(y_clipped),
        train_r2=train_r2,
        trained_at=datetime.now().isoformat(),
        model_name="lightgbm_keepa_bl",
        cv_r2_mean=cv_r2,
        cv_r2_std=cv_r2_std,
        target_transformer=tt,
        kelly_calibration=kelly_cal,
    )

    # Phase 4: Classifier
    # Finding from Exp 31d: the regressor's predicted BL/RRP ratio is a BETTER
    # loser detector (AUC=0.746) than a dedicated binary classifier (AUC=0.661).
    # So we train the classifier on the same features but use the regressor's
    # score as the primary avoid signal: pred < 1.0 = avoid.
    #
    # We still train a classifier for the P(avoid) probability display,
    # but the regressor is the authoritative signal.
    logger.info("Phase 4: Avoid classifier (avoid = BL price/RRP < 1.0)")

    y_binary = (y_clipped < 1.0).astype(float)
    n_avoid = int(y_binary.sum())
    logger.info("  Avoid class: %d / %d (%.1f%%)", n_avoid, len(y_binary),
                n_avoid / len(y_binary) * 100)

    # Convert BL ratio target to growth % for classifier compatibility
    y_growth_pct = (y_train - 1.0) * 100  # ratio -> growth %
    classifier = train_classifier(
        X_arr, y_growth_pct, feature_names,
        tuple((f, float(fill_values[f])) for f in feature_names),
        threshold=0.0,  # avoid = growth < 0% (BL price < RRP)
        tuning_trials=20,
    )

    if classifier:
        logger.info("Classifier: AUC=%.3f, F1=%.3f, Recall=%.3f",
                    classifier.cv_auc, classifier.cv_f1, classifier.cv_recall)
        logger.info("NOTE: Regressor score (pred<1.0) is the primary avoid signal (AUC=0.75 vs classifier 0.66)")
    else:
        logger.info("Classifier training returned None (too few avoid samples)")

    return tier1, None, {}, {}, classifier, None
