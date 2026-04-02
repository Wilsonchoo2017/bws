"""ML prediction API routes."""

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_db
from api.serialization import sanitize_nan

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

router = APIRouter(prefix="/ml", tags=["ml"])
logger = logging.getLogger(__name__)


@router.get("/predictions")
async def list_predictions(
    horizon: int = Query(12, description="Horizon in months (12, 24, 36)"),
    conn: "DuckDBPyConnection" = Depends(get_db),
):
    """Get ML predictions for sets approaching retirement."""
    from services.ml.prediction import predict_current_sets

    results = predict_current_sets(conn)
    return sanitize_nan([
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


@router.get("/predictions/{set_number}")
async def get_set_prediction(
    set_number: str,
    horizon: int = Query(12, description="Horizon in months"),
    conn: "DuckDBPyConnection" = Depends(get_db),
):
    """Get ML prediction for a single set."""
    from services.ml.prediction import predict_single_set

    result = predict_single_set(conn, set_number)
    if result is None:
        return {"error": f"No prediction available for {set_number}"}
    return sanitize_nan({
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


@router.get("/model-info")
async def get_model_info(conn: "DuckDBPyConnection" = Depends(get_db)):
    """Get info about trained models."""
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

    return sanitize_nan({
        "models": runs.to_dict(orient="records"),
    })


@router.get("/feature-store/stats")
async def get_feature_store_stats(conn: "DuckDBPyConnection" = Depends(get_db)):
    """Get feature store statistics."""
    from services.ml.feature_store import get_store_stats

    return get_store_stats(conn)
