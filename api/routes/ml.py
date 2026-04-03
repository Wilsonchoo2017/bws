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


# ---------------------------------------------------------------------------
# Growth model (research-based tiered predictions)
# ---------------------------------------------------------------------------


@router.get("/growth/predictions")
async def list_growth_predictions(
    only_retiring: bool = Query(False, description="Only show retiring-soon sets"),
    conn: "DuckDBPyConnection" = Depends(get_db),
):
    """Get growth predictions for all sets (tiered model from research)."""
    from services.scoring.growth_provider import growth_provider

    scores = growth_provider.score_all(conn)

    results = [
        {"set_number": sn, **vals}
        for sn, vals in sorted(scores.items(), key=lambda x: x[1].get("growth_pct", 0), reverse=True)
    ]

    if only_retiring:
        retiring = set(
            r[0] for r in conn.execute(
                "SELECT set_number FROM lego_items WHERE retiring_soon = true"
            ).fetchall()
        )
        results = [r for r in results if r["set_number"] in retiring]

    return sanitize_nan(results)


@router.get("/growth/predictions/{set_number}")
async def get_growth_prediction(
    set_number: str,
    conn: "DuckDBPyConnection" = Depends(get_db),
):
    """Get growth prediction for a single set."""
    from services.scoring.growth_provider import growth_provider

    scores = growth_provider.score_all(conn)
    pred = scores.get(set_number)
    if pred is None:
        return {"error": f"No prediction available for {set_number}"}

    return sanitize_nan({"set_number": set_number, **pred})


@router.get("/kelly")
async def ml_kelly_sizing(
    budget: int | None = Query(None, description="Budget in cents (e.g. 500000 = MYR 5000)"),
    max_positions: int | None = Query(None, description="Max number of positions (e.g. 10)"),
    only_retiring: bool = Query(False, description="Only retiring-soon sets"),
    conn: "DuckDBPyConnection" = Depends(get_db),
):
    """ML-optimized Kelly Criterion position sizing."""
    from services.ml.kelly_optimizer import compute_ml_kelly_sizing

    results = compute_ml_kelly_sizing(
        conn,
        budget_cents=budget,
        only_retiring=only_retiring,
        max_positions=max_positions,
    )

    return sanitize_nan([
        {
            "set_number": r.set_number,
            "title": r.title,
            "theme": r.theme,
            "predicted_growth_pct": r.predicted_growth_pct,
            "win_probability": r.win_probability,
            "expected_win_pct": r.expected_win_pct,
            "expected_loss_pct": r.expected_loss_pct,
            "raw_kelly": r.raw_kelly,
            "half_kelly": r.half_kelly,
            "recommended_pct": r.recommended_pct,
            "recommended_amount_cents": int(budget * r.recommended_pct) if budget else None,
            "confidence": r.confidence,
            "ml_tier": r.ml_tier,
        }
        for r in results
    ])


@router.get("/portfolio")
async def optimize_portfolio_endpoint(
    budget: float = Query(1000, description="Budget in USD"),
    risk: str = Query("balanced", description="Risk profile: aggressive, balanced, conservative"),
    max_units: int = Query(3, description="Max units per set"),
    conn: "DuckDBPyConnection" = Depends(get_db),
):
    """Optimize a LEGO investment portfolio using Mean-Variance model."""
    from services.ml.portfolio_optimizer import optimize_portfolio

    result = optimize_portfolio(
        conn,
        budget_usd=budget,
        risk_profile=risk,
        max_units_per_set=max_units,
    )

    return sanitize_nan({
        "budget_usd": result.budget_usd,
        "risk_profile": result.risk_profile,
        "total_cost_usd": result.total_cost_usd,
        "expected_return_pct": result.expected_return_pct,
        "portfolio_std_pct": result.portfolio_std_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "var_95_pct": result.var_95_pct,
        "n_sets": result.n_sets,
        "n_units": result.n_units,
        "n_themes": result.n_themes,
        "max_theme_concentration_pct": result.max_theme_pct,
        "holdings": [
            {
                "set_number": h.set_number,
                "title": h.title,
                "theme": h.theme,
                "units": h.units,
                "price_usd": h.price_usd,
                "total_cost_usd": h.total_cost_usd,
                "predicted_growth_pct": h.predicted_growth_pct,
                "expected_profit_usd": h.expected_profit_usd,
                "confidence": h.confidence,
                "ml_tier": h.ml_tier,
            }
            for h in result.holdings
        ],
    })


@router.get("/tracking/report")
async def tracking_report(conn: "DuckDBPyConnection" = Depends(get_db)):
    """Get prediction tracking report (predicted vs actual)."""
    from services.ml.prediction_tracker import get_tracking_report

    return sanitize_nan(get_tracking_report(conn))


@router.post("/tracking/snapshot")
async def save_tracking_snapshot(conn: "DuckDBPyConnection" = Depends(get_db)):
    """Save today's predictions for future validation."""
    from services.ml.prediction_tracker import backfill_actuals, save_prediction_snapshot

    n_saved = save_prediction_snapshot(conn)
    n_backfilled = backfill_actuals(conn)
    return {"saved": n_saved, "backfilled": n_backfilled}


@router.post("/growth/retrain")
async def retrain_growth_models(conn: "DuckDBPyConnection" = Depends(get_db)):
    """Force retrain growth models (clears cache)."""
    from services.scoring.growth_provider import growth_provider

    stats = growth_provider.retrain(conn)
    return {"status": "retrained", **stats}
