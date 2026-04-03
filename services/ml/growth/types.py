"""Data types for the growth prediction model."""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class GrowthPrediction:
    """Prediction result for a single set."""

    set_number: str
    title: str
    theme: str
    predicted_growth_pct: float
    confidence: str  # "high", "moderate", "low"
    tier: int  # 1 or 2
    feature_contributions: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class TrainedGrowthModel:
    """A fitted growth model with scaler and metadata."""

    tier: int
    model: GradientBoostingRegressor
    scaler: StandardScaler
    feature_names: tuple[str, ...]
    fill_values: tuple[tuple[str, float], ...]
    n_train: int
    train_r2: float
    trained_at: str
