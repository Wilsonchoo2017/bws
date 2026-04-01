"""Model training for the ML pipeline.

Trains multiple models (regression + classification) using time-series
cross-validation. Follows the pattern established in optimizer.py.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from config.ml import MLPipelineConfig
from services.ml.evaluation import (
    evaluate_classification,
    evaluate_regression,
    format_metrics_table,
)
from services.ml.feature_selection import select_features
from services.ml.feature_store import load_feature_store
from services.ml.types import ModelMetrics, TrainedModel

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


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
    4. Train multiple models with TimeSeriesSplit CV
    5. Evaluate on held-out test set
    6. Return ranked results

    Args:
        conn: DuckDB connection
        horizon_months: Target horizon (12, 24, or 36)
        task: "regression" or "classification"
        config: Pipeline configuration

    Returns:
        List of TrainedModel, ranked by quintile_spread (regression)
        or roc_auc (classification).
    """
    if config is None:
        config = MLPipelineConfig()

    # 1. Load feature store
    df = load_feature_store(conn, horizon_months)
    if df.empty:
        logger.warning("Feature store is empty for horizon=%dm", horizon_months)
        return []

    target_col = "target_return" if task == "regression" else "target_profitable"
    if target_col not in df.columns:
        logger.warning("Target column %s not found", target_col)
        return []

    # Drop rows with missing target
    valid = df.dropna(subset=[target_col])
    if len(valid) < config.min_training_samples:
        logger.warning(
            "Only %d samples (need %d). Skipping training.",
            len(valid),
            config.min_training_samples,
        )
        return []

    # Identify feature columns (everything except set_number and target cols)
    exclude = {"set_number", "target_return", "target_profitable"}
    feature_cols = [c for c in valid.columns if c not in exclude]

    # 2. Feature selection
    selection = select_features(valid, target_col, feature_cols, config)
    selected = selection.selected_features
    if not selected:
        logger.warning("No features selected")
        return []

    logger.info(
        "Training with %d features on %d samples (horizon=%dm, task=%s)",
        len(selected),
        len(valid),
        horizon_months,
        task,
    )

    # 3. Time-series split: sort by set retirement year (proxy for time)
    # We need to join back year_retired for sorting
    sorted_df = _sort_chronologically(conn, valid)

    split_idx = int(len(sorted_df) * (1 - config.test_fraction))
    train_df = sorted_df.iloc[:split_idx]
    test_df = sorted_df.iloc[split_idx:]

    if len(train_df) < 20 or len(test_df) < 10:
        logger.warning(
            "Train=%d, test=%d: too small for reliable results",
            len(train_df),
            len(test_df),
        )
        return []

    x_train = train_df[selected].fillna(train_df[selected].median())
    y_train = train_df[target_col].values
    x_test = test_df[selected].fillna(train_df[selected].median())
    y_test = test_df[target_col].values

    if task == "classification":
        y_train = y_train.astype(int)
        y_test = y_test.astype(int)

    # 4. Train models
    pipelines = _build_pipelines(task, config)
    results: list[TrainedModel] = []
    now = datetime.now(timezone.utc).isoformat()

    for name, pipeline in pipelines:
        trained = _train_single_model(
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

    # 5. Rank results
    if task == "regression":
        results.sort(key=lambda r: r.metrics.quintile_spread, reverse=True)
    else:
        results.sort(
            key=lambda r: r.metrics.roc_auc if r.metrics.roc_auc else 0,
            reverse=True,
        )

    # Log results table
    metrics_list = [r.metrics for r in results]
    logger.info("Training results:\n%s", format_metrics_table(metrics_list))

    return results


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
    conn: "DuckDBPyConnection",
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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _sort_chronologically(
    conn: "DuckDBPyConnection",
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Sort DataFrame by set retirement year for time-series splitting."""
    # Get year_retired for each set
    set_numbers = df["set_number"].tolist()
    if not set_numbers:
        return df

    placeholders = ", ".join(f"'{s}'" for s in set_numbers)
    query = f"""
        SELECT set_number, year_retired
        FROM lego_items
        WHERE set_number IN ({placeholders})
    """
    years_df = conn.execute(query).df()
    if years_df.empty:
        return df

    merged = df.merge(years_df, on="set_number", how="left")
    merged = merged.sort_values("year_retired", na_position="last").reset_index(drop=True)
    merged = merged.drop(columns=["year_retired"], errors="ignore")
    return merged


def _build_pipelines(task: str, config: MLPipelineConfig) -> list[tuple[str, object]]:
    """Build named sklearn pipelines for the given task."""
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Lasso, LogisticRegression, Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if task == "regression":
        return [
            (
                "Ridge",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler()),
                    ("model", Ridge(alpha=1.0, random_state=config.random_state)),
                ]),
            ),
            (
                "Lasso",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler()),
                    ("model", Lasso(alpha=0.01, random_state=config.random_state, max_iter=5000)),
                ]),
            ),
            (
                "GBRT",
                HistGradientBoostingRegressor(
                    max_iter=200,
                    max_depth=4,
                    learning_rate=0.05,
                    random_state=config.random_state,
                ),
            ),
        ]

    return [
        (
            "LogisticRegression",
            Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", LogisticRegression(
                    C=1.0, random_state=config.random_state, max_iter=1000
                )),
            ]),
        ),
        (
            "GBClassifier",
            HistGradientBoostingClassifier(
                max_iter=200,
                max_depth=4,
                learning_rate=0.05,
                random_state=config.random_state,
            ),
        ),
    ]


def _train_single_model(
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

        # Cross-validation
        scoring = "r2" if task == "regression" else "roc_auc"
        cv_scores = cross_val_score(
            pipeline, x_train.values, y_train, cv=cv, scoring=scoring
        )
        logger.info(
            "%s CV %s: %.4f +/- %.4f",
            name,
            scoring,
            float(np.mean(cv_scores)),
            float(np.std(cv_scores)),
        )

        # Fit on full training set
        pipeline.fit(x_train.values, y_train)

        # Evaluate on test set
        if task == "regression":
            y_pred = pipeline.predict(x_test.values)
            metrics = evaluate_regression(y_test, y_pred, name, horizon_months)
        else:
            if hasattr(pipeline, "predict_proba"):
                y_prob = pipeline.predict_proba(x_test.values)[:, 1]
            else:
                y_prob = pipeline.predict(x_test.values).astype(float)
            metrics = evaluate_classification(y_test, y_prob, name, horizon_months)

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
