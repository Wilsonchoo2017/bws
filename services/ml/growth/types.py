"""Data types for the growth prediction model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    avoid_probability: float | None = None  # P(avoid) from classifier
    raw_growth_pct: float | None = None  # regressor output before hurdle
    kelly_fraction: float | None = None  # recommended position size (0-1)
    win_probability: float | None = None  # P(return > hurdle)


@dataclass(frozen=True)
class KellyCalibration:
    """Error distribution from CV residuals, used for position sizing."""

    residual_std: float  # std of (actual - predicted) from CV
    residual_mean: float
    hurdle_rate: float  # 8% default
    n_samples: int
    # Pre-computed Kelly params at key growth levels
    # Maps predicted_growth_pct -> (win_prob, kelly_fraction)
    kelly_table: tuple[tuple[float, float, float], ...] = ()  # (growth, win_prob, kelly)


@dataclass(frozen=True)
class TrainedGrowthModel:
    """A fitted growth regressor with scaler and metadata."""

    tier: int
    model: Any
    scaler: Any | None
    feature_names: tuple[str, ...]
    fill_values: tuple[tuple[str, float], ...]
    n_train: int
    train_r2: float
    trained_at: str
    model_name: str = "lightgbm"
    cv_r2_mean: float | None = None
    cv_r2_std: float | None = None
    target_transformer: Any | None = None
    conformal_calibration: Any | None = None
    isotonic_calibrator: Any | None = None
    kelly_calibration: KellyCalibration | None = None


@dataclass(frozen=True)
class TrainedEnsemble:
    """Stacked ensemble combining Tier 1/2/3 predictions."""

    base_models: tuple[TrainedGrowthModel, ...]
    meta_model: Any
    meta_scaler: Any
    n_train: int
    oos_r2: float
    trained_at: str
    weights: tuple[tuple[str, float], ...] = ()
    cv_scores: tuple[float, ...] = ()
