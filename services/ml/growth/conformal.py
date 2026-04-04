"""Split conformal prediction for growth model intervals.

Provides distribution-free prediction intervals with finite-sample
coverage guarantees. Uses the most recent temporal cohort as the
calibration set, and nonconformity scores (absolute residuals) to
compute per-prediction intervals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from services.ml.growth.types import PredictionInterval

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConformalCalibration:
    """Calibration result from split conformal prediction."""

    nonconformity_scores: tuple[float, ...]
    calibration_year: int | None
    n_calibration: int

    @property
    def median_score(self) -> float:
        return float(np.median(self.nonconformity_scores))


def calibrate_conformal(
    y_cal: np.ndarray,
    y_pred_cal: np.ndarray,
    *,
    calibration_year: int | None = None,
) -> ConformalCalibration:
    """Compute nonconformity scores from a calibration set.

    The calibration set should be a held-out temporal cohort (e.g., the
    most recent retirement year) that was NOT used during training.

    Args:
        y_cal: True target values for the calibration set.
        y_pred_cal: Model predictions on the calibration set.
        calibration_year: Optional label for which year was used.

    Returns:
        ConformalCalibration with sorted nonconformity scores.
    """
    scores = np.abs(y_cal - y_pred_cal)
    sorted_scores = tuple(sorted(float(s) for s in scores))

    logger.info(
        "Conformal calibration: %d samples, median |residual|=%.2f%%, "
        "90th=%.2f%%, max=%.2f%%",
        len(scores), np.median(scores),
        np.percentile(scores, 90), np.max(scores),
    )

    return ConformalCalibration(
        nonconformity_scores=sorted_scores,
        calibration_year=calibration_year,
        n_calibration=len(scores),
    )


def predict_with_interval(
    y_pred: float,
    calibration: ConformalCalibration,
    *,
    alpha: float = 0.10,
) -> PredictionInterval:
    """Compute a conformal prediction interval at (1-alpha) coverage.

    Uses the quantile of nonconformity scores adjusted for finite-sample
    coverage: q = ceil((1-alpha)(1 + 1/n)) quantile of scores.

    Args:
        y_pred: Point prediction.
        calibration: ConformalCalibration from calibrate_conformal().
        alpha: Miscoverage rate (0.10 = 90% coverage).

    Returns:
        PredictionInterval with point, lower, upper, alpha.
    """
    n = calibration.n_calibration
    scores = np.array(calibration.nonconformity_scores)

    # Finite-sample corrected quantile level
    q_level = min((1 - alpha) * (1 + 1 / n), 1.0)
    q_hat = float(np.quantile(scores, q_level))

    return PredictionInterval(
        point=y_pred,
        lower=round(y_pred - q_hat, 1),
        upper=round(y_pred + q_hat, 1),
        alpha=alpha,
    )


def batch_predict_with_intervals(
    y_preds: np.ndarray,
    calibration: ConformalCalibration,
    *,
    alpha: float = 0.10,
) -> list[PredictionInterval]:
    """Compute conformal intervals for a batch of predictions."""
    return [
        predict_with_interval(float(p), calibration, alpha=alpha)
        for p in y_preds
    ]
