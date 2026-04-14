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
import pandas as pd
from sklearn.metrics import f1_score, fbeta_score, precision_score, recall_score, roc_auc_score
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
    prob_calibrator: Any | None = None  # isotonic calibration for P(avoid)
    decision_threshold: float = 0.5  # auto-tuned for high recall


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
    merged = {**defaults, **(params or {})}
    # scale_pos_weight and is_unbalance are mutually exclusive in LightGBM
    if "scale_pos_weight" in merged:
        merged.pop("is_unbalance", None)
    return lgb.LGBMClassifier(**merged)


# ---------------------------------------------------------------------------
# Hyperparameter tuning (Optuna)
# ---------------------------------------------------------------------------


def _get_classifier_search_space(trial: Any) -> dict:
    """Optuna-sampled LightGBM classifier hyperparameters."""
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 400),
        "max_depth": trial.suggest_int("max_depth", 3, 6),
        "num_leaves": trial.suggest_int("num_leaves", 7, 31),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 30),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 1.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 1.0, log=True),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
        "subsample": trial.suggest_float("subsample", 0.7, 1.0),
        "scale_pos_weight": trial.suggest_float("scale_pos_weight", 1.5, 5.0),
    }


def tune_classifier(
    X: np.ndarray,
    y_binary: np.ndarray,
    *,
    n_trials: int = 50,
    n_splits: int = 5,
    n_repeats: int = 3,
    decision_threshold: float = 0.30,
    sample_weight: np.ndarray | None = None,
) -> dict:
    """Tune classifier hyperparameters with Optuna.

    Optimizes F-beta (beta=2) which weights recall 4x more than precision,
    aggressively penalizing false negatives (missed losers).
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    best_params: dict = {}
    best_score: float = -1.0

    rskf = RepeatedStratifiedKFold(
        n_splits=n_splits, n_repeats=n_repeats, random_state=42,
    )

    def objective(trial: optuna.Trial) -> float:
        nonlocal best_params, best_score
        params = _get_classifier_search_space(trial)
        f2_scores: list[float] = []

        for train_idx, val_idx in rskf.split(X, y_binary):
            scaler = StandardScaler()
            X_tr = scaler.fit_transform(X[train_idx])
            X_va = scaler.transform(X[val_idx])

            w_tr = sample_weight[train_idx] if sample_weight is not None else None
            clf = _build_classifier(params)
            clf.fit(X_tr, y_binary[train_idx], sample_weight=w_tr)
            y_prob = clf.predict_proba(X_va)[:, 1]
            y_pred = (y_prob >= decision_threshold).astype(int)

            f2_scores.append(float(fbeta_score(
                y_binary[val_idx], y_pred, beta=2, zero_division=0,
            )))

        mean_score = float(np.mean(f2_scores)) if f2_scores else 0.0
        if mean_score > best_score:
            best_score = mean_score
            best_params = params
        return mean_score

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    logger.info(
        "Classifier Optuna: best F2=%.4f after %d trials (threshold=%.2f), params=%s",
        best_score, n_trials, decision_threshold, best_params,
    )
    return best_params


def _find_recall_threshold(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    min_precision: float = 0.40,
) -> float:
    """Find threshold that maximizes F2 score (recall-weighted) with minimum precision.

    F-beta with beta=2 weights recall 4x more than precision, naturally
    biasing toward catching losers. Sweeps thresholds from 0.15 to 0.55.
    Falls back to 0.35 if no threshold satisfies the precision floor.
    """
    best_threshold = 0.35
    best_f2 = 0.0

    for t_int in range(15, 56):  # 0.15 to 0.55
        t = t_int / 100.0
        preds = (y_prob >= t).astype(int)
        if preds.sum() == 0:
            continue
        prec = precision_score(y_true, preds, zero_division=0)
        if prec < min_precision:
            continue
        f2 = fbeta_score(y_true, preds, beta=2, zero_division=0)
        if f2 > best_f2:
            best_f2 = f2
            best_threshold = t

    return best_threshold


def compute_avoid_sample_weights(
    y_growth: np.ndarray,
    strong_loser: float = -15.0,
    loser: float = -5.0,
) -> np.ndarray:
    """Asymmetric weights: severe losers weighted more than stagnant sets.

    Within the avoid class (growth < 5%), worse outcomes get higher weight
    so the model prioritizes not missing truly bad investments.

    Tiers (matching InversionConfig):
      strong_loser (< -15%): weight 3.0
      loser (-15% to -5%):   weight 2.0
      stagnant (-5% to 5%):  weight 1.0
      keeper (>= 5%):        weight 1.0
    """
    weights = np.ones(len(y_growth))
    weights[y_growth < loser] = 2.0
    weights[y_growth < strong_loser] = 3.0
    return weights


def make_avoid_labels(
    y_growth: np.ndarray,
    threshold: float = AVOID_THRESHOLD_PCT,
    *,
    invert: bool = False,
) -> np.ndarray:
    """Label sets for binary classification.

    Default: 1 = avoid (loser below threshold), 0 = keep.
    Inverted: 1 = winner (at or above threshold), 0 = rest.
    """
    if invert:
        return (y_growth >= threshold).astype(int)
    return (y_growth < threshold).astype(int)


def train_classifier(
    X: np.ndarray,
    y_growth: np.ndarray,
    feature_names: list[str],
    fill_values: tuple[tuple[str, float], ...],
    *,
    threshold: float = AVOID_THRESHOLD_PCT,
    tuning_trials: int = 50,
    invert: bool = False,
    sample_weight: np.ndarray | None = None,
) -> TrainedClassifier | None:
    """Train a binary classifier.

    Default: predicts P(avoid) where avoid = growth < threshold.
    Inverted: predicts P(winner) where winner = growth >= threshold.

    Args:
        sample_weight: Per-sample weights for asymmetric loss. Use
            compute_avoid_sample_weights() to weight severe losers
            more heavily than stagnant sets.
    """
    from datetime import datetime

    y_binary = make_avoid_labels(y_growth, threshold, invert=invert)
    n_avoid = int(y_binary.sum())

    label = "winner" if invert else "avoid"

    if n_avoid < 15:
        logger.info("Classifier skipped: only %d %s samples", n_avoid, label)
        return None

    median_loser = float(np.median(y_growth[y_binary == 1]))

    logger.info(
        "Training %s classifier: %d positive / %d negative (%.1f%%, median=%.1f%%)",
        label, n_avoid, len(y_binary) - n_avoid,
        n_avoid / len(y_binary) * 100, median_loser,
    )

    if sample_weight is not None:
        logger.info(
            "Asymmetric sample weights: min=%.1f, max=%.1f, mean=%.2f",
            sample_weight.min(), sample_weight.max(), sample_weight.mean(),
        )

    # Optuna hyperparameter tuning
    best_params: dict = {}
    if tuning_trials > 0:
        best_params = tune_classifier(
            X, y_binary, n_trials=tuning_trials, sample_weight=sample_weight,
        )

    # CV evaluation with tuned params (metrics at default threshold, final threshold tuned later)
    cv = _cross_validate(X, y_binary, params=best_params, sample_weight=sample_weight)
    logger.info(
        "Classifier CV (threshold=0.30): AUC=%.3f+/-%.3f, F1=%.3f, Recall=%.3f",
        cv.auc_mean, cv.auc_std, cv.f1_mean, cv.recall_mean,
    )

    # Single OOF pass for both calibration and threshold tuning
    oof_probs = _get_oof_probabilities(
        X, y_binary, params=best_params, sample_weight=sample_weight,
    )

    # Isotonic calibration on OOF probabilities (fixes overconfidence at low probs)
    prob_calibrator = _fit_probability_calibrator(
        y_binary, oof_probs=oof_probs,
    )

    # Auto-tune decision threshold for high recall (minimize FN)
    calibrated_oof = oof_probs
    if prob_calibrator is not None:
        calibrated_oof = np.clip(prob_calibrator.predict(oof_probs), 0.0, 1.0)
    decision_threshold = _find_recall_threshold(y_binary, calibrated_oof)
    logger.info(
        "Decision threshold auto-tuned: %.2f (max F2 with precision>=40%%)",
        decision_threshold,
    )

    # Fit final on all data
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    clf = _build_classifier(best_params)
    clf.fit(X_s, y_binary, sample_weight=sample_weight)

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
        prob_calibrator=prob_calibrator,
        decision_threshold=decision_threshold,
    )


def predict_class_proba(
    X: np.ndarray | pd.DataFrame,
    classifier: TrainedClassifier,
) -> np.ndarray:
    """P(positive class) for each row. Shape (n,).

    For avoid classifiers: returns P(avoid).
    For winner classifiers (invert=True): returns P(winner).
    Applies isotonic calibration if available.
    """
    X_scaled = classifier.scaler.transform(X)
    if isinstance(X, pd.DataFrame):
        X_s = pd.DataFrame(X_scaled, columns=X.columns, index=X.index)
    else:
        X_s = X_scaled
    raw_probs = classifier.model.predict_proba(X_s)[:, 1]
    if classifier.prob_calibrator is not None:
        return np.clip(classifier.prob_calibrator.predict(raw_probs), 0.0, 1.0)
    return raw_probs


# Backward-compatible alias
predict_avoid_proba = predict_class_proba


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


def _get_oof_probabilities(
    X: np.ndarray,
    y_binary: np.ndarray,
    n_splits: int = 5,
    params: dict | None = None,
    sample_weight: np.ndarray | None = None,
) -> np.ndarray:
    """Get out-of-fold raw probabilities for threshold tuning."""
    from sklearn.model_selection import StratifiedKFold

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    oof_probs = np.zeros(len(y_binary))

    for train_idx, val_idx in skf.split(X, y_binary):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X[train_idx])
        X_va = scaler.transform(X[val_idx])

        w_tr = sample_weight[train_idx] if sample_weight is not None else None
        clf = _build_classifier(params)
        clf.fit(X_tr, y_binary[train_idx], sample_weight=w_tr)
        oof_probs[val_idx] = clf.predict_proba(X_va)[:, 1]

    return oof_probs


def _fit_probability_calibrator(
    y_binary: np.ndarray,
    oof_probs: np.ndarray,
) -> Any | None:
    """Fit isotonic calibration on precomputed OOF probabilities.

    Exp 23 showed P(avoid) is overconfident at low probs: raw P=0.15
    corresponds to actual 6% avoid rate (gap=-9%). Isotonic regression
    maps raw probs to empirically correct probabilities.
    """
    from sklearn.isotonic import IsotonicRegression

    if len(y_binary) < 50:
        return None

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(oof_probs, y_binary)

    # Check if calibration actually helps
    from sklearn.metrics import brier_score_loss

    raw_brier = brier_score_loss(y_binary, oof_probs)
    cal_brier = brier_score_loss(y_binary, np.clip(iso.predict(oof_probs), 0, 1))

    if cal_brier >= raw_brier:
        logger.info(
            "P(avoid) calibration skipped: no improvement (raw=%.4f, cal=%.4f)",
            raw_brier, cal_brier,
        )
        return None

    logger.info(
        "P(avoid) isotonic calibration: Brier %.4f -> %.4f (%.1f%% improvement)",
        raw_brier, cal_brier, (raw_brier - cal_brier) / raw_brier * 100,
    )
    return iso


def _cross_validate(
    X: np.ndarray,
    y_binary: np.ndarray,
    n_splits: int = 5,
    n_repeats: int = 3,
    params: dict | None = None,
    decision_threshold: float = 0.30,
    sample_weight: np.ndarray | None = None,
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

        w_tr = sample_weight[train_idx] if sample_weight is not None else None
        clf = _build_classifier(params)
        clf.fit(X_tr, y_tr, sample_weight=w_tr)
        y_prob = clf.predict_proba(X_va)[:, 1]
        y_pred = (y_prob >= decision_threshold).astype(int)

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
