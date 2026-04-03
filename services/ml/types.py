"""Data models for the ML pipeline.

All models are frozen dataclasses for immutability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FeatureMeta:
    """Metadata for a single registered feature."""

    name: str
    source_table: str
    description: str
    dtype: str = "float"  # "float", "int", "categorical"
    is_enabled: bool = True


@dataclass(frozen=True)
class FeatureRow:
    """One row of materialized features for a set."""

    set_number: str
    year_retired: int | None
    rrp_usd_cents: int | None
    target_return_12m: float | None
    target_return_24m: float | None
    target_return_36m: float | None
    features: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelMetrics:
    """Evaluation metrics for a trained model."""

    model_name: str
    horizon_months: int
    task: str  # "regression" or "classification"
    r_squared: float
    roc_auc: float | None = None
    hit_rate: float = 0.0
    quintile_spread: float = 0.0
    sharpe_like: float = 0.0
    n_train: int = 0
    n_test: int = 0


@dataclass(frozen=True)
class TrainedModel:
    """A trained model with its metadata."""

    model_name: str
    horizon_months: int
    task: str
    pipeline: Any  # sklearn Pipeline (not serializable in dataclass)
    metrics: ModelMetrics
    feature_names: list[str] = field(default_factory=list)
    trained_at: str = ""


@dataclass(frozen=True)
class PredictionResult:
    """Prediction output for a single set."""

    set_number: str
    title: str | None = None
    theme: str | None = None
    predicted_return_12m: float | None = None
    predicted_return_24m: float | None = None
    predicted_return_36m: float | None = None
    predicted_profitable_12m: float | None = None  # probability
    confidence: str = "low"  # "high", "moderate", "low"
    top_features: list[tuple[str, float]] = field(default_factory=list)


@dataclass(frozen=True)
class SelectionResult:
    """Result of automated feature selection."""

    selected_features: list[str] = field(default_factory=list)
    dropped_features: list[str] = field(default_factory=list)
    method_results: dict[str, dict[str, float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Task-specific metrics (Phase 0 -- ISP-compliant replacements for
# the repurposed ModelMetrics fields in inversion/classification tasks)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegressionMetrics:
    """Evaluation metrics for regression models."""

    model_name: str
    horizon_months: int
    r_squared: float
    hit_rate: float = 0.0
    quintile_spread: float = 0.0
    sharpe_like: float = 0.0
    n_train: int = 0
    n_test: int = 0

    def to_model_metrics(self) -> ModelMetrics:
        """Backward-compatible conversion to legacy ModelMetrics."""
        return ModelMetrics(
            model_name=self.model_name,
            horizon_months=self.horizon_months,
            task="regression",
            r_squared=self.r_squared,
            hit_rate=self.hit_rate,
            quintile_spread=self.quintile_spread,
            sharpe_like=self.sharpe_like,
            n_train=self.n_train,
            n_test=self.n_test,
        )


@dataclass(frozen=True)
class ClassificationMetrics:
    """Evaluation metrics for classification models."""

    model_name: str
    horizon_months: int
    roc_auc: float | None = None
    hit_rate: float = 0.0
    quintile_spread: float = 0.0
    n_train: int = 0
    n_test: int = 0

    def to_model_metrics(self) -> ModelMetrics:
        """Backward-compatible conversion to legacy ModelMetrics."""
        return ModelMetrics(
            model_name=self.model_name,
            horizon_months=self.horizon_months,
            task="classification",
            r_squared=0.0,
            roc_auc=self.roc_auc,
            hit_rate=self.hit_rate,
            quintile_spread=self.quintile_spread,
            n_train=self.n_train,
            n_test=self.n_test,
        )


@dataclass(frozen=True)
class InversionMetrics:
    """Evaluation metrics for inversion (avoid) models.

    Each field has clear semantics -- no repurposing of unrelated fields.
    """

    model_name: str
    horizon_months: int
    roc_auc: float | None = None
    precision_avoid: float = 0.0
    recall_avoid: float = 0.0
    avoided_loss_pct: float = 0.0
    bottom_quintile_accuracy: float = 0.0
    false_alarm_rate: float = 0.0
    net_precision: float = 0.0
    n_train: int = 0
    n_test: int = 0

    def to_model_metrics(self) -> ModelMetrics:
        """Backward-compatible conversion to legacy ModelMetrics.

        Maps inversion-specific fields to the legacy layout used by
        format_metrics_table and record_model_run.
        """
        return ModelMetrics(
            model_name=self.model_name,
            horizon_months=self.horizon_months,
            task="inversion",
            r_squared=self.avoided_loss_pct,
            roc_auc=self.roc_auc,
            hit_rate=self.bottom_quintile_accuracy,
            quintile_spread=self.net_precision,
            sharpe_like=self.recall_avoid,
            n_train=self.n_train,
            n_test=self.n_test,
        )
