"""SHAP-based per-prediction explanations for growth models.

Uses TreeExplainer for exact SHAP values on GBM/LightGBM models.
Falls back gracefully when shap is not installed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_SHAP_AVAILABLE: bool | None = None


def _check_shap() -> bool:
    """Check if shap is importable (cached)."""
    global _SHAP_AVAILABLE
    if _SHAP_AVAILABLE is None:
        try:
            import shap  # noqa: F401
            _SHAP_AVAILABLE = True
        except ImportError:
            _SHAP_AVAILABLE = False
            logger.info("shap not installed, SHAP explanations disabled")
    return _SHAP_AVAILABLE


@dataclass(frozen=True)
class SHAPExplanation:
    """Per-prediction SHAP decomposition."""

    base_value: float  # E[f(X)] -- expected model output
    contributions: tuple[tuple[str, float], ...]  # (feature_name, shap_value)
    top_positive: tuple[tuple[str, float], ...]  # top drivers pushing UP
    top_negative: tuple[tuple[str, float], ...]  # top drivers pushing DOWN


def explain_predictions(
    model: Any,
    X: np.ndarray,
    feature_names: tuple[str, ...],
    *,
    top_k: int = 5,
) -> list[SHAPExplanation] | None:
    """Compute SHAP explanations for a batch of predictions.

    Returns None if shap is not installed.
    """
    if not _check_shap():
        return None

    import shap

    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
    except Exception:
        logger.warning("SHAP computation failed", exc_info=True)
        return None

    base_value = float(explainer.expected_value)
    if isinstance(base_value, np.ndarray):
        base_value = float(base_value[0])

    explanations: list[SHAPExplanation] = []
    for i in range(len(X)):
        row_vals = shap_values[i]
        contribs = tuple(
            (feature_names[j], round(float(row_vals[j]), 3))
            for j in range(len(feature_names))
        )

        # Sort by absolute value for top features
        sorted_contribs = sorted(contribs, key=lambda x: abs(x[1]), reverse=True)
        top_pos = tuple(
            (name, val) for name, val in sorted_contribs if val > 0
        )[:top_k]
        top_neg = tuple(
            (name, val) for name, val in sorted_contribs if val < 0
        )[:top_k]

        explanations.append(SHAPExplanation(
            base_value=round(base_value, 2),
            contributions=contribs,
            top_positive=top_pos,
            top_negative=top_neg,
        ))

    return explanations
