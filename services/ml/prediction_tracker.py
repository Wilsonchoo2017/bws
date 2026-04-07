"""Prediction tracking for out-of-sample validation.

Saves a snapshot of today's ML predictions so we can compare
to actual returns in 12/24 months. This builds a real track record.

Usage:
    .venv/bin/python -m services.ml.prediction_tracker snapshot
    .venv/bin/python -m services.ml.prediction_tracker report
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)

BUY_HURDLE_PCT = 8.0
AVOID_GATE_THRESHOLD = 0.5


def save_prediction_snapshot(conn: Any) -> int:
    """Save today's ML predictions to the tracking table.

    Skips sets that already have a snapshot for today (idempotent).
    Returns the number of new predictions saved.
    """
    from db.pg.engine import get_engine
    from services.ml.growth_model import predict_growth, train_growth_models
    from services.ml.pg_queries import (
        load_growth_candidate_sets,
        load_growth_training_data,
        load_keepa_timelines,
    )

    engine = get_engine()
    df_raw = load_growth_training_data(engine)
    keepa_df = load_keepa_timelines(engine)
    candidates = load_growth_candidate_sets(engine)

    tier1, tier2, ts, ss, tier3, ensemble = train_growth_models(
        df_raw=df_raw, keepa_df=keepa_df,
    )
    predictions = predict_growth(
        candidates, keepa_df, tier1, tier2, ts, ss,
        classifier=tier3, ensemble=ensemble,
    )

    if not predictions:
        logger.warning("No predictions to save")
        return 0

    today = date.today().isoformat()
    model_version = f"gbm_t1n{tier1.n_train}_t2n{tier2.n_train if tier2 else 0}"

    saved = 0
    for pred in predictions:
        ap = pred.avoid_probability
        is_avoid = ap is not None and ap >= AVOID_GATE_THRESHOLD
        is_buy = (not is_avoid) and pred.predicted_growth_pct >= BUY_HURDLE_PCT
        interval = pred.prediction_interval

        try:
            conn.execute(
                """
                INSERT INTO ml_prediction_snapshots
                    (snapshot_date, set_number, predicted_growth_pct,
                     confidence, tier, model_version,
                     avoid_probability, buy_signal, kelly_fraction,
                     win_probability, interval_lower, interval_upper)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (snapshot_date, set_number)
                DO UPDATE SET
                    predicted_growth_pct = EXCLUDED.predicted_growth_pct,
                    confidence = EXCLUDED.confidence,
                    tier = EXCLUDED.tier,
                    model_version = EXCLUDED.model_version,
                    avoid_probability = EXCLUDED.avoid_probability,
                    buy_signal = EXCLUDED.buy_signal,
                    kelly_fraction = EXCLUDED.kelly_fraction,
                    win_probability = EXCLUDED.win_probability,
                    interval_lower = EXCLUDED.interval_lower,
                    interval_upper = EXCLUDED.interval_upper
                """,
                [
                    today, pred.set_number, pred.predicted_growth_pct,
                    pred.confidence, pred.tier, model_version,
                    ap, is_buy, pred.kelly_fraction,
                    pred.win_probability,
                    interval.lower if interval else None,
                    interval.upper if interval else None,
                ],
            )
            saved += 1
        except Exception:
            logger.debug("Skipped %s (error)", pred.set_number)

    logger.info("Saved %d prediction snapshots for %s (model: %s)", saved, today, model_version)
    return saved


def save_scored_snapshot(conn: Any, scored: dict[str, dict]) -> int:
    """Save pre-scored predictions (from growth_provider.score_all) to tracking table.

    This avoids retraining -- just persists whatever the cached predictions are.
    Returns the number of new/updated predictions saved.
    """
    if not scored:
        return 0

    today = date.today().isoformat()
    saved = 0

    for set_number, entry in scored.items():
        growth = entry.get("growth_pct")
        if growth is None:
            continue

        try:
            conn.execute(
                """
                INSERT INTO ml_prediction_snapshots
                    (snapshot_date, set_number, predicted_growth_pct,
                     confidence, tier, model_version,
                     avoid_probability, buy_signal, kelly_fraction,
                     win_probability, interval_lower, interval_upper)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (snapshot_date, set_number) DO NOTHING
                """,
                [
                    today, set_number, growth,
                    entry.get("confidence"), entry.get("tier"),
                    None,  # model_version not available from scored dict
                    entry.get("avoid_probability"),
                    entry.get("buy_signal"),
                    entry.get("kelly_fraction"),
                    entry.get("win_probability"),
                    entry.get("interval_lower"),
                    entry.get("interval_upper"),
                ],
            )
            saved += 1
        except Exception:
            logger.debug("Skipped snapshot for %s", set_number)

    if saved:
        logger.info("Auto-saved %d prediction snapshots for %s", saved, today)
    return saved


def get_prediction_history(conn: Any, set_number: str) -> list[dict]:
    """Get prediction history for a single set, ordered by date."""
    rows = conn.execute(
        """
        SELECT snapshot_date, predicted_growth_pct, confidence, tier,
               model_version, actual_growth_pct,
               avoid_probability, buy_signal, kelly_fraction,
               win_probability, interval_lower, interval_upper
        FROM ml_prediction_snapshots
        WHERE set_number = ?
        ORDER BY snapshot_date
        """,
        [set_number],
    ).fetchall()

    columns = [
        "date", "growth_pct", "confidence", "tier",
        "model_version", "actual_growth_pct",
        "avoid_probability", "buy_signal", "kelly_fraction",
        "win_probability", "interval_lower", "interval_upper",
    ]
    return [
        {col: (str(val) if col == "date" else val) for col, val in zip(columns, row)}
        for row in rows
    ]


def backfill_actuals(conn: Any) -> int:
    """Update prediction snapshots with actual growth data where available.

    Compares predicted_growth_pct vs actual BE annual_growth_pct
    for snapshots that don't yet have actual_growth_pct filled in.

    Returns number of records updated.
    """
    conn.execute("""
        UPDATE ml_prediction_snapshots ps
        SET actual_growth_pct = be.annual_growth_pct,
            actual_measured_at = CURRENT_DATE
        FROM brickeconomy_snapshots be
        WHERE ps.set_number = be.set_number
          AND ps.actual_growth_pct IS NULL
          AND be.annual_growth_pct IS NOT NULL
    """)

    n = conn.execute("""
        SELECT COUNT(*) FROM ml_prediction_snapshots
        WHERE actual_growth_pct IS NOT NULL
    """).fetchone()[0]

    logger.info("Backfilled actuals: %d total records with actuals", n)
    return n


def get_tracking_report(conn: Any) -> dict:
    """Generate a report comparing predictions to actuals."""
    snapshots = conn.execute("""
        SELECT snapshot_date, COUNT(*) as n_predictions,
               AVG(predicted_growth_pct) as avg_predicted,
               SUM(CASE WHEN actual_growth_pct IS NOT NULL THEN 1 ELSE 0 END) as n_with_actuals,
               AVG(actual_growth_pct) as avg_actual,
               AVG(ABS(predicted_growth_pct - actual_growth_pct)) as mae,
               CORR(predicted_growth_pct, actual_growth_pct) as correlation
        FROM ml_prediction_snapshots
        GROUP BY snapshot_date
        ORDER BY snapshot_date DESC
    """).fetchdf()

    if snapshots.empty:
        return {"snapshots": [], "message": "No prediction snapshots yet. Run 'snapshot' first."}

    all_with_actuals = conn.execute("""
        SELECT predicted_growth_pct, actual_growth_pct, confidence, tier,
               set_number, snapshot_date
        FROM ml_prediction_snapshots
        WHERE actual_growth_pct IS NOT NULL
    """).fetchdf()

    report: dict = {
        "snapshots": snapshots.to_dict(orient="records"),
        "total_predictions": int(conn.execute("SELECT COUNT(*) FROM ml_prediction_snapshots").fetchone()[0]),
        "total_with_actuals": len(all_with_actuals),
    }

    if not all_with_actuals.empty:
        pred = all_with_actuals["predicted_growth_pct"].values
        actual = all_with_actuals["actual_growth_pct"].values
        import numpy as np
        report["overall_mae"] = round(float(np.mean(np.abs(pred - actual))), 2)
        report["overall_correlation"] = round(float(np.corrcoef(pred, actual)[0, 1]), 3)
        report["overall_r2"] = round(float(1 - np.sum((actual - pred)**2) / np.sum((actual - actual.mean())**2)), 3)

        for conf in ["high", "moderate", "low"]:
            mask = all_with_actuals["confidence"] == conf
            if mask.sum() >= 5:
                p = all_with_actuals[mask]["predicted_growth_pct"].values
                a = all_with_actuals[mask]["actual_growth_pct"].values
                report[f"{conf}_mae"] = round(float(np.mean(np.abs(p - a))), 2)
                report[f"{conf}_n"] = int(mask.sum())

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python -m services.ml.prediction_tracker [snapshot|report|backfill]")
        sys.exit(1)

    from db.connection import get_connection

    cmd = sys.argv[1]
    conn = get_connection()

    try:
        from db.schema import init_schema
        init_schema(conn)

        if cmd == "snapshot":
            n = save_prediction_snapshot(conn)
            print(f"Saved {n} predictions")

        elif cmd == "backfill":
            n = backfill_actuals(conn)
            print(f"Backfilled {n} records with actuals")

        elif cmd == "report":
            import json
            report = get_tracking_report(conn)
            print(json.dumps(report, indent=2, default=str))

        else:
            print(f"Unknown command: {cmd}")
            sys.exit(1)
    finally:
        conn.close()
