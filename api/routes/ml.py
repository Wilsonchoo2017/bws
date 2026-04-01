"""ML prediction API routes."""

import logging
import math

from fastapi import APIRouter, Query

from db.connection import get_connection

router = APIRouter(prefix="/ml", tags=["ml"])
logger = logging.getLogger(__name__)


def _sanitize_nan(obj: object) -> object:
    """Replace NaN/Inf with None for JSON serialization."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


@router.get("/predictions")
async def list_predictions(
    horizon: int = Query(12, description="Horizon in months (12, 24, 36)"),
):
    """Get ML predictions for sets approaching retirement."""
    from services.ml.prediction import predict_current_sets

    conn = get_connection()
    try:
        results = predict_current_sets(conn)
        return _sanitize_nan([
            {
                "set_number": r.set_number,
                "title": r.title,
                "theme": r.theme,
                "predicted_return_12m": r.predicted_return_12m,
                "predicted_return_24m": r.predicted_return_24m,
                "predicted_return_36m": r.predicted_return_36m,
                "predicted_profitable_12m": r.predicted_profitable_12m,
                "confidence": r.confidence,
                "top_features": r.top_features,
            }
            for r in results
        ])
    finally:
        conn.close()


@router.get("/predictions/{set_number}")
async def get_set_prediction(
    set_number: str,
    horizon: int = Query(12, description="Horizon in months"),
):
    """Get ML prediction for a single set."""
    from services.ml.prediction import predict_single_set

    conn = get_connection()
    try:
        result = predict_single_set(conn, set_number)
        if result is None:
            return {"error": f"No prediction available for {set_number}"}
        return _sanitize_nan({
            "set_number": result.set_number,
            "title": result.title,
            "theme": result.theme,
            "predicted_return_12m": result.predicted_return_12m,
            "predicted_return_24m": result.predicted_return_24m,
            "predicted_return_36m": result.predicted_return_36m,
            "predicted_profitable_12m": result.predicted_profitable_12m,
            "confidence": result.confidence,
            "top_features": result.top_features,
        })
    finally:
        conn.close()


@router.get("/model-info")
async def get_model_info():
    """Get info about trained models."""
    conn = get_connection()
    try:
        runs = conn.execute("""
            SELECT model_name, horizon_months, task, r_squared, roc_auc,
                   hit_rate, quintile_spread, n_train, n_test, feature_count,
                   trained_at
            FROM ml_model_runs
            ORDER BY trained_at DESC
            LIMIT 10
        """).df()

        if runs.empty:
            return {"models": [], "message": "No models trained yet"}

        return _sanitize_nan({
            "models": runs.to_dict(orient="records"),
        })
    finally:
        conn.close()


@router.get("/feature-store/stats")
async def get_feature_store_stats():
    """Get feature store statistics."""
    from services.ml.feature_store import get_store_stats

    conn = get_connection()
    try:
        return get_store_stats(conn)
    finally:
        conn.close()
