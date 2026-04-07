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
    prob_calibrator: Any | None = None  # isotonic calibration for P(avoid)


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
    }


def tune_classifier(
    X: np.ndarray,
    y_binary: np.ndarray,
    *,
    n_trials: int = 50,
    n_splits: int = 5,
    n_repeats: int = 3,
) -> dict:
    """Tune classifier hyperparameters with Optuna. Returns best params."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    best_params: dict = {}
    best_auc: float = -1.0

    rskf = RepeatedStratifiedKFold(
        n_splits=n_splits, n_repeats=n_repeats, random_state=42,
    )

    def objective(trial: optuna.Trial) -> float:
        nonlocal best_params, best_auc
        params = _get_classifier_search_space(trial)
        aucs: list[float] = []

        for train_idx, val_idx in rskf.split(X, y_binary):
            scaler = StandardScaler()
            X_tr = scaler.fit_transform(X[train_idx])
            X_va = scaler.transform(X[val_idx])

            clf = _build_classifier(params)
            clf.fit(X_tr, y_binary[train_idx])
            y_prob = clf.predict_proba(X_va)[:, 1]

            try:
                aucs.append(float(roc_auc_score(y_binary[val_idx], y_prob)))
            except ValueError:
                pass

        mean_auc = float(np.mean(aucs)) if aucs else 0.0
        if mean_auc > best_auc:
            best_auc = mean_auc
            best_params = params
        return mean_auc

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    logger.info(
        "Classifier Optuna: best AUC=%.4f after %d trials, params=%s",
        best_auc, n_trials, best_params,
    )
    return best_params


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
    tuning_trials: int = 50,
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

    # Optuna hyperparameter tuning
    best_params: dict = {}
    if tuning_trials > 0:
        best_params = tune_classifier(X, y_binary, n_trials=tuning_trials)

    # CV evaluation with tuned params
    cv = _cross_validate(X, y_binary, params=best_params)
    logger.info(
        "Classifier CV: AUC=%.3f+/-%.3f, F1=%.3f, Recall=%.3f",
        cv.auc_mean, cv.auc_std, cv.f1_mean, cv.recall_mean,
    )

    # Isotonic calibration on CV probabilities (fixes overconfidence at low probs)
    prob_calibrator = _fit_probability_calibrator(X, y_binary, params=best_params)

    # Fit final on all data
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    clf = _build_classifier(best_params)
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
        prob_calibrator=prob_calibrator,
    )


def predict_avoid_proba(
    X: np.ndarray,
    classifier: TrainedClassifier,
) -> np.ndarray:
    """P(avoid) for each row. Shape (n,).

    Applies isotonic calibration if available (fixes overconfidence at low
    probabilities, e.g. raw P=0.15 calibrated to actual 0.06).
    """
    X_s = classifier.scaler.transform(X)
    raw_probs = classifier.model.predict_proba(X_s)[:, 1]
    if classifier.prob_calibrator is not None:
        return np.clip(classifier.prob_calibrator.predict(raw_probs), 0.0, 1.0)
    return raw_probs


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


def _fit_probability_calibrator(
    X: np.ndarray,
    y_binary: np.ndarray,
    n_splits: int = 5,
    params: dict | None = None,
) -> Any | None:
    """Fit isotonic calibration on CV probabilities.

    Exp 23 showed P(avoid) is overconfident at low probs: raw P=0.15
    corresponds to actual 6% avoid rate (gap=-9%). Isotonic regression
    maps raw probs to empirically correct probabilities.
    """
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import StratifiedKFold

    if len(y_binary) < 50:
        return None

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    oof_probs = np.zeros(len(y_binary))

    for train_idx, val_idx in skf.split(X, y_binary):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X[train_idx])
        X_va = scaler.transform(X[val_idx])

        clf = _build_classifier(params)
        clf.fit(X_tr, y_binary[train_idx])
        oof_probs[val_idx] = clf.predict_proba(X_va)[:, 1]

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

        clf = _build_classifier(params)
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
