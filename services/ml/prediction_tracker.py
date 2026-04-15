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


logger = logging.getLogger(__name__)


def save_scored_snapshot(conn: Any, scored: dict[str, dict]) -> int:
    """Save pre-scored predictions (from growth_provider.score_all) to tracking table.

    Upserts every row — if a later run in the same day produces fresh
    predictions, they overwrite. Errors are logged, not swallowed.
    """
    if not scored:
        logger.warning("save_scored_snapshot: empty scored dict, nothing to write")
        return 0

    today = date.today().isoformat()
    saved = 0
    errors = 0
    first_error: Exception | None = None

    for set_number, entry in scored.items():
        try:
            conn.execute(
                """
                INSERT INTO ml_prediction_snapshots
                    (snapshot_date, set_number, predicted_growth_pct,
                     confidence, tier, model_version,
                     avoid_probability, buy_signal, kelly_fraction,
                     win_probability, interval_lower, interval_upper,
                     buy_category, great_buy_probability, good_buy_probability)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    interval_upper = EXCLUDED.interval_upper,
                    buy_category = EXCLUDED.buy_category,
                    great_buy_probability = EXCLUDED.great_buy_probability,
                    good_buy_probability = EXCLUDED.good_buy_probability
                """,
                [
                    today, set_number, entry.get("growth_pct"),
                    entry.get("confidence"), entry.get("tier"),
                    entry.get("model_version"),
                    entry.get("avoid_probability"),
                    entry.get("buy_signal"),
                    entry.get("kelly_fraction"),
                    entry.get("win_probability"),
                    entry.get("interval_lower"),
                    entry.get("interval_upper"),
                    entry.get("buy_category"),
                    entry.get("great_buy_probability"),
                    entry.get("good_buy_probability"),
                ],
            )
            saved += 1
        except Exception as exc:
            errors += 1
            if first_error is None:
                first_error = exc

    if errors:
        logger.error(
            "save_scored_snapshot: %d errors out of %d (first: %s)",
            errors, len(scored), first_error,
        )
    logger.info("Saved %d prediction snapshots for %s", saved, today)
    return saved


def get_prediction_history(conn: Any, set_number: str) -> list[dict]:
    """Get prediction history for a single set, ordered by date."""
    rows = conn.execute(
        """
        SELECT snapshot_date, predicted_growth_pct, confidence, tier,
               model_version, actual_growth_pct,
               avoid_probability, buy_signal, kelly_fraction,
               win_probability, interval_lower, interval_upper,
               buy_category, great_buy_probability, good_buy_probability
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
        "buy_category", "great_buy_probability", "good_buy_probability",
    ]
    history = []
    for row in rows:
        record = {
            col: (str(val) if col == "date" else val)
            for col, val in zip(columns, row)
        }
        # Architecture-agnostic display metric: P(APR >= 10% hurdle).
        # Classifier-only rows have growth_pct=0 as a sentinel; the real
        # signal lives in avoid_probability.
        ap = record.get("avoid_probability")
        if ap is not None:
            record["hurdle_prob_pct"] = round((1.0 - float(ap)) * 100.0, 1)
        else:
            record["hurdle_prob_pct"] = None
        history.append(record)
    return history


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
            from services.scoring.growth_provider import growth_provider
            scored = growth_provider.score_all()
            n = save_scored_snapshot(conn, scored)
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
