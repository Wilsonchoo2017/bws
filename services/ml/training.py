"""Model training for the ML pipeline.

Trains multiple models (regression + classification) using time-series
cross-validation. Composes pure computation steps with an impure
data-loading boundary.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from config.ml import MLPipelineConfig
from services.ml.evaluation import (
    evaluate_classification,
    evaluate_inversion,
    evaluate_regression,
    format_metrics_table,
)
from services.ml.feature_selection import select_features
from services.ml.feature_store import load_feature_store
from services.ml.persistence import load_model, record_model_run, save_model
from services.ml.pipelines import build_pipelines
from services.ml.queries import load_year_retired
from services.ml.types import ModelMetrics, TrainedModel

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# Re-export persistence functions for backward compatibility
__all__ = [
    "train_pipeline",
    "save_model",
    "load_model",
    "record_model_run",
]


def train_pipeline(
    conn: "DuckDBPyConnection",
    horizon_months: int = 12,
    task: str = "regression",
    config: MLPipelineConfig | None = None,
) -> list[TrainedModel]:
    """Full training pipeline.

    Steps:
    1. Load feature store
    2. Run feature selection
    3. Time-series split (sort by year_retired, no shuffle)
    4. Train multiple models
    5. Evaluate on held-out test set
    6. Return ranked results
    """
    if config is None:
        config = MLPipelineConfig()

    # 1. Load feature store (impure boundary)
    df = load_feature_store(conn, horizon_months)
    if df.empty:
        logger.warning("Feature store is empty for horizon=%dm", horizon_months)
        return []

    # 2. Prepare training data
    target_col = _get_target_column(task)
    valid = _prepare_training_data(df, target_col, config)
    if valid is None:
        return []

    # 3. Feature selection
    exclude = {"set_number", "target_return", "target_profitable", "target_avoid"}
    feature_cols = [c for c in valid.columns if c not in exclude]
    selection = select_features(valid, target_col, feature_cols, config, task=task)
    selected = selection.selected_features
    if not selected:
        logger.warning("No features selected")
        return []

    logger.info(
        "Training with %d features on %d samples (horizon=%dm, task=%s)",
        len(selected), len(valid), horizon_months, task,
    )

    # 4. Time-series split
    train_df, test_df = _time_series_split(conn, valid, config)
    if train_df is None:
        return []

    # 5. Prepare feature matrices
    x_train, y_train, x_test, y_test = _prepare_matrices(
        train_df, test_df, selected, target_col, task
    )

    # 6. Build pipelines (via registry -- OCP compliant)
    pipelines = build_pipelines(task, config)

    # 7. Train and evaluate each model
    now = datetime.now(timezone.utc).isoformat()
    results: list[TrainedModel] = []

    for name, pipeline in pipelines:
        trained = _train_and_evaluate(
            name=name,
            pipeline=pipeline,
            x_train=x_train,
            y_train=y_train,
            x_test=x_test,
            y_test=y_test,
            selected=selected,
            horizon_months=horizon_months,
            task=task,
            config=config,
            trained_at=now,
        )
        if trained is not None:
            results.append(trained)

    # 8. Rank results
    results = _rank_models(results, task)

    metrics_list = [r.metrics for r in results]
    logger.info("Training results:\n%s", format_metrics_table(metrics_list))

    return results


# ---------------------------------------------------------------------------
# Pure helper functions (each does one thing)
# ---------------------------------------------------------------------------


def _get_target_column(task: str) -> str:
    """Map task name to target column name."""
    mapping = {
        "regression": "target_return",
        "inversion": "target_avoid",
        "classification": "target_profitable",
    }
    return mapping.get(task, "target_profitable")


def _prepare_training_data(
    df: pd.DataFrame,
    target_col: str,
    config: MLPipelineConfig,
) -> pd.DataFrame | None:
    """Validate and filter training data."""
    if target_col not in df.columns:
        logger.warning("Target column %s not found", target_col)
        return None

    valid = df.dropna(subset=[target_col])
    if len(valid) < config.min_training_samples:
        logger.warning(
            "Only %d samples (need %d). Skipping training.",
            len(valid), config.min_training_samples,
        )
        return None

    return valid


def _time_series_split(
    conn: "DuckDBPyConnection",
    df: pd.DataFrame,
    config: MLPipelineConfig,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Split data chronologically by retirement year."""
    sorted_df = _sort_chronologically(conn, df)

    split_idx = int(len(sorted_df) * (1 - config.test_fraction))
    train_df = sorted_df.iloc[:split_idx]
    test_df = sorted_df.iloc[split_idx:]

    if len(train_df) < 20 or len(test_df) < 10:
        logger.warning(
            "Train=%d, test=%d: too small for reliable results",
            len(train_df), len(test_df),
        )
        return None, None

    return train_df, test_df


def _sort_chronologically(
    conn: "DuckDBPyConnection",
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Sort DataFrame by set retirement year for time-series splitting."""
    set_numbers = df["set_number"].tolist()
    if not set_numbers:
        return df

    years_df = load_year_retired(conn, set_numbers)
    if years_df.empty:
        return df

    merged = df.merge(years_df, on="set_number", how="left")
    merged = merged.sort_values("year_retired", na_position="last").reset_index(drop=True)
    merged = merged.drop(columns=["year_retired"], errors="ignore")
    return merged


def _prepare_matrices(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    selected: list[str],
    target_col: str,
    task: str,
) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame, np.ndarray]:
    """Prepare X/y matrices for training and testing."""
    x_train = train_df[selected].fillna(train_df[selected].median())
    y_train = train_df[target_col].values
    x_test = test_df[selected].fillna(train_df[selected].median())
    y_test = test_df[target_col].values

    if task in ("classification", "inversion"):
        y_train = y_train.astype(int)
        y_test = y_test.astype(int)

    return x_train, y_train, x_test, y_test


def _rank_models(results: list[TrainedModel], task: str) -> list[TrainedModel]:
    """Rank trained models by task-appropriate metric."""
    if task == "regression":
        return sorted(results, key=lambda r: r.metrics.quintile_spread, reverse=True)
    if task == "inversion":
        return sorted(results, key=lambda r: r.metrics.hit_rate, reverse=True)
    return sorted(
        results,
        key=lambda r: r.metrics.roc_auc if r.metrics.roc_auc else 0,
        reverse=True,
    )


def _train_and_evaluate(
    *,
    name: str,
    pipeline: object,
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    x_test: pd.DataFrame,
    y_test: np.ndarray,
    selected: list[str],
    horizon_months: int,
    task: str,
    config: MLPipelineConfig,
    trained_at: str,
) -> TrainedModel | None:
    """Train one model and evaluate it."""
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score

    try:
        n_splits = min(config.n_cv_splits, len(x_train) // 10)
        if n_splits < 2:
            n_splits = 2
        cv = TimeSeriesSplit(n_splits=n_splits)

        scoring = "r2" if task == "regression" else "roc_auc"
        cv_scores = cross_val_score(
            pipeline, x_train.values, y_train, cv=cv, scoring=scoring
        )
        logger.info(
            "%s CV %s: %.4f +/- %.4f",
            name, scoring,
            float(np.mean(cv_scores)), float(np.std(cv_scores)),
        )

        pipeline.fit(x_train.values, y_train)

        metrics = _evaluate_model(
            pipeline, x_test, y_test, name, horizon_months, task
        )

        metrics = ModelMetrics(
            model_name=metrics.model_name,
            horizon_months=metrics.horizon_months,
            task=metrics.task,
            r_squared=metrics.r_squared,
            roc_auc=metrics.roc_auc,
            hit_rate=metrics.hit_rate,
            quintile_spread=metrics.quintile_spread,
            sharpe_like=metrics.sharpe_like,
            n_train=len(x_train),
            n_test=len(x_test),
        )

        return TrainedModel(
            model_name=name,
            horizon_months=horizon_months,
            task=task,
            pipeline=pipeline,
            metrics=metrics,
            feature_names=selected,
            trained_at=trained_at,
        )

    except Exception:
        logger.warning("Failed to train %s", name, exc_info=True)
        return None


def _evaluate_model(
    pipeline: object,
    x_test: pd.DataFrame,
    y_test: np.ndarray,
    model_name: str,
    horizon_months: int,
    task: str,
) -> ModelMetrics:
    """Evaluate a fitted model on test data."""
    if task == "regression":
        y_pred = pipeline.predict(x_test.values)
        return evaluate_regression(y_test, y_pred, model_name, horizon_months)

    if hasattr(pipeline, "predict_proba"):
        y_prob = pipeline.predict_proba(x_test.values)[:, 1]
    else:
        y_prob = pipeline.predict(x_test.values).astype(float)

    if task == "inversion":
        y_returns = np.zeros_like(y_test, dtype=float)
        return evaluate_inversion(
            y_test, y_prob, y_returns, model_name, horizon_months
        )

    return evaluate_classification(y_test, y_prob, model_name, horizon_months)
