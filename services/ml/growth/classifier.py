"""Hurdle model gate -- classifier predicts which sets to AVOID.

Part 1 of a two-stage hurdle model:
  1. Classifier: P(set is a loser) -- trained on ALL data
  2. Regressor: E[growth | not loser] -- trained on non-losers only
  Combined: P(good) * regressor_pred + P(bad) * median_loser_return

"Tell me where I'm going to die, so I'll never go there." -- Munger
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import f1_score, recall_score, roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# Sets growing below this are "losers" to avoid.
AVOID_THRESHOLD_PCT = 5.0


@dataclass(frozen=True)
class ClassifierMetrics:
    """CV metrics for the avoid classifier."""

    auc_mean: float
    auc_std: float
    f1_mean: float
    recall_mean: float
    n_avoid: int
    n_total: int


@dataclass(frozen=True)
class TrainedClassifier:
    """Fitted avoid classifier."""

    model: Any
    scaler: StandardScaler
    feature_names: tuple[str, ...]
    fill_values: tuple[tuple[str, float], ...]
    avoid_threshold: float
    n_train: int
    n_avoid: int
    cv_auc: float
    cv_f1: float
    cv_recall: float
    median_loser_return: float  # avg return of avoid-class sets
    trained_at: str


def _build_classifier(params: dict | None = None) -> Any:
    """LightGBM classifier tuned for recall on minority (loser) class."""
    try:
        import lightgbm as lgb
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(
            max_iter=200, max_depth=4, learning_rate=0.05,
            class_weight="balanced", random_state=42,
        )

    defaults = {
        "verbosity": -1,
        "random_state": 42,
        "n_jobs": 1,
        "objective": "binary",
        "is_unbalance": True,
        "n_estimators": 200,
        "max_depth": 4,
        "num_leaves": 15,
        "learning_rate": 0.05,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "min_child_samples": 10,
    }
    return lgb.LGBMClassifier(**{**defaults, **(params or {})})


def make_avoid_labels(
    y_growth: np.ndarray,
    threshold: float = AVOID_THRESHOLD_PCT,
) -> np.ndarray:
    """1 = avoid (loser), 0 = keep (winner)."""
    return (y_growth < threshold).astype(int)


def train_classifier(
    X: np.ndarray,
    y_growth: np.ndarray,
    feature_names: list[str],
    fill_values: tuple[tuple[str, float], ...],
    *,
    threshold: float = AVOID_THRESHOLD_PCT,
) -> TrainedClassifier | None:
    """Train the avoid classifier. Returns None if too few avoid samples."""
    from datetime import datetime

    y_binary = make_avoid_labels(y_growth, threshold)
    n_avoid = int(y_binary.sum())

    if n_avoid < 15:
        logger.info("Classifier skipped: only %d avoid samples", n_avoid)
        return None

    median_loser = float(np.median(y_growth[y_binary == 1]))

    logger.info(
        "Training classifier: %d avoid / %d keep (%.1f%% avoid, median loser=%.1f%%)",
        n_avoid, len(y_binary) - n_avoid,
        n_avoid / len(y_binary) * 100, median_loser,
    )

    # CV evaluation
    cv = _cross_validate(X, y_binary)
    logger.info(
        "Classifier CV: AUC=%.3f+/-%.3f, F1=%.3f, Recall=%.3f",
        cv.auc_mean, cv.auc_std, cv.f1_mean, cv.recall_mean,
    )

    # Fit final on all data
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    clf = _build_classifier()
    clf.fit(X_s, y_binary)

    return TrainedClassifier(
        model=clf,
        scaler=scaler,
        feature_names=tuple(feature_names),
        fill_values=fill_values,
        avoid_threshold=threshold,
        n_train=len(y_binary),
        n_avoid=n_avoid,
        cv_auc=cv.auc_mean,
        cv_f1=cv.f1_mean,
        cv_recall=cv.recall_mean,
        median_loser_return=median_loser,
        trained_at=datetime.now().isoformat(),
    )


def predict_avoid_proba(
    X: np.ndarray,
    classifier: TrainedClassifier,
) -> np.ndarray:
    """P(avoid) for each row. Shape (n,)."""
    X_s = classifier.scaler.transform(X)
    return classifier.model.predict_proba(X_s)[:, 1]


def hurdle_combine(
    regressor_growth: np.ndarray,
    avoid_proba: np.ndarray,
    median_loser_return: float,
) -> np.ndarray:
    """Hurdle model combination.

    final = P(good) * regressor_pred + P(bad) * median_loser_return

    The regressor was trained on non-losers only, so its predictions
    represent E[growth | good]. We weight by classifier confidence.
    """
    p_good = 1.0 - avoid_proba
    return p_good * regressor_growth + avoid_proba * median_loser_return


def _cross_validate(
    X: np.ndarray,
    y_binary: np.ndarray,
    n_splits: int = 5,
    n_repeats: int = 3,
) -> ClassifierMetrics:
    rskf = RepeatedStratifiedKFold(
        n_splits=n_splits, n_repeats=n_repeats, random_state=42,
    )
    aucs: list[float] = []
    f1s: list[float] = []
    recs: list[float] = []

    for train_idx, val_idx in rskf.split(X, y_binary):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X[train_idx])
        X_va = scaler.transform(X[val_idx])
        y_tr, y_va = y_binary[train_idx], y_binary[val_idx]

        clf = _build_classifier()
        clf.fit(X_tr, y_tr)
        y_prob = clf.predict_proba(X_va)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)

        try:
            aucs.append(float(roc_auc_score(y_va, y_prob)))
        except ValueError:
            pass
        f1s.append(float(f1_score(y_va, y_pred, zero_division=0)))
        recs.append(float(recall_score(y_va, y_pred, zero_division=0)))

    return ClassifierMetrics(
        auc_mean=float(np.mean(aucs)) if aucs else 0.0,
        auc_std=float(np.std(aucs)) if aucs else 0.0,
        f1_mean=float(np.mean(f1s)),
        recall_mean=float(np.mean(recs)),
        n_avoid=int(y_binary.sum()),
        n_total=len(y_binary),
    )
