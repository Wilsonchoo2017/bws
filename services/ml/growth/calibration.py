"""Isotonic calibration for growth model predictions.

Fixes systematic bias where the model over/under-predicts at extremes.
Trained on LOO residuals, applied as a post-processing step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sklearn.isotonic import IsotonicRegression

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IsotonicCalibrator:
    """Fitted isotonic calibration model."""

    model: IsotonicRegression
    n_calibration: int
    pre_mae: float
    post_mae: float
    improvement_pct: float


def fit_isotonic_calibrator(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> IsotonicCalibrator | None:
    """Fit isotonic regression to map raw predictions -> calibrated predictions.

    Uses isotonic regression (monotone, non-parametric) to correct systematic
    bias. If calibration doesn't improve MAE, returns None.

    Args:
        y_true: Actual growth percentages (from LOO or CV).
        y_pred: Raw model predictions (same ordering as y_true).

    Returns:
        Fitted calibrator, or None if calibration doesn't help.
    """
    if len(y_true) < 30:
        logger.info("Isotonic calibration skipped: only %d samples (need 30+)", len(y_true))
        return None

    pre_mae = float(np.mean(np.abs(y_true - y_pred)))

    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(y_pred, y_true)

    y_calibrated = iso.predict(y_pred)
    post_mae = float(np.mean(np.abs(y_true - y_calibrated)))

    improvement = (pre_mae - post_mae) / pre_mae * 100

    if improvement < 1.0:
        logger.info(
            "Isotonic calibration skipped: only %.1f%% improvement (%.3f -> %.3f MAE)",
            improvement, pre_mae, post_mae,
        )
        return None

    logger.info(
        "Isotonic calibration: MAE %.3f -> %.3f (%.1f%% improvement, n=%d)",
        pre_mae, post_mae, improvement, len(y_true),
    )

    return IsotonicCalibrator(
        model=iso,
        n_calibration=len(y_true),
        pre_mae=pre_mae,
        post_mae=post_mae,
        improvement_pct=improvement,
    )


def apply_calibration(
    predictions: np.ndarray,
    calibrator: IsotonicCalibrator | None,
) -> np.ndarray:
    """Apply isotonic calibration to raw predictions.

    If no calibrator is provided, returns predictions unchanged.
    """
    if calibrator is None:
        return predictions

    return calibrator.model.predict(predictions)
