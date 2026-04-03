"""Model selection, hyperparameter tuning, and cross-validation harness.

Provides a model-agnostic CV pipeline with Optuna-based Bayesian tuning.
Supports GradientBoostingRegressor and LightGBM as candidates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import RepeatedKFold
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CVResult:
    """Cross-validation evaluation result with per-fold metrics."""

    r2_mean: float
    r2_std: float
    r2_folds: tuple[float, ...]
    mae_mean: float
    mae_std: float
    mae_folds: tuple[float, ...]
    rmse_mean: float
    rmse_std: float
    n_folds: int
    model_name: str = ""
    best_params: dict = field(default_factory=dict)

    @property
    def r2_ci_95(self) -> tuple[float, float]:
        """95% confidence interval for R2."""
        margin = 1.96 * self.r2_std / max(1, self.n_folds**0.5)
        return (self.r2_mean - margin, self.r2_mean + margin)

    def summary(self) -> str:
        lo, hi = self.r2_ci_95
        return (
            f"{self.model_name or 'model'}: "
            f"R2={self.r2_mean:+.3f} +/-{self.r2_std:.3f} "
            f"[{lo:+.3f}, {hi:+.3f}] "
            f"MAE={self.mae_mean:.1f}% "
            f"({self.n_folds} folds)"
        )


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------


def build_model(name: str, params: dict | None = None) -> Any:
    """Create a model instance by name.

    Supports 'gbm' (sklearn GradientBoosting) and 'lightgbm'.
    Falls back to GBM if LightGBM is not available.
    """
    params = params or {}

    if name == "lightgbm":
        try:
            import lightgbm as lgb
        except ImportError:
            logger.warning("LightGBM not installed, falling back to GBM")
            return _build_gbm(params)
        defaults = {"verbosity": -1, "random_state": 42, "n_jobs": 1}
        return lgb.LGBMRegressor(**{**defaults, **params})

    return _build_gbm(params)


def _build_gbm(params: dict) -> GradientBoostingRegressor:
    defaults = {
        "n_estimators": 300,
        "max_depth": 4,
        "min_samples_leaf": 5,
        "learning_rate": 0.02,
        "random_state": 42,
    }
    return GradientBoostingRegressor(**{**defaults, **params})


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------


def cross_validate_model(
    X: np.ndarray,
    y: np.ndarray,
    model_factory: Callable[[], Any],
    *,
    n_splits: int = 5,
    n_repeats: int = 3,
    random_state: int = 42,
) -> CVResult:
    """Run RepeatedKFold CV with per-fold scaling (no leakage).

    The scaler is fit on the training fold only, then applied to the
    validation fold. This prevents information leaking from val -> train.
    """
    rkf = RepeatedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=random_state)

    r2_scores: list[float] = []
    mae_scores: list[float] = []
    rmse_scores: list[float] = []

    for train_idx, val_idx in rkf.split(X):
        X_tr, X_va = X[train_idx], X[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_va_s = scaler.transform(X_va)

        model = model_factory()
        model.fit(X_tr_s, y_tr)
        y_pred = model.predict(X_va_s)

        ss_res = np.sum((y_va - y_pred) ** 2)
        ss_tot = np.sum((y_va - y_va.mean()) ** 2)
        r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

        r2_scores.append(r2)
        mae_scores.append(float(mean_absolute_error(y_va, y_pred)))
        rmse_scores.append(float(np.sqrt(mean_squared_error(y_va, y_pred))))

    return CVResult(
        r2_mean=float(np.mean(r2_scores)),
        r2_std=float(np.std(r2_scores)),
        r2_folds=tuple(r2_scores),
        mae_mean=float(np.mean(mae_scores)),
        mae_std=float(np.std(mae_scores)),
        mae_folds=tuple(mae_scores),
        rmse_mean=float(np.mean(rmse_scores)),
        rmse_std=float(np.std(rmse_scores)),
        n_folds=len(r2_scores),
    )


# ---------------------------------------------------------------------------
# Feature preprocessing
# ---------------------------------------------------------------------------


def clip_outliers(
    X: pd.DataFrame,
    *,
    lower_pct: float = 0.01,
    upper_pct: float = 0.99,
) -> pd.DataFrame:
    """Clip each feature column to its percentile bounds."""
    result = X.copy()
    for col in result.columns:
        series = pd.to_numeric(result[col], errors="coerce").astype(float)
        lo = series.quantile(lower_pct)
        hi = series.quantile(upper_pct)
        if pd.notna(lo) and pd.notna(hi) and lo < hi:
            result[col] = series.clip(lo, hi)
        else:
            result[col] = series
    return result


# ---------------------------------------------------------------------------
# Hyperparameter tuning
# ---------------------------------------------------------------------------


def _get_search_space(name: str, trial: Any) -> dict:
    """Return Optuna-sampled hyperparameters for a model."""
    if name == "lightgbm":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "num_leaves": trial.suggest_int("num_leaves", 15, 63),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 30),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 1.0, log=True),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
            "subsample": trial.suggest_float("subsample", 0.7, 1.0),
        }

    # GBM
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500),
        "max_depth": trial.suggest_int("max_depth", 3, 6),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 3, 15),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "subsample": trial.suggest_float("subsample", 0.7, 1.0),
    }


def tune_model(
    X: np.ndarray,
    y: np.ndarray,
    model_name: str,
    *,
    n_trials: int = 50,
    n_splits: int = 5,
    n_repeats: int = 3,
) -> tuple[dict, CVResult]:
    """Tune hyperparameters using Optuna Bayesian optimization.

    Returns (best_params, cv_result_for_best_params).
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    best_params: dict = {}
    best_cv: CVResult | None = None

    def objective(trial: optuna.Trial) -> float:
        nonlocal best_params, best_cv
        params = _get_search_space(model_name, trial)
        cv = cross_validate_model(
            X, y,
            lambda p=params: build_model(model_name, p),
            n_splits=n_splits,
            n_repeats=n_repeats,
        )
        if best_cv is None or cv.r2_mean > best_cv.r2_mean:
            best_params = params
            best_cv = cv
        return cv.r2_mean

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    # Re-evaluate best params for clean CVResult
    final_cv = cross_validate_model(
        X, y,
        lambda: build_model(model_name, best_params),
        n_splits=n_splits,
        n_repeats=n_repeats,
    )

    return best_params, CVResult(
        r2_mean=final_cv.r2_mean,
        r2_std=final_cv.r2_std,
        r2_folds=final_cv.r2_folds,
        mae_mean=final_cv.mae_mean,
        mae_std=final_cv.mae_std,
        mae_folds=final_cv.mae_folds,
        rmse_mean=final_cv.rmse_mean,
        rmse_std=final_cv.rmse_std,
        n_folds=final_cv.n_folds,
        model_name=model_name,
        best_params=best_params,
    )


def select_best_model(
    X: np.ndarray,
    y: np.ndarray,
    candidates: tuple[str, ...] = ("lightgbm", "gbm"),
    *,
    n_trials: int = 50,
    n_splits: int = 5,
    n_repeats: int = 3,
    min_improvement: float = 0.01,
) -> tuple[str, dict, CVResult]:
    """Tune each candidate model and return the best.

    Prefers simpler models (GBM) when complex models (LightGBM)
    don't improve by at least `min_improvement` R2.
    """
    results: list[tuple[str, dict, CVResult]] = []

    for name in candidates:
        logger.info("Tuning %s (%d trials)...", name, n_trials)
        try:
            params, cv = tune_model(
                X, y, name,
                n_trials=n_trials,
                n_splits=n_splits,
                n_repeats=n_repeats,
            )
            logger.info("  %s: %s", name, cv.summary())
            results.append((name, params, cv))
        except Exception:
            logger.exception("  %s tuning failed, skipping", name)

    if not results:
        # Fallback: default GBM
        logger.warning("All candidates failed, using default GBM")
        default_cv = cross_validate_model(
            X, y, lambda: build_model("gbm"),
            n_splits=n_splits, n_repeats=n_repeats,
        )
        return "gbm", {}, default_cv

    # Sort by R2 descending
    results.sort(key=lambda r: r[2].r2_mean, reverse=True)
    best_name, best_params, best_cv = results[0]

    # Prefer simpler model if complex model doesn't improve enough
    if best_name != "gbm" and len(results) > 1:
        gbm_result = next((r for r in results if r[0] == "gbm"), None)
        if gbm_result and best_cv.r2_mean - gbm_result[2].r2_mean < min_improvement:
            logger.info(
                "LightGBM R2=%.3f vs GBM R2=%.3f (delta=%.3f < %.3f), preferring GBM",
                best_cv.r2_mean, gbm_result[2].r2_mean,
                best_cv.r2_mean - gbm_result[2].r2_mean,
                min_improvement,
            )
            return gbm_result

    return best_name, best_params, best_cv
