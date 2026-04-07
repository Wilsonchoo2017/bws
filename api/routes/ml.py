"""ML prediction API routes."""

import logging

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_db
from api.serialization import sanitize_nan
from typing import Any


router = APIRouter(prefix="/ml", tags=["ml"])
logger = logging.getLogger(__name__)


@router.get("/predictions")
async def list_predictions(
    horizon: int = Query(12, description="Horizon in months (12, 24, 36)"),
    conn: Any = Depends(get_db),
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
    conn: Any = Depends(get_db),
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
async def get_model_info(conn: Any = Depends(get_db)):
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
async def get_feature_store_stats(conn: Any = Depends(get_db)):
    """Get feature store statistics."""
    from services.ml.feature_store import get_store_stats

    return get_store_stats(conn)


# ---------------------------------------------------------------------------
# Growth model (research-based tiered predictions)
# ---------------------------------------------------------------------------


@router.get("/growth/predictions")
async def list_growth_predictions(
    only_retiring: bool = Query(False, description="Only show retiring-soon sets"),
    conn: Any = Depends(get_db),
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
    conn: Any = Depends(get_db),
):
    """Get growth prediction for a single set."""
    from services.scoring.growth_provider import growth_provider

    scores = growth_provider.score_all(conn)
    pred = scores.get(set_number)
    if pred is not None:
        return sanitize_nan({"set_number": set_number, **pred})

    # No prediction -- diagnose what data is missing
    missing = _diagnose_missing_data(conn, set_number)
    return sanitize_nan({"set_number": set_number, "error": "No prediction available", **missing})


@router.get("/kelly")
async def ml_kelly_sizing(
    budget: int | None = Query(None, description="Budget in cents (e.g. 500000 = MYR 5000)"),
    max_positions: int | None = Query(None, description="Max number of positions (e.g. 10)"),
    only_retiring: bool = Query(False, description="Only retiring-soon sets"),
    conn: Any = Depends(get_db),
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
    budget: float = Query(3000, description="Budget in MYR (default 3000)"),
    risk: str = Query("balanced", description="Risk profile: aggressive, balanced, conservative"),
    max_units: int = Query(3, description="Max units per set"),
    conn: Any = Depends(get_db),
):
    """Optimize a LEGO investment portfolio.

    Returns holdings with MYR values, expected returns, drawdown risk,
    and write-off exposure. Think of it like a stock portfolio.
    """
    from services.ml.portfolio_optimizer import optimize_portfolio

    result = optimize_portfolio(
        conn,
        budget_myr=budget,
        risk_profile=risk,
        max_units_per_set=max_units,
    )

    return sanitize_nan({
        "summary": {
            "budget_myr": result.budget_myr,
            "invested_myr": result.total_cost_myr,
            "expected_profit_myr": result.expected_profit_myr,
            "expected_return_pct": result.expected_return_pct,
            "expected_12m_value_myr": result.expected_12m_value_myr,
            "expected_24m_value_myr": result.expected_24m_value_myr,
        },
        "risk": {
            "risk_profile": result.risk_profile,
            "portfolio_volatility_pct": result.portfolio_std_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "worst_case_return_pct": result.var_95_pct,
            "max_drawdown_pct": result.max_drawdown_pct,
            "writeoff_exposure_myr": result.writeoff_exposure_myr,
        },
        "composition": {
            "n_sets": result.n_sets,
            "n_units": result.n_units,
            "n_themes": result.n_themes,
            "max_theme_concentration_pct": result.max_theme_pct,
        },
        "holdings": [
            {
                "set_number": h.set_number,
                "title": h.title,
                "theme": h.theme,
                "units": h.units,
                "buy_price_myr": h.price_myr,
                "total_cost_myr": h.total_cost_myr,
                "expected_return_pct": h.predicted_growth_pct,
                "expected_profit_myr": h.expected_profit_myr,
                "expected_value_myr": h.expected_value_myr,
                "win_probability": h.win_probability,
                "worst_case_return_pct": h.worst_case_pct,
            }
            for h in result.holdings
        ],
    })


@router.get("/buy-signal/{set_number}")
async def buy_signal(
    set_number: str,
    price: float | None = Query(None, description="Your buy price in MYR (omit for RRP)"),
    discount: float = Query(0, description="Discount off RRP in percent (0-50)"),
    conn: Any = Depends(get_db),
):
    """Should you buy this set at this price?

    Returns buy/pass signal based on predicted growth vs your entry price.
    Shows effective return, break-even price, and discount scenarios.
    """
    from services.ml.buy_signal import compute_buy_signal, compute_discount_scenarios
    from services.scoring.growth_provider import growth_provider

    scores = growth_provider.score_all(conn)
    pred = scores.get(set_number)
    if pred is None:
        return {"error": f"No prediction for set {set_number}"}

    growth_pct = pred["growth_pct"]
    title = pred.get("title", set_number)
    theme = pred.get("theme", "")

    # Get RRP
    rrp_row = conn.execute(
        f"SELECT rrp_usd_cents FROM brickeconomy_snapshots "
        f"WHERE set_number = '{set_number}' AND rrp_usd_cents > 0 "
        f"ORDER BY scraped_at DESC LIMIT 1"
    ).fetchone()
    if rrp_row is None:
        return {"error": f"No RRP data for set {set_number}"}

    rrp_usd_cents = int(rrp_row[0])

    signal = compute_buy_signal(
        set_number=set_number,
        title=title,
        theme=theme,
        rrp_usd_cents=rrp_usd_cents,
        predicted_growth_pct=growth_pct,
        buy_price_myr=price,
        discount_pct=discount,
    )

    scenarios = compute_discount_scenarios(
        set_number=set_number,
        title=title,
        theme=theme,
        rrp_usd_cents=rrp_usd_cents,
        predicted_growth_pct=growth_pct,
    )

    response = {
        "signal": signal.signal,
        "reason": signal.signal_reason,
        "set_number": signal.set_number,
        "title": signal.title,
        "theme": signal.theme,
        "rrp_myr": signal.rrp_myr,
        "your_price_myr": signal.buy_price_myr,
        "discount_pct": signal.discount_pct,
        "predicted_growth_from_rrp_pct": signal.predicted_growth_from_rrp_pct,
        "effective_return_12m_pct": signal.effective_return_12m_pct,
        "effective_return_24m_pct": signal.effective_return_24m_pct,
        "expected_profit_12m_myr": signal.effective_profit_12m_myr,
        "expected_profit_24m_myr": signal.effective_profit_24m_myr,
        "expected_value_12m_myr": signal.expected_value_12m_myr,
        "expected_value_24m_myr": signal.expected_value_24m_myr,
        "max_buy_price_myr": signal.max_buy_price_myr,
        "min_discount_needed_pct": signal.break_even_discount_pct,
        "discount_scenarios": [
            {
                "discount_pct": s.discount_pct,
                "buy_price_myr": s.buy_price_myr,
                "effective_return_12m_pct": s.effective_return_12m_pct,
                "profit_12m_myr": s.effective_profit_12m_myr,
                "signal": s.signal,
            }
            for s in scenarios
        ],
    }

    # Include avoid probability if classifier is available
    if "avoid_probability" in pred:
        response["avoid_probability"] = pred["avoid_probability"]

    return sanitize_nan(response)


@router.get("/tracking/report")
async def tracking_report(conn: Any = Depends(get_db)):
    """Get prediction tracking report (predicted vs actual)."""
    from services.ml.prediction_tracker import get_tracking_report

    return sanitize_nan(get_tracking_report(conn))


@router.post("/tracking/snapshot")
async def save_tracking_snapshot(conn: Any = Depends(get_db)):
    """Save today's predictions for future validation."""
    from services.ml.prediction_tracker import backfill_actuals, save_prediction_snapshot

    n_saved = save_prediction_snapshot(conn)
    n_backfilled = backfill_actuals(conn)
    return {"saved": n_saved, "backfilled": n_backfilled}


def _diagnose_missing_data(conn: Any, set_number: str) -> dict:
    """Check what data is missing for a set to get an ML prediction.

    Returns a dict with 'missing' (list of human-readable items) and
    'has' (dict of booleans for each data source).
    """
    missing: list[str] = []
    has: dict[str, bool] = {}

    # 1. Check lego_items entry
    item_row = conn.execute(
        "SELECT 1 FROM lego_items WHERE set_number = ?", [set_number]
    ).fetchone()
    has["lego_item"] = item_row is not None
    if not has["lego_item"]:
        missing.append("Set not found in catalog (lego_items)")
        return {"missing": missing, "has": has}

    # 2. Check BrickEconomy snapshot
    be_row = conn.execute("""
        SELECT rrp_usd_cents, rating_value, review_count, pieces, minifigs, subtheme
        FROM brickeconomy_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT 1
    """, [set_number]).fetchone()

    has["brickeconomy"] = be_row is not None
    if not has["brickeconomy"]:
        missing.append("BrickEconomy data (needed for RRP, ratings, piece count)")
    else:
        rrp, rating, reviews, pieces, minifigs, subtheme = be_row
        if not rrp or rrp <= 0:
            missing.append("RRP price (rrp_usd_cents is missing or zero)")
        if rating is None:
            missing.append("Rating value (from BrickEconomy)")
        if reviews is None:
            missing.append("Review count (from BrickEconomy)")
        if not pieces:
            missing.append("Piece count")
        has["rrp"] = bool(rrp and rrp > 0)
        has["rating"] = rating is not None
        has["reviews"] = reviews is not None
        has["pieces"] = bool(pieces)
        has["minifigs"] = minifigs is not None
        has["subtheme"] = bool(subtheme)

    # 3. Check Keepa data (Tier 2)
    keepa_row = conn.execute("""
        SELECT amazon_price_json
        FROM keepa_products
        WHERE set_number = ?
        LIMIT 1
    """, [set_number]).fetchone()

    has["keepa"] = keepa_row is not None and keepa_row[0] is not None
    if not has["keepa"]:
        missing.append("Keepa Amazon price history (needed for Tier 2 prediction)")

    return {"missing": missing, "has": has}


@router.post("/growth/retrain")
async def retrain_growth_models():
    """Force retrain growth models (clears cache)."""
    from services.scoring.growth_provider import growth_provider

    stats = growth_provider.retrain()
    return {"status": "retrained", **stats}
