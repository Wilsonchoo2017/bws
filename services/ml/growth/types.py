"""Data types for the growth prediction model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class PredictionInterval:
    """Conformal prediction interval."""

    point: float
    lower: float
    upper: float
    alpha: float  # e.g. 0.10 for 90% coverage


@dataclass(frozen=True)
class GrowthPrediction:
    """Prediction result for a single set."""

    set_number: str
    title: str
    theme: str
    predicted_growth_pct: float
    confidence: str  # "high", "moderate", "low"
    tier: int  # 1, 2, 3, or 4 (ensemble)
    feature_contributions: tuple[tuple[str, float], ...] = ()
    prediction_interval: PredictionInterval | None = None
    shap_base_value: float | None = None


@dataclass(frozen=True)
class TrainedGrowthModel:
    """A fitted growth model with scaler and metadata."""

    tier: int
    model: Any  # GBM, LightGBM, or similar .predict()/.feature_importances_ API
    scaler: StandardScaler
    feature_names: tuple[str, ...]
    fill_values: tuple[tuple[str, float], ...]
    n_train: int
    train_r2: float
    trained_at: str
    model_name: str = "gbm"
    cv_r2_mean: float | None = None
    cv_r2_std: float | None = None
    target_transformer: Any | None = None  # PowerTransformer for target
    conformal_calibration: Any | None = None  # ConformalCalibration


@dataclass(frozen=True)
class TrainedEnsemble:
    """Stacked ensemble combining Tier 1/2/3 predictions."""

    base_models: tuple[TrainedGrowthModel, ...]
    meta_model: Any  # Ridge or similar linear meta-learner
    meta_scaler: StandardScaler
    n_train: int
    oos_r2: float
    trained_at: str
    weights: tuple[tuple[str, float], ...] = ()  # (model_name, weight) pairs
    cv_scores: tuple[float, ...] = ()
