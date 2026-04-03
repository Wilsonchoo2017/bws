"""Model persistence: save, load, and record model training runs.

Separates I/O concerns (disk serialization, DB recording) from
the training logic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from services.ml.types import ModelMetrics, TrainedModel

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


def save_model(model: TrainedModel, directory: str = "models") -> str:
    """Serialize a trained model to disk using joblib.

    Returns the path to the saved file.
    """
    import joblib

    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)

    filename = f"{model.model_name}_{model.task}_{model.horizon_months}m.joblib"
    filepath = path / filename
    joblib.dump(
        {
            "model_name": model.model_name,
            "horizon_months": model.horizon_months,
            "task": model.task,
            "pipeline": model.pipeline,
            "feature_names": model.feature_names,
            "metrics": model.metrics,
            "trained_at": model.trained_at,
        },
        filepath,
    )
    logger.info("Saved model to %s", filepath)
    return str(filepath)


def load_model(filepath: str) -> TrainedModel:
    """Load a serialized model from disk."""
    import joblib

    data = joblib.load(filepath)
    return TrainedModel(
        model_name=data["model_name"],
        horizon_months=data["horizon_months"],
        task=data["task"],
        pipeline=data["pipeline"],
        feature_names=data["feature_names"],
        metrics=data["metrics"],
        trained_at=data["trained_at"],
    )


def record_model_run(
    conn: DuckDBPyConnection,
    model: TrainedModel,
    artifact_path: str | None = None,
) -> None:
    """Record model training run in ml_model_runs table."""
    conn.execute(
        """
        INSERT INTO ml_model_runs
            (id, model_name, horizon_months, task, r_squared, roc_auc,
             hit_rate, quintile_spread, n_train, n_test, feature_count,
             artifact_path)
        VALUES (
            nextval('ml_model_runs_id_seq'),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            model.model_name,
            model.horizon_months,
            model.task,
            model.metrics.r_squared,
            model.metrics.roc_auc,
            model.metrics.hit_rate,
            model.metrics.quintile_spread,
            model.metrics.n_train,
            model.metrics.n_test,
            len(model.feature_names),
            artifact_path,
        ],
    )
