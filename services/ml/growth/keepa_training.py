"""Keepa+BL classifier-only training pipeline.

Target: BrickLink current new price / RRP (real secondary market data).
Features: 43 classifier features (36 Keepa+metadata + 7 Google Trends).

Architecture (Exp 32 + Exp 33 + Exp 34 + Exp 35 + Exp 36):
  - P(avoid): BL annualized return < 10%, asymmetric weights
  - P(great_buy): BL annualized return >= 20%
  - P(good_buy): derived at prediction time as max(0, (1-P(avoid)) - P(great_buy))
  - No regressor -- buy categories from classifiers only
  - Theme-level Keepa aggregates (LOO Bayesian encoded, Exp 33)
  - Regional RRP, buy box, interactions (Exp 34)
  - Phase-aware, composite, and relative signal features (Exp 35)
  - APR skip threshold tightened 8%->10% (Exp 36, 2026-04)
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from services.ml.growth.keepa_features import (
    CLASSIFIER_FEATURES,
    GT_FEATURES,
    KEEPA_BL_FEATURES,
    compute_regional_stats,
    compute_theme_keepa_stats,
    encode_theme_keepa_features,
    engineer_gt_features,
    engineer_keepa_bl_features,
)
from services.ml.growth.classifier import TrainedClassifier, train_classifier
from services.ml.growth.model_selection import (
    clip_outliers,
    compute_recency_weights,
)
from services.ml.growth.types import TrainedGrowthModel

logger = logging.getLogger(__name__)


def train_keepa_bl_models(
    *,
    base_df: pd.DataFrame,
    keepa_df: pd.DataFrame,
    target_series: pd.Series,
    gt_df: pd.DataFrame | None = None,
) -> tuple[
    None,  # no regressor in classifier-only architecture
    None,  # no tier2
    dict,  # theme_stats (Keepa feature aggregates per theme)
    dict,  # subtheme_stats (empty)
    TrainedClassifier | None,
    None,  # no ensemble
    TrainedClassifier | None,  # great-buy classifier
]:
    """Train Keepa+BL classifiers (no regressor).

    Args:
        base_df: Metadata (set_number, theme, parts_count, rrp_usd_cents, etc.)
        keepa_df: Keepa timelines
        target_series: BL current price / RRP ratio (indexed by set_number)
        gt_df: Google Trends data (optional). GT features added to classifiers.

    Returns:
        7-tuple: (None, None, theme_stats, subtheme_stats, classifier,
        None, great_buy_classifier).
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

    # Exp 33: Theme-level Keepa feature aggregates (LOO encoded, training mode)
    theme_stats = compute_theme_keepa_stats(df_feat)
    df_feat = encode_theme_keepa_features(df_feat, theme_stats=theme_stats, training=True)
    logger.info("Theme Keepa stats: %d themes, features: theme_avg_retire_price, "
                "theme_growth_x_prem",
                len(theme_stats.get("theme_avg_retire_price", {}).get("groups", {})))

    # Exp 34: Regional RRP stats (median GBP/USD ratio for rrp_uk_premium)
    regional_stats = compute_regional_stats(base_df)
    theme_stats["regional_stats"] = regional_stats
    logger.info("Regional stats: median_gbp_usd_ratio=%.4f",
                regional_stats.get("median_gbp_usd_ratio", 0))

    # Merge GT features (for classifiers, not regressor)
    if gt_df is not None and not gt_df.empty:
        gt_feat = engineer_gt_features(gt_df, base_df)
        df_feat = df_feat.merge(gt_feat, on="set_number", how="left")
        for col in GT_FEATURES:
            if col not in df_feat.columns:
                df_feat[col] = 0.0
            else:
                df_feat[col] = df_feat[col].fillna(0.0)
        gt_coverage = (df_feat["gt_peak_value"] > 0).sum()
        logger.info("GT features merged: %d/%d sets with data (%.1f%%)",
                    gt_coverage, len(df_feat), gt_coverage / len(df_feat) * 100)
    else:
        for col in GT_FEATURES:
            df_feat[col] = 0.0
        logger.info("No GT data provided, GT features zeroed")

    logger.info("Sets with features + target: %d", len(df_feat))

    if len(df_feat) < 50:
        raise ValueError(f"Too few training sets: {len(df_feat)} (need 50+)")

    # Classifier features: base 36 + GT 7 = 43 total
    clf_feature_names = [f for f in CLASSIFIER_FEATURES if f in df_feat.columns]
    X_clf_full = df_feat[clf_feature_names].fillna(0).copy()
    clf_fill_values = X_clf_full.median()
    X_clf_full = X_clf_full.fillna(clf_fill_values)

    # Groups for CV: year_retired from base_df
    year_retired_map = dict(zip(base_df["set_number"].astype(str), base_df.get("year_retired")))
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
    X_clf_train = X_clf_full[train_mask].copy()

    logger.info("Training on %d sets (retired <= 2024), excluded %d sets (2025+)",
                train_mask.sum(), (~train_mask).sum())

    # No regressor -- classifier-only architecture (Exp 32)
    logger.info("Classifier-only architecture: no regressor trained")

    # Phase 4: Classifier (BL ground truth + asymmetric weights)
    # Exp 31h: BL annualized returns are strictly better than raw ratio for
    # classifier training. Asymmetric weights (3x strong losers, 2x losers)
    # reduce false negatives by 44% (133->75). Combined system: 98.1% WORST
    # recall, +20.6% avg return on buys.
    logger.info("Phase 4: Avoid classifier (BL ground truth + asymmetric weights)")

    from services.ml.growth.classifier import compute_avoid_sample_weights

    # Load BL annualized returns as classifier ground truth
    try:
        from db.pg.engine import get_engine as _get_engine
        from services.ml.pg_queries import load_bl_ground_truth

        _engine = _get_engine()
        bl_target = load_bl_ground_truth(_engine)
    except Exception as exc:
        logger.warning("Could not load BL ground truth: %s", exc)
        bl_target = {}

    # Classifier uses expanded feature set (base 26 + GT 7 = 33)
    X_clf_arr = clip_outliers(X_clf_train).values.astype(float)
    n_base = len([f for f in KEEPA_BL_FEATURES if f in df_feat.columns])
    logger.info("Classifier features: %d (base %d + GT %d)",
                len(clf_feature_names), n_base, len(clf_feature_names) - n_base)

    # Map BL returns to training set order
    train_set_numbers = df_feat.loc[train_mask, "set_number"].values.astype(str)
    if not bl_target:
        raise ValueError("BL ground truth required for classifier-only architecture")

    bl_mask = np.array([sn in bl_target for sn in train_set_numbers])
    y_classifier = np.array([bl_target[sn] for sn in train_set_numbers[bl_mask]])
    X_classifier = X_clf_arr[bl_mask]

    logger.info(
        "BL ground truth: %d/%d sets (%.1f%%), avoid rate %.1f%%",
        len(y_classifier), len(train_set_numbers),
        len(y_classifier) / len(train_set_numbers) * 100,
        (y_classifier < 10.0).mean() * 100,
    )

    avoid_weights = compute_avoid_sample_weights(y_classifier)
    classifier_threshold = 10.0  # annualized growth % hurdle (Exp 36)

    classifier = train_classifier(
        X_classifier, y_classifier, clf_feature_names,
        tuple((f, float(clf_fill_values[f])) for f in clf_feature_names),
        threshold=classifier_threshold,
        tuning_trials=20,
        sample_weight=avoid_weights,
    )

    if classifier:
        logger.info("Classifier: AUC=%.3f, F1=%.3f, Recall=%.3f, threshold=%.2f, features=%d",
                    classifier.cv_auc, classifier.cv_f1, classifier.cv_recall,
                    classifier.decision_threshold, len(clf_feature_names))
    else:
        logger.info("Classifier training returned None (too few avoid samples)")

    # Phase 5: Great-buy classifier (great_buy = growth >= 20%)
    # Uses same BL ground truth target and classifier features for consistency
    logger.info("Phase 5: Great-buy classifier (great_buy = growth >= 20%%)")

    great_buy_classifier = train_classifier(
        X_classifier, y_classifier, clf_feature_names,
        tuple((f, float(clf_fill_values[f])) for f in clf_feature_names),
        threshold=20.0,
        tuning_trials=20,
        invert=True,
    )

    if great_buy_classifier:
        logger.info("Great-buy classifier: AUC=%.3f, F1=%.3f, Recall=%.3f, threshold=%.2f",
                    great_buy_classifier.cv_auc, great_buy_classifier.cv_f1,
                    great_buy_classifier.cv_recall, great_buy_classifier.decision_threshold)
    else:
        logger.info("Great-buy classifier training returned None")

    return None, None, theme_stats, {}, classifier, None, great_buy_classifier
