"""Protocol definitions for the ML pipeline.

Defines the interfaces (structural subtyping) that decouple
business logic from concrete implementations. Implementations
satisfy these protocols implicitly -- no explicit inheritance needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd
    from duckdb import DuckDBPyConnection

    from config.ml import MLPipelineConfig
    from services.ml.types import FeatureMeta


@runtime_checkable
class FeatureExtractor(Protocol):
    """Extracts features from one data source.

    Each extractor is responsible for a single data source (e.g. BrickEconomy,
    Keepa, Google Trends). It declares which features it produces and extracts
    them given pre-loaded base metadata.
    """

    @property
    def name(self) -> str:
        """Human-readable extractor name (e.g. 'brickeconomy')."""
        ...

    @property
    def features(self) -> tuple[FeatureMeta, ...]:
        """Feature metadata this extractor produces."""
        ...

    def extract(
        self,
        conn: DuckDBPyConnection,
        base: pd.DataFrame,
    ) -> pd.DataFrame:
        """Extract features for sets in base DataFrame.

        Args:
            conn: Database connection for loading source data.
            base: Base metadata with set_number, cutoff_year, cutoff_month, etc.

        Returns:
            DataFrame with 'set_number' column plus one column per feature.
        """
        ...


@runtime_checkable
class PriceSource(Protocol):
    """Resolves a transacted price at a given year/month for a set.

    Multiple sources form a chain of responsibility -- the first to return
    a non-None price wins.
    """

    @property
    def name(self) -> str:
        """Source identifier (e.g. 'bricklink', 'brickeconomy_chart')."""
        ...

    def get_price(
        self,
        identifier: str,
        target_year: int,
        target_month: int,
        half_window: int,
    ) -> int | None:
        """Return the price in cents at the target month, or None.

        Args:
            identifier: Set number or item ID depending on source.
            target_year: Year to look up.
            target_month: Month to look up.
            half_window: Half-width of smoothing window in months.
        """
        ...


@runtime_checkable
class PipelineBuilder(Protocol):
    """Builds sklearn pipelines for a specific ML task type.

    Each builder produces a list of named (model_name, pipeline) tuples
    for the training loop to iterate over.
    """

    @property
    def task(self) -> str:
        """Task identifier: 'regression', 'classification', or 'inversion'."""
        ...

    def build(
        self,
        config: MLPipelineConfig,
    ) -> list[tuple[str, object]]:
        """Return named sklearn pipelines for this task.

        Args:
            config: Pipeline configuration (random_state, etc.).

        Returns:
            List of (model_name, sklearn_pipeline) tuples.
        """
        ...


@runtime_checkable
class MetricsEvaluator(Protocol):
    """Evaluates model predictions for a specific task type.

    Returns task-appropriate metrics without repurposing unrelated fields.
    """

    @property
    def task(self) -> str:
        """Task identifier this evaluator handles."""
        ...

    def evaluate(
        self,
        y_true: np.ndarray,
        y_pred_or_prob: np.ndarray,
        model_name: str,
        horizon_months: int,
    ) -> object:
        """Compute task-specific evaluation metrics.

        Args:
            y_true: Ground truth values.
            y_pred_or_prob: Predictions (regression) or probabilities (classification).
            model_name: Model identifier for labeling.
            horizon_months: Prediction horizon.

        Returns:
            Task-specific metrics dataclass (RegressionMetrics, ClassificationMetrics,
            or InversionMetrics).
        """
        ...
