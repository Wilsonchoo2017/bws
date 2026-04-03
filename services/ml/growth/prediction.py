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
from services.ml.growth.types import GrowthPrediction, TrainedGrowthModel
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

    predictions: list[GrowthPrediction] = []

    for tier_mask, model_obj in [
        (has_kp if use_tier2 else pd.Series(False, index=df_feat.index), tier2),
        (~has_kp if use_tier2 else pd.Series(True, index=df_feat.index), tier1),
    ]:
        if model_obj is None or tier_mask.sum() == 0:
            continue

        df_batch = df_feat[tier_mask].copy()
        fill_map = dict(model_obj.fill_values)

        X_batch = df_batch[list(model_obj.feature_names)].copy()
        for c in X_batch.columns:
            X_batch[c] = pd.to_numeric(X_batch[c], errors="coerce")

        n_missing_per_row = X_batch.isna().sum(axis=1)

        for f in model_obj.feature_names:
            X_batch[f] = X_batch[f].fillna(fill_map.get(f, 0))

        X_scaled = model_obj.scaler.transform(X_batch)
        preds = model_obj.model.predict(X_scaled)

        importances = model_obj.model.feature_importances_
        top_global = tuple(sorted(
            zip(model_obj.feature_names, importances),
            key=lambda x: x[1],
            reverse=True,
        )[:5])

        for i, (_, row) in enumerate(df_batch.iterrows()):
            n_feat = len(model_obj.feature_names)
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

    # Tier 3: predict using all extractor features
    if tier3 is not None:
        tier3_preds = _predict_tier3(conn, candidates, tier3)
        # Merge: prefer Tier 3 when it has enough coverage
        existing_sns = {p.set_number for p in predictions}
        for p3 in tier3_preds:
            if p3.set_number not in existing_sns:
                predictions.append(p3)
            elif p3.confidence in ("high", "moderate"):
                # Replace Tier 1 with Tier 3 if Tier 3 has good coverage
                predictions = [
                    p3 if p.set_number == p3.set_number and p.tier == 1 else p
                    for p in predictions
                ]

    return sorted(predictions, key=lambda p: p.predicted_growth_pct, reverse=True)


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


def run_pipeline(
    conn: DuckDBPyConnection,
    *,
    only_retiring: bool = False,
) -> list[GrowthPrediction]:
    """Train models and generate predictions in one call."""
    tier1, tier2, theme_stats, subtheme_stats, tier3 = train_growth_models(conn)
    return predict_growth(
        conn, tier1, tier2, theme_stats, subtheme_stats,
        only_retiring=only_retiring,
        tier3=tier3,
    )
