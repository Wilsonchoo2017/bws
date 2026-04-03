"""Growth model prediction.

Generates growth predictions using trained Tier 1/2 models.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

from config.ml import FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
from services.ml.extractors import extract_all as _extract_all_plugin
from services.ml.growth.features import engineer_intrinsic_features, engineer_keepa_features
from services.ml.growth.training import train_growth_models
from services.ml.growth.types import GrowthPrediction, TrainedEnsemble, TrainedGrowthModel
from services.ml.helpers import compute_cutoff_dates
from services.ml.queries import load_base_metadata, load_growth_candidate_sets, load_keepa_timelines

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


def predict_growth(
    conn: DuckDBPyConnection,
    tier1: TrainedGrowthModel,
    tier2: TrainedGrowthModel | None,
    theme_stats: dict,
    subtheme_stats: dict,
    *,
    only_retiring: bool = False,
    tier3: TrainedGrowthModel | None = None,
    ensemble: TrainedEnsemble | None = None,
) -> list[GrowthPrediction]:
    """Generate growth predictions for candidate sets.

    Uses Tier 2 (with Keepa features) when available, falls back to Tier 1.
    """
    candidates = load_growth_candidate_sets(conn)
    if only_retiring:
        candidates = candidates[candidates["retiring_soon"] == True]  # noqa: E712

    if candidates.empty:
        return []

    keepa_df = load_keepa_timelines(conn)

    # Engineer features using pre-computed stats (no LOO leakage)
    df_feat, _, _ = engineer_intrinsic_features(
        candidates,
        theme_stats=theme_stats,
        subtheme_stats=subtheme_stats,
    )
    df_feat = engineer_keepa_features(df_feat, keepa_df)

    # Split into tier 2 (has Keepa) and tier 1 (rest)
    has_kp = df_feat["kp_bb_premium"].notna() | df_feat["kp_below_rrp_pct"].notna()
    use_tier2 = tier2 is not None and has_kp.any()

    # Generate predictions from ALL available tiers per set
    all_tier_preds: list[GrowthPrediction] = []

    # Tier 1: predict ALL sets (always available)
    all_tier_preds.extend(_predict_batch(df_feat, tier1))

    # Tier 2: predict sets with Keepa data
    if use_tier2 and tier2 is not None:
        all_tier_preds.extend(_predict_batch(df_feat[has_kp], tier2))

    # Tier 3: predict using all extractor features
    if tier3 is not None:
        all_tier_preds.extend(_predict_tier3(conn, candidates, tier3))

    # Ensemble: blend individual tier predictions via meta-model
    if ensemble is not None:
        predictions = _apply_ensemble(all_tier_preds, ensemble)
    else:
        # Fall back to best-tier-wins logic
        predictions = _select_best_tier(all_tier_preds)

    return sorted(predictions, key=lambda p: p.predicted_growth_pct, reverse=True)


def _predict_batch(
    df_feat: pd.DataFrame,
    model_obj: TrainedGrowthModel,
) -> list[GrowthPrediction]:
    """Generate predictions for a batch of sets using a single-tier model."""
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

    # Pad missing features
    for f in model_obj.feature_names:
        if f not in X_batch.columns:
            X_batch[f] = fill_map.get(f, 0)

    X_batch = X_batch[list(model_obj.feature_names)]
    X_scaled = model_obj.scaler.transform(X_batch)
    preds = model_obj.model.predict(X_scaled)

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

        predictions.append(GrowthPrediction(
            set_number=row["set_number"],
            title=str(row.get("title", "")),
            theme=str(row.get("theme", "")),
            predicted_growth_pct=round(float(preds[i]), 1),
            confidence=confidence,
            tier=model_obj.tier,
            feature_contributions=top_global,
        ))

    return predictions


def _select_best_tier(
    all_preds: list[GrowthPrediction],
) -> list[GrowthPrediction]:
    """Select the best tier prediction per set (highest tier with good confidence)."""
    by_set: dict[str, list[GrowthPrediction]] = {}
    for p in all_preds:
        by_set.setdefault(p.set_number, []).append(p)

    result: list[GrowthPrediction] = []
    for sn, preds in by_set.items():
        # Prefer higher tiers with at least moderate confidence
        good = [p for p in preds if p.confidence in ("high", "moderate")]
        if good:
            result.append(max(good, key=lambda p: p.tier))
        else:
            result.append(max(preds, key=lambda p: p.tier))

    return result


def _predict_tier3(
    conn: "DuckDBPyConnection",
    candidates: pd.DataFrame,
    tier3: TrainedGrowthModel,
) -> list[GrowthPrediction]:
    """Generate Tier 3 predictions using extractor features."""
    set_numbers = candidates["set_number"].tolist()
    base = load_base_metadata(conn, set_numbers)
    if base.empty:
        return []

    base = compute_cutoff_dates(base, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT)

    extractor_features = _extract_all_plugin(conn, base)
    if extractor_features.empty:
        return []

    merged = candidates[["set_number", "title", "theme"]].merge(
        extractor_features, on="set_number", how="inner"
    )

    fill_map = dict(tier3.fill_values)
    available_features = [f for f in tier3.feature_names if f in merged.columns]
    if len(available_features) < len(tier3.feature_names) * 0.5:
        return []

    X = merged[available_features].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")

    n_missing_per_row = X.isna().sum(axis=1)

    for f in available_features:
        X[f] = X[f].fillna(fill_map.get(f, 0))

    # Pad missing features with fill values
    for f in tier3.feature_names:
        if f not in X.columns:
            X[f] = fill_map.get(f, 0)

    X = X[list(tier3.feature_names)]
    X_scaled = tier3.scaler.transform(X)
    preds = tier3.model.predict(X_scaled)

    importances = tier3.model.feature_importances_
    top_global = tuple(sorted(
        zip(tier3.feature_names, importances),
        key=lambda x: x[1],
        reverse=True,
    )[:5])

    predictions: list[GrowthPrediction] = []
    n_feat = len(tier3.feature_names)
    for i, (_, row) in enumerate(merged.iterrows()):
        coverage = 1 - (n_missing_per_row.iloc[i] / n_feat) if n_feat > 0 else 0

        if coverage > 0.7:
            confidence = "high"
        elif coverage > 0.4:
            confidence = "moderate"
        else:
            confidence = "low"

        predictions.append(GrowthPrediction(
            set_number=row["set_number"],
            title=str(row.get("title", "")),
            theme=str(row.get("theme", "")),
            predicted_growth_pct=round(float(preds[i]), 1),
            confidence=confidence,
            tier=3,
            feature_contributions=top_global,
        ))

    return predictions


def _apply_ensemble(
    predictions: list[GrowthPrediction],
    ensemble: TrainedEnsemble,
) -> list[GrowthPrediction]:
    """Replace predictions with ensemble-blended values where possible.

    For each set that has predictions from multiple tiers, combine them
    via the meta-model. Sets with only one tier prediction keep their
    original value.
    """
    import numpy as np

    # Group predictions by set_number
    by_set: dict[str, dict[int, GrowthPrediction]] = {}
    for p in predictions:
        by_set.setdefault(p.set_number, {})[p.tier] = p

    # Identify which tiers the ensemble expects
    tier_order = [int(name.replace("tier", "")) for name, _ in ensemble.weights]

    result: list[GrowthPrediction] = []
    for sn, tier_preds in by_set.items():
        # Build meta-feature vector from individual tier predictions
        meta_feats = []
        for t in tier_order:
            if t in tier_preds:
                meta_feats.append(tier_preds[t].predicted_growth_pct)
            else:
                meta_feats.append(np.nan)

        # Only use ensemble if we have all tiers
        if any(np.isnan(f) for f in meta_feats):
            # Fall back to best available tier
            best = max(tier_preds.values(), key=lambda p: p.tier)
            result.append(best)
            continue

        meta_X = np.array([meta_feats])
        meta_X_s = ensemble.meta_scaler.transform(meta_X)
        blended = float(ensemble.meta_model.predict(meta_X_s)[0])

        # Use the highest-tier prediction as template
        best = max(tier_preds.values(), key=lambda p: p.tier)
        result.append(GrowthPrediction(
            set_number=best.set_number,
            title=best.title,
            theme=best.theme,
            predicted_growth_pct=round(blended, 1),
            confidence="high" if best.confidence in ("high", "moderate") else "moderate",
            tier=4,  # ensemble
            feature_contributions=best.feature_contributions,
        ))

    return result


def run_pipeline(
    conn: DuckDBPyConnection,
    *,
    only_retiring: bool = False,
) -> list[GrowthPrediction]:
    """Train models and generate predictions in one call."""
    tier1, tier2, theme_stats, subtheme_stats, tier3, ensemble = train_growth_models(conn)
    return predict_growth(
        conn, tier1, tier2, theme_stats, subtheme_stats,
        only_retiring=only_retiring,
        tier3=tier3,
        ensemble=ensemble,
    )
