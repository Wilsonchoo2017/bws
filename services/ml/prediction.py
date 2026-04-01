"""Prediction pipeline for scoring sets approaching retirement.

Loads a trained model and generates predictions for sets that are
retiring soon or recently retired.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from services.ml.feature_extractors import extract_all_features
from services.ml.training import load_model
from services.ml.types import PredictionResult, TrainedModel

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


def predict_current_sets(
    conn: "DuckDBPyConnection",
    model_path: str | None = None,
    model_dir: str = "models",
) -> list[PredictionResult]:
    """Score all sets that are retiring soon.

    1. Find sets where retiring_soon=True or year_retired >= current year - 1
    2. Extract features for those sets
    3. Load trained model
    4. Generate predictions
    5. Compute feature contributions (permutation-based)
    6. Return ranked PredictionResult list
    """
    # Find candidate sets
    candidates = _find_candidate_sets(conn)
    if candidates.empty:
        logger.warning("No candidate sets found for prediction")
        return []

    set_numbers = candidates["set_number"].tolist()
    logger.info("Found %d candidate sets for prediction", len(set_numbers))

    # Extract features
    features_df = extract_all_features(conn, set_numbers)
    if features_df.empty:
        logger.warning("No features extracted for candidates")
        return []

    # Load model
    model = _load_best_model(model_path, model_dir)
    if model is None:
        logger.warning("No trained model found")
        return []

    # Align features with model's expected columns
    available = [c for c in model.feature_names if c in features_df.columns]
    missing = [c for c in model.feature_names if c not in features_df.columns]
    if missing:
        logger.warning("Missing %d features for prediction: %s", len(missing), missing[:5])
        for col in missing:
            features_df[col] = np.nan

    x = features_df[model.feature_names].fillna(
        features_df[model.feature_names].median()
    )

    # Predict
    if model.task == "regression":
        predictions = model.pipeline.predict(x.values)
        probabilities = None
    else:
        if hasattr(model.pipeline, "predict_proba"):
            probabilities = model.pipeline.predict_proba(x.values)[:, 1]
        else:
            probabilities = model.pipeline.predict(x.values).astype(float)
        predictions = probabilities

    # Compute top contributing features via permutation importance
    top_features_per_set = _compute_feature_contributions(
        model, x, predictions
    )

    # Build results
    results: list[PredictionResult] = []
    for i, (_, row) in enumerate(features_df.iterrows()):
        sn = row["set_number"]
        cand_row = candidates[candidates["set_number"] == sn]
        title = cand_row.iloc[0]["title"] if not cand_row.empty else None
        theme = cand_row.iloc[0]["theme"] if not cand_row.empty else None

        pred_return = float(predictions[i]) if model.task == "regression" else None
        pred_prob = float(probabilities[i]) if probabilities is not None else None

        # Confidence based on feature coverage
        non_null = sum(1 for c in model.feature_names if pd.notna(row.get(c)))
        coverage = non_null / len(model.feature_names) if model.feature_names else 0
        if coverage >= 0.8:
            confidence = "high"
        elif coverage >= 0.5:
            confidence = "moderate"
        else:
            confidence = "low"

        results.append(PredictionResult(
            set_number=sn,
            title=title,
            theme=theme,
            predicted_return_12m=pred_return if model.horizon_months == 12 else None,
            predicted_return_24m=pred_return if model.horizon_months == 24 else None,
            predicted_return_36m=pred_return if model.horizon_months == 36 else None,
            predicted_profitable_12m=pred_prob,
            confidence=confidence,
            top_features=top_features_per_set.get(sn, []),
        ))

    # Sort by predicted return (descending)
    results.sort(
        key=lambda r: (r.predicted_return_12m or r.predicted_return_24m or r.predicted_return_36m or 0),
        reverse=True,
    )
    return results


def predict_single_set(
    conn: "DuckDBPyConnection",
    set_number: str,
    model_path: str | None = None,
    model_dir: str = "models",
) -> PredictionResult | None:
    """Score a single set."""
    results = predict_current_sets(conn, model_path, model_dir)
    for r in results:
        if r.set_number == set_number:
            return r

    # If set wasn't in candidates, try extracting features directly
    features_df = extract_all_features(conn, [set_number])
    if features_df.empty:
        return None

    model = _load_best_model(model_path, model_dir)
    if model is None:
        return None

    for col in model.feature_names:
        if col not in features_df.columns:
            features_df[col] = np.nan

    x = features_df[model.feature_names].fillna(
        features_df[model.feature_names].median()
    )

    pred = model.pipeline.predict(x.values)
    return PredictionResult(
        set_number=set_number,
        predicted_return_12m=float(pred[0]) if model.horizon_months == 12 else None,
        predicted_return_24m=float(pred[0]) if model.horizon_months == 24 else None,
        predicted_return_36m=float(pred[0]) if model.horizon_months == 36 else None,
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _find_candidate_sets(conn: "DuckDBPyConnection") -> pd.DataFrame:
    """Find sets eligible for prediction (retiring soon or recently retired)."""
    query = """
        SELECT set_number, title, theme, year_retired, retiring_soon
        FROM lego_items
        WHERE retiring_soon = TRUE
           OR (year_retired IS NOT NULL AND year_retired >= EXTRACT(YEAR FROM CURRENT_DATE) - 1)
        ORDER BY set_number
    """
    return conn.execute(query).df()


def _load_best_model(
    model_path: str | None,
    model_dir: str,
) -> TrainedModel | None:
    """Load a model from path or find the best one in model_dir."""
    if model_path:
        try:
            return load_model(model_path)
        except Exception:
            logger.warning("Failed to load model from %s", model_path, exc_info=True)
            return None

    # Find the best model file in the directory
    model_dir_path = Path(model_dir)
    if not model_dir_path.exists():
        return None

    model_files = sorted(model_dir_path.glob("*.joblib"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in model_files:
        try:
            return load_model(str(f))
        except Exception:
            continue

    return None


def _compute_feature_contributions(
    model: TrainedModel,
    x: pd.DataFrame,
    predictions: np.ndarray,
) -> dict[str, list[tuple[str, float]]]:
    """Compute per-set top feature contributions using simple perturbation.

    For each set, perturb each feature to its median and measure
    the change in prediction. Top 5 most influential features are returned.
    """
    result: dict[str, list[tuple[str, float]]] = {}
    medians = x.median()

    for i, (_, row) in enumerate(x.iterrows()):
        contributions: list[tuple[str, float]] = []
        base_pred = predictions[i]

        for feat in model.feature_names:
            perturbed = row.copy()
            perturbed[feat] = medians[feat]
            perturbed_pred = model.pipeline.predict(
                perturbed.values.reshape(1, -1)
            )[0]
            impact = abs(base_pred - perturbed_pred)
            contributions.append((feat, float(impact)))

        contributions.sort(key=lambda x: x[1], reverse=True)
        sn = x.index[i] if hasattr(x.index, "__getitem__") else str(i)
        # Try to get set_number from the original dataframe
        result[str(sn)] = contributions[:5]

    return result
