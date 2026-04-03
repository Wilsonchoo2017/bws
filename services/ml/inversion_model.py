"""Munger inversion model -- predict which sets to AVOID.

Combines ML classifier probability with rule-based red flag signals
to produce a final avoid recommendation per set.

"All I want to know is where I'm going to die, so I'll never go there."
-- Charlie Munger
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from config.ml import InversionConfig
from services.ml.feature_store import load_feature_store
from services.ml.target import compute_outcome_labels, compute_retirement_returns
from services.ml.training import load_model

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InversionPrediction:
    """Prediction output for the inversion (avoid) model."""

    set_number: str
    title: str | None = None
    theme: str | None = None
    avoid_probability: float = 0.0
    red_flag_score: float | None = None
    combined_score: float = 0.0  # Weighted blend of ML + red flags
    outcome_label: str | None = None  # Actual outcome if known
    confidence: str = "low"
    top_risk_factors: list[tuple[str, float]] = field(default_factory=list)


# Weight for combining ML probability and red flag score
ML_WEIGHT = 0.6
RED_FLAG_WEIGHT = 0.4


def predict_avoids(
    conn: "DuckDBPyConnection",
    model_path: str | None = None,
    horizon_months: int = 12,
    config: InversionConfig | None = None,
) -> list[InversionPrediction]:
    """Generate avoid predictions for all sets in the feature store.

    Combines:
    1. ML classifier: trained probability of underperformance
    2. Red flag score: rule-based danger signals (when available)

    Args:
        conn: DuckDB connection.
        model_path: Path to serialized inversion model. If None, uses ML only.
        horizon_months: Prediction horizon.
        config: Inversion thresholds.

    Returns:
        List of InversionPrediction sorted by combined_score descending (worst first).
    """
    if config is None:
        config = InversionConfig()

    # Load feature store
    df = load_feature_store(conn, horizon_months)
    if df.empty:
        logger.warning("Feature store is empty for horizon=%dm", horizon_months)
        return []

    # Load item metadata for titles/themes
    metadata = _load_metadata(conn, df["set_number"].tolist())

    # Get actual outcomes if available (for validation)
    returns_df = compute_retirement_returns(conn)
    outcomes_df = compute_outcome_labels(returns_df, config) if not returns_df.empty else pd.DataFrame()

    # ML predictions
    ml_probs = _get_ml_probabilities(df, model_path)

    # Build predictions
    predictions: list[InversionPrediction] = []
    for idx, row in df.iterrows():
        set_number = row["set_number"]
        meta = metadata.get(set_number, {})

        avoid_prob = ml_probs.get(set_number, 0.0)

        # Look up actual outcome if available
        outcome_label = None
        col = f"outcome_{horizon_months}m"
        if not outcomes_df.empty and col in outcomes_df.columns:
            match = outcomes_df[outcomes_df["set_number"] == set_number]
            if not match.empty:
                outcome_label = match.iloc[0].get(col)

        # Combined score (ML only if no red flags available)
        combined = avoid_prob

        # Confidence based on how extreme the prediction is
        if avoid_prob >= 0.7:
            confidence = "high"
        elif avoid_prob >= 0.4:
            confidence = "moderate"
        else:
            confidence = "low"

        predictions.append(InversionPrediction(
            set_number=set_number,
            title=meta.get("title"),
            theme=meta.get("theme"),
            avoid_probability=avoid_prob,
            red_flag_score=None,  # Populated when red_flags module is integrated
            combined_score=combined,
            outcome_label=outcome_label,
            confidence=confidence,
        ))

    # Sort by combined score descending (worst first)
    predictions.sort(key=lambda p: p.combined_score, reverse=True)
    return predictions


def blend_scores(
    ml_probability: float,
    red_flag_score: float | None,
) -> float:
    """Combine ML probability and red flag score into a single avoid score.

    Args:
        ml_probability: Classifier probability of underperformance (0-1).
        red_flag_score: Rule-based danger score (0-100), or None.

    Returns:
        Combined score (0-1).
    """
    if red_flag_score is None:
        return ml_probability

    # Normalize red flag score to 0-1
    rf_normalized = red_flag_score / 100.0
    return ML_WEIGHT * ml_probability + RED_FLAG_WEIGHT * rf_normalized


def _get_ml_probabilities(
    df: pd.DataFrame,
    model_path: str | None,
) -> dict[str, float]:
    """Get ML avoid probabilities for each set in the DataFrame."""
    if model_path is None:
        # No model available -- return zeros
        return {row["set_number"]: 0.0 for _, row in df.iterrows()}

    try:
        model = load_model(model_path)
    except Exception as exc:
        logger.warning("Could not load inversion model: %s", exc)
        return {row["set_number"]: 0.0 for _, row in df.iterrows()}

    exclude = {"set_number", "target_return", "target_profitable", "target_avoid"}
    feature_cols = [c for c in model.feature_names if c in df.columns]
    if not feature_cols:
        logger.warning("No matching features between model and feature store")
        return {row["set_number"]: 0.0 for _, row in df.iterrows()}

    x = df[feature_cols].fillna(df[feature_cols].median())

    pipeline = model.pipeline
    if hasattr(pipeline, "predict_proba"):
        probs = pipeline.predict_proba(x.values)[:, 1]
    else:
        probs = pipeline.predict(x.values).astype(float)

    return dict(zip(df["set_number"].tolist(), probs.tolist()))


def _load_metadata(
    conn: "DuckDBPyConnection",
    set_numbers: list[str],
) -> dict[str, dict]:
    """Load title and theme for a list of sets."""
    if not set_numbers:
        return {}

    placeholders = ", ".join(f"'{s}'" for s in set_numbers)
    query = f"""
        SELECT set_number, title, theme
        FROM lego_items
        WHERE set_number IN ({placeholders})
    """
    df = conn.execute(query).df()
    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        result[row["set_number"]] = {
            "title": row.get("title"),
            "theme": row.get("theme"),
        }
    return result
