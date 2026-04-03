"""ML-optimized Kelly Criterion position sizing.

Uses the growth model's predictions and known error distribution
to compute per-set Kelly fractions instead of bin-level averages.

Approach:
1. ML model predicts expected growth for each set
2. LOO residuals define the prediction error distribution
3. For each set, we simulate the return distribution:
   predicted_growth + error ~ Normal(0, sigma)
4. From that distribution, derive per-set win_prob and payoff_ratio
5. Compute Kelly fraction: f* = (b*p - q) / b

This gives every set a unique, calibrated bet size based on how
confident the model is about that specific set.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.model_selection import LeaveOneOut, cross_val_predict

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# Safety parameters
KELLY_FRACTION: float = 0.5  # Half-Kelly
MAX_POSITION_PCT: float = 0.25  # Max 25% of portfolio in one set
MIN_PREDICTED_GROWTH: float = 2.0  # Don't bet on sets predicted below 2% growth
# "Win" threshold: we need to beat opportunity cost (e.g., index fund returns)
# LEGO sets have storage costs + capital lockup. Require 8% to call it a "win".
PROFIT_THRESHOLD: float = 8.0


@dataclass(frozen=True)
class MLKellyResult:
    """Per-set Kelly sizing from ML predictions."""

    set_number: str
    title: str
    theme: str
    predicted_growth_pct: float
    win_probability: float
    expected_win_pct: float
    expected_loss_pct: float
    raw_kelly: float
    half_kelly: float
    recommended_pct: float  # After caps and adjustments
    confidence: str
    ml_tier: int


@dataclass(frozen=True)
class MLKellyCalibration:
    """Error distribution learned from LOO residuals."""

    residual_mean: float
    residual_std: float
    residual_skew: float
    n_samples: int
    # Percentile-based error bounds
    error_p10: float  # 10th percentile (model underpredicts by this much)
    error_p90: float  # 90th percentile (model overpredicts by this much)


def calibrate_prediction_errors(
    conn: DuckDBPyConnection,
) -> tuple[MLKellyCalibration, dict, dict, object, object]:
    """Compute prediction error distribution using LOO cross-validation.

    Returns (calibration, theme_stats, subtheme_stats, tier1_model_blueprint, feature_data)
    for use in per-set Kelly computation.
    """
    from services.ml.growth_model import (
        _build_model,
        _engineer_intrinsic_features,
        _engineer_keepa_features,
        _load_keepa_timelines,
        _load_training_data,
        TIER1_FEATURES,
    )

    df_raw = _load_training_data(conn)
    y = df_raw["annual_growth_pct"].values.astype(float)

    df_feat, theme_stats, subtheme_stats = _engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y),
    )

    tier1_features = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X = df_feat[tier1_features].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    fill_vals = X.median()
    X = X.fillna(fill_vals)

    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    Xs = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

    # LOO predictions to get unbiased error estimates
    model = _build_model()
    y_pred_loo = cross_val_predict(model, Xs, y, cv=LeaveOneOut())

    residuals = y - y_pred_loo  # positive = model underpredicted

    calibration = MLKellyCalibration(
        residual_mean=float(np.mean(residuals)),
        residual_std=float(np.std(residuals)),
        residual_skew=float(pd.Series(residuals).skew()),
        n_samples=len(residuals),
        error_p10=float(np.percentile(residuals, 10)),
        error_p90=float(np.percentile(residuals, 90)),
    )

    logger.info(
        "Kelly calibration: mean_error=%.2f%%, std=%.2f%%, n=%d",
        calibration.residual_mean,
        calibration.residual_std,
        calibration.n_samples,
    )

    return calibration, theme_stats, subtheme_stats


def compute_per_set_kelly(
    predicted_growth: float,
    calibration: MLKellyCalibration,
    confidence_str: str,
    n_simulations: int = 10000,
) -> tuple[float, float, float, float, float]:
    """Compute Kelly fraction for a single set.

    Simulates the return distribution by adding calibrated noise
    to the ML prediction, then computes win_prob and payoff_ratio.

    Returns: (win_prob, expected_win, expected_loss, raw_kelly, half_kelly)
    """
    rng = np.random.default_rng(42)

    # Simulate possible actual returns
    noise = rng.normal(
        loc=calibration.residual_mean,
        scale=calibration.residual_std,
        size=n_simulations,
    )
    simulated_returns = predicted_growth + noise

    # Win/loss classification
    wins = simulated_returns[simulated_returns > PROFIT_THRESHOLD]
    losses = simulated_returns[simulated_returns <= PROFIT_THRESHOLD]

    win_prob = len(wins) / n_simulations
    expected_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    expected_loss = float(abs(np.mean(losses))) if len(losses) > 0 else 0.001

    # Classic Kelly: f* = (b*p - q) / b
    if expected_loss > 0 and expected_win > 0:
        b = expected_win / expected_loss  # odds ratio
        q = 1.0 - win_prob
        raw_kelly = (b * win_prob - q) / b
    elif expected_win > 0 and expected_loss == 0:
        raw_kelly = 1.0
    else:
        raw_kelly = 0.0

    raw_kelly = max(0.0, raw_kelly)

    # Confidence discount
    confidence_mult = {"high": 1.0, "moderate": 0.8, "low": 0.5}.get(confidence_str, 0.3)
    half_kelly = raw_kelly * KELLY_FRACTION * confidence_mult

    return (
        round(win_prob, 4),
        round(expected_win, 2),
        round(expected_loss, 2),
        round(raw_kelly, 4),
        round(half_kelly, 4),
    )


def compute_ml_kelly_sizing(
    conn: DuckDBPyConnection,
    budget_cents: int | None = None,
    *,
    only_retiring: bool = False,
    max_positions: int | None = None,
) -> list[MLKellyResult]:
    """Full ML Kelly pipeline: predict growth, calibrate errors, compute per-set sizing."""
    from services.ml.growth_model import predict_growth, train_growth_models

    # Train models
    tier1, tier2, theme_stats, subtheme_stats = train_growth_models(conn)

    # Get predictions
    predictions = predict_growth(
        conn, tier1, tier2, theme_stats, subtheme_stats,
        only_retiring=only_retiring,
    )

    if not predictions:
        return []

    # Calibrate error distribution
    calibration, _, _ = calibrate_prediction_errors(conn)

    results: list[MLKellyResult] = []

    for pred in predictions:
        # Skip sets predicted to barely grow
        if pred.predicted_growth_pct < MIN_PREDICTED_GROWTH:
            continue

        win_prob, exp_win, exp_loss, raw_kelly, half_kelly = compute_per_set_kelly(
            pred.predicted_growth_pct,
            calibration,
            pred.confidence,
        )

        # Apply position cap
        recommended = min(half_kelly, MAX_POSITION_PCT)

        results.append(MLKellyResult(
            set_number=pred.set_number,
            title=pred.title,
            theme=pred.theme,
            predicted_growth_pct=pred.predicted_growth_pct,
            win_probability=win_prob,
            expected_win_pct=exp_win,
            expected_loss_pct=exp_loss,
            raw_kelly=raw_kelly,
            half_kelly=half_kelly,
            recommended_pct=round(recommended, 4),
            confidence=pred.confidence,
            ml_tier=pred.tier,
        ))

    # Sort by recommended allocation (best bets first)
    results.sort(key=lambda r: r.recommended_pct, reverse=True)

    # Limit to top N positions if requested
    if max_positions is not None and len(results) > max_positions:
        results = results[:max_positions]

    # Normalize: if total allocation > 100%, scale down proportionally
    total = sum(r.recommended_pct for r in results)
    if total > 1.0 and results:
        scale = 1.0 / total
        results = [
            MLKellyResult(
                set_number=r.set_number,
                title=r.title,
                theme=r.theme,
                predicted_growth_pct=r.predicted_growth_pct,
                win_probability=r.win_probability,
                expected_win_pct=r.expected_win_pct,
                expected_loss_pct=r.expected_loss_pct,
                raw_kelly=r.raw_kelly,
                half_kelly=r.half_kelly,
                recommended_pct=round(r.recommended_pct * scale, 4),
                confidence=r.confidence,
                ml_tier=r.ml_tier,
            )
            for r in results
        ]

    return results
