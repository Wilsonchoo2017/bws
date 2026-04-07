"""Growth model prediction using hurdle model.

Combines classifier P(avoid) with regressor E[growth | non-loser]
to produce risk-adjusted predictions per set.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config.ml import MLPipelineConfig
from services.ml.growth.classifier import (
    TrainedClassifier,
    hurdle_combine,
    predict_avoid_proba,
)
from services.ml.growth.features import engineer_intrinsic_features, engineer_keepa_features
from services.ml.growth.types import GrowthPrediction, TrainedEnsemble, TrainedGrowthModel

_cfg = MLPipelineConfig()

logger = logging.getLogger(__name__)


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
    """Generate hurdle-model growth predictions for candidate sets.

    Steps:
    1. Engineer features
    2. Get P(avoid) from classifier (if available)
    3. Get raw growth from regressor (Tier 2 if Keepa, else Tier 1)
    4. Combine via hurdle: P(good) * regressor + P(bad) * median_loser
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

    has_kp = df_feat["kp_bb_premium"].notna() | df_feat["kp_below_rrp_pct"].notna()
    use_tier2 = tier2 is not None and has_kp.any()

    # Tier 1: all sets
    all_preds = _predict_batch(df_feat, tier1, classifier)

    # Tier 2: sets with Keepa
    if use_tier2 and tier2 is not None:
        all_preds.extend(_predict_batch(df_feat[has_kp], tier2, classifier))

    # Ensemble or best-tier selection
    if ensemble is not None:
        predictions = _apply_ensemble(all_preds, ensemble)
    else:
        predictions = _select_best_tier(all_preds)

    return sorted(predictions, key=lambda p: p.predicted_growth_pct, reverse=True)


def _predict_batch(
    df_feat: pd.DataFrame,
    model_obj: TrainedGrowthModel,
    classifier: TrainedClassifier | None,
) -> list[GrowthPrediction]:
    """Predictions for a batch using one tier, with hurdle adjustment."""
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

    raw_growth = preds.copy()

    # Hurdle model: combine with classifier P(avoid)
    avoid_probs = None
    if classifier is not None:
        # Build classifier feature matrix (same features as tier 1)
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
        preds = hurdle_combine(preds, avoid_probs, classifier.median_loser_return)

    # Conformal intervals
    intervals: list | None = None
    if model_obj.conformal_calibration is not None:
        from services.ml.growth.conformal import batch_predict_with_intervals

        intervals = batch_predict_with_intervals(preds, model_obj.conformal_calibration)

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

        if model_obj.tier == 2 and coverage > 0.8:
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

        ap = float(avoid_probs[i]) if avoid_probs is not None else None

        # Kelly position sizing
        win_prob_i, kelly_frac_i = None, None
        if model_obj.kelly_calibration is not None:
            from services.ml.growth.training import kelly_for_prediction

            win_prob_i, kelly_frac_i = kelly_for_prediction(
                float(preds[i]), model_obj.kelly_calibration, ap,
            )

        predictions.append(GrowthPrediction(
            set_number=row["set_number"],
            title=str(row.get("title", "")),
            theme=str(row.get("theme", "")),
            predicted_growth_pct=round(float(preds[i]), 1),
            confidence=confidence,
            tier=model_obj.tier,
            feature_contributions=contribs,
            prediction_interval=intervals[i] if intervals else None,
            shap_base_value=base_val,
            avoid_probability=ap,
            raw_growth_pct=round(float(raw_growth[i]), 1),
            kelly_fraction=kelly_frac_i,
            win_probability=win_prob_i,
        ))

    return predictions


def _select_best_tier(
    all_preds: list[GrowthPrediction],
) -> list[GrowthPrediction]:
    """Best tier per set (highest tier with good confidence)."""
    by_set: dict[str, list[GrowthPrediction]] = {}
    for p in all_preds:
        by_set.setdefault(p.set_number, []).append(p)

    result: list[GrowthPrediction] = []
    for preds in by_set.values():
        good = [p for p in preds if p.confidence in ("high", "moderate")]
        if good:
            result.append(max(good, key=lambda p: p.tier))
        else:
            result.append(max(preds, key=lambda p: p.tier))

    return result


def _apply_ensemble(
    predictions: list[GrowthPrediction],
    ensemble: TrainedEnsemble,
) -> list[GrowthPrediction]:
    """Blend predictions via meta-model where all tiers available."""
    by_set: dict[str, dict[int, GrowthPrediction]] = {}
    for p in predictions:
        by_set.setdefault(p.set_number, {})[p.tier] = p

    tier_order = [int(name.replace("tier", "")) for name, _ in ensemble.weights]

    result: list[GrowthPrediction] = []
    for tier_preds in by_set.values():
        meta_feats = []
        for t in tier_order:
            if t in tier_preds:
                meta_feats.append(tier_preds[t].predicted_growth_pct)
            else:
                meta_feats.append(np.nan)

        if any(np.isnan(f) for f in meta_feats):
            best = max(tier_preds.values(), key=lambda p: p.tier)
            result.append(best)
            continue

        meta_X = np.array([meta_feats])
        meta_X_s = ensemble.meta_scaler.transform(meta_X)
        blended = float(ensemble.meta_model.predict(meta_X_s)[0])

        best = max(tier_preds.values(), key=lambda p: p.tier)
        result.append(GrowthPrediction(
            set_number=best.set_number,
            title=best.title,
            theme=best.theme,
            predicted_growth_pct=round(blended, 1),
            confidence="high" if best.confidence in ("high", "moderate") else "moderate",
            tier=4,
            feature_contributions=best.feature_contributions,
            avoid_probability=best.avoid_probability,
            raw_growth_pct=best.raw_growth_pct,
        ))

    return result
