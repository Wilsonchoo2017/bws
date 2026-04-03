"""Evaluation metrics for the ML pipeline.

Computes regression and classification metrics including
domain-specific measures like quintile spread and Sharpe-like ratios.
"""

import logging

import numpy as np

from services.ml.types import ModelMetrics

logger = logging.getLogger(__name__)


def evaluate_regression(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str,
    horizon_months: int,
) -> ModelMetrics:
    """Compute regression metrics: R-squared, quintile spread, hit rate, Sharpe-like."""
    from sklearn.metrics import r2_score

    r2 = float(r2_score(y_true, y_pred))
    hit_rate = _compute_hit_rate(y_true, y_pred)
    q_spread = _compute_quintile_spread(y_true, y_pred)
    sharpe = _compute_sharpe_like(y_true, y_pred)

    return ModelMetrics(
        model_name=model_name,
        horizon_months=horizon_months,
        task="regression",
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
    """Compute classification metrics: ROC-AUC, hit rate."""
    from sklearn.metrics import roc_auc_score

    try:
        auc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        auc = None

    # Use probability as score for quintile-based metrics
    # (treat as pseudo-regression for ranking purposes)
    hit_rate = _compute_hit_rate(y_true.astype(float), y_prob)
    q_spread = _compute_quintile_spread(y_true.astype(float), y_prob)

    return ModelMetrics(
        model_name=model_name,
        horizon_months=horizon_months,
        task="classification",
        r_squared=0.0,
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
    """Compute inversion-specific metrics focused on left-tail prediction.

    Metrics:
    - precision_avoid: When we say "avoid", how often is the set actually bad?
    - recall_avoid: Of actual losers (return < threshold), how many did we catch?
    - avoided_loss_pct: Average actual return of correctly flagged sets (negative = good)
    - bottom_quintile_accuracy: Of predicted bottom quintile, what % actually underperformed?
    - false_alarm_rate: Sets we said "avoid" that actually performed well

    Args:
        y_true: Binary ground truth (1=avoid, 0=keep).
        y_prob: Predicted probability of "avoid" class.
        y_returns: Continuous returns for dollar-impact calculations.
        model_name: Model identifier.
        horizon_months: Prediction horizon.
        avoid_threshold: Return threshold for avoid classification.
    """
    from sklearn.metrics import precision_score, recall_score, roc_auc_score

    y_pred = (y_prob >= 0.5).astype(int)

    try:
        auc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        auc = None

    # Precision/recall on the "avoid" class (label=1)
    precision_avoid = float(precision_score(y_true, y_pred, zero_division=0))
    recall_avoid = float(recall_score(y_true, y_pred, zero_division=0))

    # Avoided loss: average actual return of true positives (correctly flagged)
    tp_mask = (y_pred == 1) & (y_true == 1)
    avoided_loss_pct = float(np.mean(y_returns[tp_mask])) if tp_mask.any() else 0.0

    # Bottom quintile accuracy
    n = len(y_true)
    q_size = max(1, n // 5)
    bottom_order = np.argsort(y_prob)[::-1][:q_size]  # highest avoid probability
    bottom_q_accuracy = float(np.mean(y_true[bottom_order])) if q_size > 0 else 0.0

    # False alarm rate: predicted avoid but actually good
    fp_mask = (y_pred == 1) & (y_true == 0)
    total_predicted_avoid = int(y_pred.sum())
    false_alarm_rate = (
        float(fp_mask.sum()) / total_predicted_avoid
        if total_predicted_avoid > 0
        else 0.0
    )

    # Use hit_rate for bottom quintile accuracy, quintile_spread for precision-recall gap,
    # sharpe_like for avoided loss magnitude
    return ModelMetrics(
        model_name=model_name,
        horizon_months=horizon_months,
        task="inversion",
        r_squared=avoided_loss_pct,  # repurposed: avg return of correctly flagged
        roc_auc=auc,
        hit_rate=bottom_q_accuracy,
        quintile_spread=precision_avoid - false_alarm_rate,  # net precision
        sharpe_like=recall_avoid,
        n_train=0,
        n_test=n,
    )


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
    """Sharpe-like ratio: mean / std of actual returns in top quintile.

    Higher is better -- indicates the model's top picks have high
    average returns with low variance.
    """
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
