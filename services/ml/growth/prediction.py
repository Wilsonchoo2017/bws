"""Growth model prediction — simplified production pipeline.

Architecture:
  1. Classifier: P(avoid) — gate to filter out losers
  2. Regressor: E[growth] — predicted annual growth %
  3. Buy signal: pass classifier AND growth >= hurdle

No T1/T2/ensemble complexity. One regressor, one classifier, one answer.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config.ml import MLPipelineConfig
from services.ml.growth.classifier import (
    TrainedClassifier,
    predict_avoid_proba,
)
from services.ml.growth.features import engineer_intrinsic_features, engineer_keepa_features
from services.ml.growth.types import GrowthPrediction, TrainedEnsemble, TrainedGrowthModel

_cfg = MLPipelineConfig()

logger = logging.getLogger(__name__)

# Sets with P(avoid) above this are flagged as AVOID
AVOID_GATE_THRESHOLD = 0.5

# Minimum predicted growth to trigger a BUY signal
BUY_HURDLE_PCT = 8.0


def predict_growth(
    candidates: pd.DataFrame,
    keepa_df: pd.DataFrame,
    tier1: TrainedGrowthModel,
    tier2: TrainedGrowthModel | None,
    theme_stats: dict,
    subtheme_stats: dict,
    *,
    classifier: TrainedClassifier | None = None,
    ensemble: TrainedEnsemble | None = None,
) -> list[GrowthPrediction]:
    """Generate growth predictions with buy/avoid signals.

    Steps:
    1. Engineer features (intrinsic + Keepa)
    2. Regressor predicts growth % (uses tier1 model on all sets)
    3. Classifier computes P(avoid)
    4. Buy signal = P(avoid) < gate AND growth >= hurdle
    """
    if candidates.empty:
        return []

    # Engineer features using pre-computed stats (no LOO leakage)
    df_feat, _, _ = engineer_intrinsic_features(
        candidates,
        theme_stats=theme_stats,
        subtheme_stats=subtheme_stats,
    )
    df_feat = engineer_keepa_features(df_feat, keepa_df)

    # Use tier1 (primary model) for all sets
    model_obj = tier1
    predictions = _predict_batch(df_feat, model_obj, classifier)

    return sorted(predictions, key=lambda p: p.predicted_growth_pct, reverse=True)


def _predict_batch(
    df_feat: pd.DataFrame,
    model_obj: TrainedGrowthModel,
    classifier: TrainedClassifier | None,
) -> list[GrowthPrediction]:
    """Predictions for all sets: regressor growth + classifier gate + buy signal."""
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
    X_scaled = model_obj.scaler.transform(X_batch) if model_obj.scaler else X_batch.values
    preds = model_obj.model.predict(X_scaled)

    if model_obj.target_transformer is not None:
        preds = model_obj.target_transformer.inverse_transform(
            preds.reshape(-1, 1),
        ).ravel()

    preds = np.clip(preds, 0.0, 50.0)

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

        avoid_probs = predict_avoid_proba(X_clf.values, classifier)

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

    importances = model_obj.model.feature_importances_
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
            raw_growth_pct=round(growth_i, 1),
            kelly_fraction=kelly_frac_i,
            win_probability=win_prob_i,
        ))

    return predictions
