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
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


def save_prediction_snapshot(conn: DuckDBPyConnection) -> int:
    """Save today's ML predictions to the tracking table.

    Skips sets that already have a snapshot for today (idempotent).
    Returns the number of new predictions saved.
    """
    from services.ml.growth_model import predict_growth, train_growth_models

    tier1, tier2, ts, ss, tier3, ensemble = train_growth_models(conn)
    predictions = predict_growth(conn, tier1, tier2, ts, ss, tier3=tier3, ensemble=ensemble)

    if not predictions:
        logger.warning("No predictions to save")
        return 0

    today = date.today().isoformat()
    model_version = f"gbm_t1n{tier1.n_train}_t2n{tier2.n_train if tier2 else 0}"

    saved = 0
    for pred in predictions:
        try:
            conn.execute(
                """
                INSERT INTO ml_prediction_snapshots
                    (snapshot_date, set_number, predicted_growth_pct,
                     confidence, tier, model_version)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (snapshot_date, set_number) DO NOTHING
                """,
                [today, pred.set_number, pred.predicted_growth_pct,
                 pred.confidence, pred.tier, model_version],
            )
            saved += 1
        except Exception:
            logger.debug("Skipped %s (already exists or error)", pred.set_number)

    logger.info("Saved %d prediction snapshots for %s (model: %s)", saved, today, model_version)
    return saved


def backfill_actuals(conn: DuckDBPyConnection) -> int:
    """Update prediction snapshots with actual growth data where available.

    Compares predicted_growth_pct vs actual BE annual_growth_pct
    for snapshots that don't yet have actual_growth_pct filled in.

    Returns number of records updated.
    """
    updated = conn.execute("""
        UPDATE ml_prediction_snapshots ps
        SET actual_growth_pct = be.annual_growth_pct,
            actual_measured_at = CURRENT_DATE
        FROM brickeconomy_snapshots be
        WHERE ps.set_number = be.set_number
          AND ps.actual_growth_pct IS NULL
          AND be.annual_growth_pct IS NOT NULL
    """).fetchone()

    # DuckDB doesn't return update count easily, query instead
    n = conn.execute("""
        SELECT COUNT(*) FROM ml_prediction_snapshots
        WHERE actual_growth_pct IS NOT NULL
    """).fetchone()[0]

    logger.info("Backfilled actuals: %d total records with actuals", n)
    return n


def get_tracking_report(conn: DuckDBPyConnection) -> dict:
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

    # Overall stats
    all_with_actuals = conn.execute("""
        SELECT predicted_growth_pct, actual_growth_pct, confidence, tier,
               set_number, snapshot_date
        FROM ml_prediction_snapshots
        WHERE actual_growth_pct IS NOT NULL
    """).fetchdf()

    report = {
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

        # By confidence tier
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
