"""Growth model prediction — simplified production pipeline.

Supports two model types (via config/model_registry.py):
  - legacy_be: Trained on BE annual_growth_pct, uses intrinsic+Keepa features
  - keepa_bl: Trained on BL price/RRP, uses Keepa+metadata features (Exp 31)

Architecture:
  1. Regressor: E[growth] — predicted growth % (or BL/RRP ratio converted to %)
  2. Classifier: P(avoid) — gate to filter out losers
  3. Buy signal: pass classifier AND growth >= hurdle
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config.ml import MLPipelineConfig
from services.ml.growth.classifier import (
    TrainedClassifier,
    predict_avoid_proba,
    predict_class_proba,
)
from services.ml.growth.types import GrowthPrediction, TrainedEnsemble, TrainedGrowthModel

_cfg = MLPipelineConfig()

logger = logging.getLogger(__name__)

# Sets with P(avoid) above this are flagged as AVOID
# (Exp 36: avoid means APR < 10%)
AVOID_GATE_THRESHOLD = 0.5

# Minimum predicted growth to trigger a BUY signal
BUY_HURDLE_PCT = 10.0

# P(great_buy) threshold for GREAT category
GREAT_BUY_THRESHOLD = 0.6

# P(good_buy) threshold for GOOD category
# good_buy = max(0, (1 - P(avoid)) - P(great_buy)) — derived, not trained
GOOD_BUY_THRESHOLD = 0.30

# Regressor fallback: predicted growth >= this for GOOD category
GOOD_BUY_HURDLE_PCT = 10.0


def _is_keepa_bl_model(tier1: TrainedGrowthModel | None) -> bool:
    """Detect if this is a Keepa+BL model by model_name."""
    if tier1 is None:
        return False
    return tier1.model_name == "lightgbm_keepa_bl"


def predict_growth(
    candidates: pd.DataFrame,
    keepa_df: pd.DataFrame,
    tier1: TrainedGrowthModel | None,
    tier2: TrainedGrowthModel | None,
    theme_stats: dict,
    subtheme_stats: dict,
    *,
    classifier: TrainedClassifier | None = None,
    ensemble: TrainedEnsemble | None = None,
    great_buy_classifier: TrainedClassifier | None = None,
    gt_df: pd.DataFrame | None = None,
) -> list[GrowthPrediction]:
    """Generate growth predictions with buy/avoid signals.

    Supports two modes:
    - Classifier-only (tier1=None): categories from P(avoid) + P(great_buy)
    - Full model (tier1 present): regressor + classifiers
    """
    if candidates.empty:
        return []

    # Classifier-only mode: no regressor, categories from classifiers
    if tier1 is None:
        df_feat = _engineer_keepa_bl(candidates, keepa_df, gt_df=gt_df, theme_stats=theme_stats)
        return _predict_classifier_only(
            df_feat, classifier, great_buy_classifier,
        )

    if _is_keepa_bl_model(tier1):
        df_feat = _engineer_keepa_bl(candidates, keepa_df, gt_df=gt_df, theme_stats=theme_stats)
    else:
        df_feat = _engineer_legacy_be(candidates, keepa_df, theme_stats, subtheme_stats)

    model_obj = tier1
    is_ratio_target = _is_keepa_bl_model(tier1)
    predictions = _predict_batch(
        df_feat, model_obj, classifier,
        ratio_to_growth=is_ratio_target,
        great_buy_classifier=great_buy_classifier,
    )

    return sorted(predictions, key=lambda p: p.predicted_growth_pct, reverse=True)


def _engineer_keepa_bl(
    candidates: pd.DataFrame,
    keepa_df: pd.DataFrame,
    *,
    gt_df: pd.DataFrame | None = None,
    theme_stats: dict | None = None,
) -> pd.DataFrame:
    """Feature engineering for Keepa+BL model (Exp 31) + GT (Exp 32) + theme (Exp 33)."""
    from services.ml.growth.keepa_features import (
        GT_FEATURES,
        engineer_gt_features,
        engineer_keepa_bl_features,
    )

    df_feat = engineer_keepa_bl_features(
        candidates, keepa_df, theme_stats=theme_stats if theme_stats else None,
    )

    if gt_df is not None and not gt_df.empty:
        gt_feat = engineer_gt_features(gt_df, candidates)
        df_feat = df_feat.merge(gt_feat, on="set_number", how="left")

    for col in GT_FEATURES:
        if col not in df_feat.columns:
            df_feat[col] = 0.0
        else:
            df_feat[col] = df_feat[col].fillna(0.0)

    return df_feat


def _engineer_legacy_be(
    candidates: pd.DataFrame,
    keepa_df: pd.DataFrame,
    theme_stats: dict,
    subtheme_stats: dict,
) -> pd.DataFrame:
    """Feature engineering for legacy BE model."""
    from services.ml.growth.features import engineer_intrinsic_features, engineer_keepa_features
    from services.ml.growth.seasonality_features import engineer_q4_seasonal_features
    df_feat, _, _ = engineer_intrinsic_features(
        candidates, theme_stats=theme_stats, subtheme_stats=subtheme_stats,
    )
    df_kp = engineer_keepa_features(df_feat, keepa_df)
    return engineer_q4_seasonal_features(df_kp, keepa_df)


def _predict_classifier_only(
    df_feat: pd.DataFrame,
    classifier: TrainedClassifier | None,
    great_buy_classifier: TrainedClassifier | None,
) -> list[GrowthPrediction]:
    """Classifier-only predictions: categories from P(avoid) + P(great_buy).

    No regressor -- growth_pct is set to 0. Buy categories:
      WORST: P(avoid) >= avoid_threshold
      GREAT: P(great_buy) >= great_threshold
      GOOD:  P(great_buy) >= GOOD_BUY_THRESHOLD (but below great)
      SKIP:  everything else
    """
    if df_feat.empty:
        return []

    # P(avoid)
    avoid_probs = np.zeros(len(df_feat))
    if classifier is not None:
        clf_feats = [f for f in classifier.feature_names if f in df_feat.columns]
        X_clf = df_feat[clf_feats].copy()
        for c in X_clf.columns:
            X_clf[c] = pd.to_numeric(X_clf[c], errors="coerce")
        clf_fill = dict(classifier.fill_values)
        for f in clf_feats:
            X_clf[f] = X_clf[f].fillna(clf_fill.get(f, 0))
        for f in classifier.feature_names:
            if f not in X_clf.columns:
                X_clf[f] = clf_fill.get(f, 0)
        X_clf = X_clf[list(classifier.feature_names)]
        avoid_probs = predict_avoid_proba(X_clf, classifier)

    # P(great_buy)
    great_buy_probs = np.zeros(len(df_feat))
    if great_buy_classifier is not None:
        gb_feats = [f for f in great_buy_classifier.feature_names if f in df_feat.columns]
        X_gb = df_feat[gb_feats].copy()
        for c in X_gb.columns:
            X_gb[c] = pd.to_numeric(X_gb[c], errors="coerce")
        gb_fill = dict(great_buy_classifier.fill_values)
        for f in gb_feats:
            X_gb[f] = X_gb[f].fillna(gb_fill.get(f, 0))
        for f in great_buy_classifier.feature_names:
            if f not in X_gb.columns:
                X_gb[f] = gb_fill.get(f, 0)
        X_gb = X_gb[list(great_buy_classifier.feature_names)]
        great_buy_probs = predict_class_proba(X_gb, great_buy_classifier)

    avoid_threshold = classifier.decision_threshold if classifier else AVOID_GATE_THRESHOLD
    great_threshold = great_buy_classifier.decision_threshold if great_buy_classifier else GREAT_BUY_THRESHOLD

    predictions: list[GrowthPrediction] = []
    for i, (_, row) in enumerate(df_feat.iterrows()):
        ap = float(avoid_probs[i])
        gbp = float(great_buy_probs[i])
        # P(good_buy) = P(10 <= APR < 20) derived from the two trained heads
        good_bp = max(0.0, min(1.0, (1.0 - ap) - gbp))

        if ap >= avoid_threshold:
            category = "WORST"
        elif gbp >= great_threshold:
            category = "GREAT"
        elif good_bp >= GOOD_BUY_THRESHOLD:
            category = "GOOD"
        else:
            category = "SKIP"

        predictions.append(GrowthPrediction(
            set_number=str(row.get("set_number", "")),
            title=str(row.get("title", "")),
            theme=str(row.get("theme", "")),
            predicted_growth_pct=0.0,
            confidence="high" if classifier and great_buy_classifier else "low",
            tier=1,
            avoid_probability=ap,
            great_buy_probability=gbp,
            good_buy_probability=good_bp,
            buy_category=category,
            raw_growth_pct=0.0,
        ))

    return sorted(predictions, key=lambda p: p.great_buy_probability or 0, reverse=True)


def _predict_batch(
    df_feat: pd.DataFrame,
    model_obj: TrainedGrowthModel,
    classifier: TrainedClassifier | None,
    *,
    ratio_to_growth: bool = False,
    great_buy_classifier: TrainedClassifier | None = None,
) -> list[GrowthPrediction]:
    """Predictions for all sets: regressor growth + classifier gate + buy signal.

    Args:
        ratio_to_growth: If True, model predicts BL/RRP ratio and we convert
            to growth %: growth_pct = (ratio - 1) * 100
    """
    if df_feat.empty:
        return []

    fill_map = dict(model_obj.fill_values)
    feat_names = [f for f in model_obj.feature_names if f in df_feat.columns]
    if len(feat_names) < len(model_obj.feature_names) * 0.5:
        return []

    X_batch = df_feat[feat_names].copy()
    for c in X_batch.columns:
        X_batch[c] = pd.to_numeric(X_batch[c], errors="coerce")

    n_missing_per_row = X_batch.isna().sum(axis=1)

    for f in feat_names:
        X_batch[f] = X_batch[f].fillna(fill_map.get(f, 0))

    for f in model_obj.feature_names:
        if f not in X_batch.columns:
            X_batch[f] = fill_map.get(f, 0)

    X_batch = X_batch[list(model_obj.feature_names)]
    if model_obj.scaler:
        X_scaled = pd.DataFrame(
            model_obj.scaler.transform(X_batch),
            columns=model_obj.feature_names,
            index=X_batch.index,
        )
    else:
        X_scaled = X_batch
    preds = model_obj.model.predict(X_scaled)

    if model_obj.target_transformer is not None:
        preds = model_obj.target_transformer.inverse_transform(
            preds.reshape(-1, 1),
        ).ravel()

    # For Keepa+BL model: convert BL/RRP ratio to growth %
    if ratio_to_growth:
        preds = (preds - 1.0) * 100

    preds = np.clip(preds, -50.0, 200.0)

    # Isotonic calibration
    if model_obj.isotonic_calibrator is not None:
        from services.ml.growth.calibration import apply_calibration

        preds = apply_calibration(preds, model_obj.isotonic_calibrator)

    predicted_growth = preds.copy()

    # Classifier: P(avoid)
    avoid_probs = None
    if classifier is not None:
        clf_feats = [f for f in classifier.feature_names if f in df_feat.columns]
        X_clf = df_feat.loc[X_batch.index, clf_feats].copy()
        for c in X_clf.columns:
            X_clf[c] = pd.to_numeric(X_clf[c], errors="coerce")
        clf_fill = dict(classifier.fill_values)
        for f in clf_feats:
            X_clf[f] = X_clf[f].fillna(clf_fill.get(f, 0))
        for f in classifier.feature_names:
            if f not in X_clf.columns:
                X_clf[f] = clf_fill.get(f, 0)
        X_clf = X_clf[list(classifier.feature_names)]

        avoid_probs = predict_avoid_proba(X_clf, classifier)

    # Great-buy classifier: P(growth >= 20%)
    great_buy_probs = None
    if great_buy_classifier is not None:
        gb_feats = [f for f in great_buy_classifier.feature_names if f in df_feat.columns]
        X_gb = df_feat.loc[X_batch.index, gb_feats].copy()
        for c in X_gb.columns:
            X_gb[c] = pd.to_numeric(X_gb[c], errors="coerce")
        gb_fill = dict(great_buy_classifier.fill_values)
        for f in gb_feats:
            X_gb[f] = X_gb[f].fillna(gb_fill.get(f, 0))
        for f in great_buy_classifier.feature_names:
            if f not in X_gb.columns:
                X_gb[f] = gb_fill.get(f, 0)
        X_gb = X_gb[list(great_buy_classifier.feature_names)]

        great_buy_probs = predict_class_proba(X_gb, great_buy_classifier)

    # Conformal intervals
    intervals: list | None = None
    if model_obj.conformal_calibration is not None:
        from services.ml.growth.conformal import batch_predict_with_intervals

        intervals = batch_predict_with_intervals(predicted_growth, model_obj.conformal_calibration)

    # SHAP explanations
    shap_explanations = None
    if _cfg.compute_shap:
        try:
            from services.ml.growth.explainer import explain_predictions

            shap_explanations = explain_predictions(
                model_obj.model, X_scaled, model_obj.feature_names,
                top_k=_cfg.shap_top_k,
            )
        except Exception:
            pass

    try:
        importances = model_obj.model.feature_importances_
    except AttributeError:
        # lgb.train() returns Booster which uses feature_importance() method
        importances = model_obj.model.feature_importance(importance_type="gain")
    top_global = tuple(sorted(
        zip(model_obj.feature_names, importances),
        key=lambda x: x[1],
        reverse=True,
    )[:5])

    predictions: list[GrowthPrediction] = []
    n_feat = len(model_obj.feature_names)

    for i, (_, row) in enumerate(df_feat.loc[X_batch.index].iterrows()):
        coverage = 1 - (n_missing_per_row.iloc[i] / n_feat) if n_feat > 0 else 0
        growth_i = float(predicted_growth[i])
        ap = float(avoid_probs[i]) if avoid_probs is not None else None
        gbp = float(great_buy_probs[i]) if great_buy_probs is not None else None
        # P(good_buy) = P(10 <= APR < 20) derived from the two trained heads
        good_bp: float | None = None
        if ap is not None and gbp is not None:
            good_bp = max(0.0, min(1.0, (1.0 - ap) - gbp))

        # Buy category from combined classifier signals
        # Use auto-tuned thresholds from classifiers when available
        avoid_threshold = classifier.decision_threshold if classifier is not None else AVOID_GATE_THRESHOLD
        great_threshold = great_buy_classifier.decision_threshold if great_buy_classifier is not None else GREAT_BUY_THRESHOLD
        if ap is not None and ap >= avoid_threshold:
            category = "WORST"
        elif gbp is not None and gbp >= great_threshold:
            category = "GREAT"
        elif good_bp is not None and good_bp >= GOOD_BUY_THRESHOLD:
            category = "GOOD"
        elif growth_i >= GOOD_BUY_HURDLE_PCT:
            category = "GOOD"
        else:
            category = "SKIP"

        # Confidence from feature coverage
        if coverage > 0.8:
            confidence = "high"
        elif coverage > 0.7:
            confidence = "moderate"
        else:
            confidence = "low"

        # SHAP or global importances
        if shap_explanations and i < len(shap_explanations):
            shap_ex = shap_explanations[i]
            contribs = shap_ex.top_positive + shap_ex.top_negative
            base_val = shap_ex.base_value
        else:
            contribs = top_global
            base_val = None

        # Kelly position sizing
        win_prob_i, kelly_frac_i = None, None
        if model_obj.kelly_calibration is not None:
            from services.ml.growth.training import kelly_for_prediction

            win_prob_i, kelly_frac_i = kelly_for_prediction(
                growth_i, model_obj.kelly_calibration, ap,
            )

        predictions.append(GrowthPrediction(
            set_number=row["set_number"],
            title=str(row.get("title", "")),
            theme=str(row.get("theme", "")),
            predicted_growth_pct=round(growth_i, 1),
            confidence=confidence,
            tier=1,
            feature_contributions=contribs,
            prediction_interval=intervals[i] if intervals else None,
            shap_base_value=base_val,
            avoid_probability=ap,
            great_buy_probability=gbp,
            good_buy_probability=good_bp,
            buy_category=category,
            raw_growth_pct=round(growth_i, 1),
            kelly_fraction=kelly_frac_i,
            win_probability=win_prob_i,
        ))

    return predictions
