"""Evaluation metrics for the ML pipeline.

Computes regression and classification metrics including
domain-specific measures like quintile spread and Sharpe-like ratios.

Returns task-specific metric types (RegressionMetrics, ClassificationMetrics,
InversionMetrics) that have clear field semantics, with backward-compatible
conversion to the legacy ModelMetrics via .to_model_metrics().
"""

import logging

import numpy as np

from services.ml.types import (
    ClassificationMetrics,
    InversionMetrics,
    ModelMetrics,
    RegressionMetrics,
)

logger = logging.getLogger(__name__)


def evaluate_regression(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str,
    horizon_months: int,
) -> ModelMetrics:
    """Compute regression metrics: R-squared, quintile spread, hit rate, Sharpe-like.

    Returns ModelMetrics for backward compatibility. Use evaluate_regression_v2()
    for the typed RegressionMetrics.
    """
    metrics = evaluate_regression_typed(y_true, y_pred, model_name, horizon_months)
    return metrics.to_model_metrics()


def evaluate_regression_typed(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str,
    horizon_months: int,
) -> RegressionMetrics:
    """Compute regression metrics with proper typing."""
    from sklearn.metrics import r2_score

    r2 = float(r2_score(y_true, y_pred))
    hit_rate = _compute_hit_rate(y_true, y_pred)
    q_spread = _compute_quintile_spread(y_true, y_pred)
    sharpe = _compute_sharpe_like(y_true, y_pred)

    return RegressionMetrics(
        model_name=model_name,
        horizon_months=horizon_months,
        r_squared=r2,
        hit_rate=hit_rate,
        quintile_spread=q_spread,
        sharpe_like=sharpe,
    )


def evaluate_classification(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    model_name: str,
    horizon_months: int,
) -> ModelMetrics:
    """Compute classification metrics: ROC-AUC, hit rate.

    Returns ModelMetrics for backward compatibility. Use evaluate_classification_v2()
    for the typed ClassificationMetrics.
    """
    metrics = evaluate_classification_typed(y_true, y_prob, model_name, horizon_months)
    return metrics.to_model_metrics()


def evaluate_classification_typed(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    model_name: str,
    horizon_months: int,
) -> ClassificationMetrics:
    """Compute classification metrics with proper typing."""
    from sklearn.metrics import roc_auc_score

    try:
        auc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        auc = None

    hit_rate = _compute_hit_rate(y_true.astype(float), y_prob)
    q_spread = _compute_quintile_spread(y_true.astype(float), y_prob)

    return ClassificationMetrics(
        model_name=model_name,
        horizon_months=horizon_months,
        roc_auc=auc,
        hit_rate=hit_rate,
        quintile_spread=q_spread,
    )


def evaluate_inversion(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    y_returns: np.ndarray,
    model_name: str,
    horizon_months: int,
    avoid_threshold: float = 0.05,  # noqa: ARG001
) -> ModelMetrics:
    """Compute inversion-specific metrics.

    Returns ModelMetrics for backward compatibility. Use evaluate_inversion_typed()
    for the typed InversionMetrics with clear field semantics.
    """
    metrics = evaluate_inversion_typed(
        y_true, y_prob, y_returns, model_name, horizon_months
    )
    return metrics.to_model_metrics()


def evaluate_inversion_typed(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    y_returns: np.ndarray,
    model_name: str,
    horizon_months: int,
) -> InversionMetrics:
    """Compute inversion-specific metrics with proper typing.

    Metrics:
    - precision_avoid: When we say "avoid", how often is the set actually bad?
    - recall_avoid: Of actual losers, how many did we catch?
    - avoided_loss_pct: Average actual return of correctly flagged sets
    - bottom_quintile_accuracy: Of predicted bottom quintile, what % actually underperformed?
    - false_alarm_rate: Sets we said "avoid" that actually performed well
    - net_precision: precision_avoid - false_alarm_rate
    """
    from sklearn.metrics import precision_score, recall_score, roc_auc_score

    y_pred = (y_prob >= 0.5).astype(int)

    try:
        auc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        auc = None

    precision_avoid = float(precision_score(y_true, y_pred, zero_division=0))
    recall_avoid = float(recall_score(y_true, y_pred, zero_division=0))

    tp_mask = (y_pred == 1) & (y_true == 1)
    avoided_loss_pct = float(np.mean(y_returns[tp_mask])) if tp_mask.any() else 0.0

    n = len(y_true)
    q_size = max(1, n // 5)
    bottom_order = np.argsort(y_prob)[::-1][:q_size]
    bottom_q_accuracy = float(np.mean(y_true[bottom_order])) if q_size > 0 else 0.0

    fp_mask = (y_pred == 1) & (y_true == 0)
    total_predicted_avoid = int(y_pred.sum())
    false_alarm_rate = (
        float(fp_mask.sum()) / total_predicted_avoid
        if total_predicted_avoid > 0
        else 0.0
    )

    return InversionMetrics(
        model_name=model_name,
        horizon_months=horizon_months,
        roc_auc=auc,
        precision_avoid=precision_avoid,
        recall_avoid=recall_avoid,
        avoided_loss_pct=avoided_loss_pct,
        bottom_quintile_accuracy=bottom_q_accuracy,
        false_alarm_rate=false_alarm_rate,
        net_precision=precision_avoid - false_alarm_rate,
        n_train=0,
        n_test=n,
    )


# ---------------------------------------------------------------------------
# Shared pure metric computation functions
# ---------------------------------------------------------------------------


def _compute_hit_rate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    """Fraction of top quintile (by prediction) that has positive actual return."""
    n = len(y_true)
    if n < 5:
        return 0.0

    order = np.argsort(y_pred)[::-1]
    q_size = max(1, n // 5)
    top_actual = y_true[order[:q_size]]
    return float(np.nanmean(top_actual > 0))


def _compute_quintile_spread(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    """Median actual return of top quintile minus bottom quintile."""
    n = len(y_true)
    if n < 5:
        return 0.0

    order = np.argsort(y_pred)[::-1]
    q_size = max(1, n // 5)
    top_actual = y_true[order[:q_size]]
    bottom_actual = y_true[order[-q_size:]]
    return float(np.nanmedian(top_actual) - np.nanmedian(bottom_actual))


def _compute_sharpe_like(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    """Sharpe-like ratio: mean / std of actual returns in top quintile."""
    n = len(y_true)
    if n < 5:
        return 0.0

    order = np.argsort(y_pred)[::-1]
    q_size = max(1, n // 5)
    top_actual = y_true[order[:q_size]]

    mean = float(np.nanmean(top_actual))
    std = float(np.nanstd(top_actual))
    if std <= 0:
        return mean if mean > 0 else 0.0
    return mean / std


def format_metrics_table(metrics_list: list[ModelMetrics]) -> str:
    """Format metrics as an aligned text table for logging."""
    if not metrics_list:
        return "No models to display."

    header = (
        f"{'Model':<25} {'Task':<15} {'R2':>8} {'AUC':>8} "
        f"{'Hit%':>8} {'QSpread':>10} {'Sharpe':>8} "
        f"{'Train':>6} {'Test':>6}"
    )
    sep = "-" * len(header)
    lines = [header, sep]

    for m in metrics_list:
        auc_str = f"{m.roc_auc:.4f}" if m.roc_auc is not None else "N/A"
        lines.append(
            f"{m.model_name:<25} {m.task:<15} {m.r_squared:>8.4f} {auc_str:>8} "
            f"{m.hit_rate:>7.1%} {m.quintile_spread:>10.4f} {m.sharpe_like:>8.3f} "
            f"{m.n_train:>6} {m.n_test:>6}"
        )

    return "\n".join(lines)
