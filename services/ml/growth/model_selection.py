"""Model selection, hyperparameter tuning, and cross-validation.

LightGBM-only pipeline with Optuna Bayesian tuning. Supports monotonic
constraints and sample weighting for recency.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import RepeatedKFold
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CVResult:
    """Cross-validation result with per-fold metrics."""

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
# Monotonic constraints
# ---------------------------------------------------------------------------

# Features where we know the direction: +1 = higher value → higher growth,
# -1 = higher value → lower growth, 0 = no constraint.
MONOTONIC_MAP: dict[str, int] = {
    "mfigs": 1,  # more minifigs → better
    "rating_value": 1,  # higher rating → better
    "log_reviews": 1,  # more reviews → better (popularity)
    "is_licensed": 1,  # licensed IP → better
    "mfig_value_to_rrp": 1,  # higher minifig value ratio → better
    "review_rank_in_theme": 1,  # higher review rank → better
    "review_rank_in_retire_year": 1,  # higher review rank → better
}


def _get_monotonic_constraints(feature_names: list[str]) -> list[int]:
    """Build monotonic constraint vector for LightGBM."""
    return [MONOTONIC_MAP.get(f, 0) for f in feature_names]


# ---------------------------------------------------------------------------
# Sample weighting
# ---------------------------------------------------------------------------


def compute_recency_weights(
    year_retired: np.ndarray,
    half_life: float = 3.0,
) -> np.ndarray:
    """Exponential decay weights: newer retirement years weigh more.

    half_life=3 means a set retired 3 years ago has half the weight
    of the most recent cohort.
    """
    finite = np.isfinite(year_retired)
    if finite.sum() == 0:
        return np.ones(len(year_retired))

    max_year = float(np.nanmax(year_retired))
    age = max_year - np.where(finite, year_retired, max_year)
    decay = np.log(2) / half_life
    weights = np.exp(-decay * age)

    # Normalize so mean weight = 1 (doesn't change effective sample size)
    return weights / weights.mean()


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------


def build_model(params: dict | None = None) -> Any:
    """Create a LightGBM regressor."""
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ImportError("LightGBM is required: pip install lightgbm") from exc

    defaults = {
        "verbosity": -1,
        "random_state": 42,
        "n_jobs": 1,
        "objective": "huber",
        "alpha": 1.0,
    }
    return lgb.LGBMRegressor(**{**defaults, **(params or {})})


# ---------------------------------------------------------------------------
# Target preprocessing
# ---------------------------------------------------------------------------


def winsorize_targets(
    y: np.ndarray,
    lower_pct: float = 5.0,
    upper_pct: float = 95.0,
) -> np.ndarray:
    """Clip extreme target values to reduce outlier influence."""
    lo = np.percentile(y, lower_pct)
    hi = np.percentile(y, upper_pct)
    clipped = np.clip(y, lo, hi)
    n_clipped = int((y < lo).sum() + (y > hi).sum())
    if n_clipped > 0:
        logger.info(
            "Winsorized %d targets: [%.1f%%, %.1f%%] -> [%.1f%%, %.1f%%]",
            n_clipped, y.min(), y.max(), lo, hi,
        )
    return clipped


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
# Early stopping
# ---------------------------------------------------------------------------


def _fit_with_early_stopping(
    model: Any,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    sample_weight: np.ndarray | None = None,
) -> None:
    """Fit model with early stopping (LightGBM only)."""
    name = type(model).__name__

    # Only LightGBM supports early stopping with eval_set
    if name != "LGBMRegressor":
        if sample_weight is not None and _supports_sample_weight(model):
            model.fit(X_train, y_train, sample_weight=sample_weight)
        else:
            model.fit(X_train, y_train)
        return

    if np.any(np.isnan(X_val)) or np.any(np.isnan(y_val)):
        model.fit(X_train, y_train, sample_weight=sample_weight)
        return
    try:
        import lightgbm as lgb

        model.fit(
            X_train, y_train,
            sample_weight=sample_weight,
            eval_set=[(X_val, y_val)],
            callbacks=[
                lgb.early_stopping(30, verbose=False),
                lgb.log_evaluation(0),
            ],
        )
    except (ValueError, ImportError):
        model.fit(X_train, y_train, sample_weight=sample_weight)


def _supports_sample_weight(model: Any) -> bool:
    """Check if model.fit accepts sample_weight."""
    import inspect

    sig = inspect.signature(model.fit)
    return "sample_weight" in sig.parameters


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
    target_transform: str = "none",
    sample_weight: np.ndarray | None = None,
    monotonic_constraints: list[int] | None = None,
) -> CVResult:
    """RepeatedKFold CV with per-fold scaling (no leakage)."""
    rkf = RepeatedKFold(
        n_splits=n_splits, n_repeats=n_repeats, random_state=random_state,
    )

    r2_scores: list[float] = []
    mae_scores: list[float] = []
    rmse_scores: list[float] = []

    for train_idx, val_idx in rkf.split(X):
        X_tr, X_va = X[train_idx], X[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]
        w_tr = sample_weight[train_idx] if sample_weight is not None else None

        # Per-fold target transform
        pt = None
        if target_transform == "yeo-johnson":
            from sklearn.preprocessing import PowerTransformer

            pt = PowerTransformer(method="yeo-johnson", standardize=False)
            y_tr_fit = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()
        else:
            y_tr_fit = y_tr

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_va_s = scaler.transform(X_va)

        model = model_factory()

        # Apply monotonic constraints if supported
        if monotonic_constraints and hasattr(model, "set_params"):
            model.set_params(monotone_constraints=monotonic_constraints)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            _fit_with_early_stopping(
                model, X_tr_s, y_tr_fit, X_va_s, y_va, sample_weight=w_tr,
            )
            y_pred_raw = model.predict(X_va_s)

        if pt is not None:
            y_pred = pt.inverse_transform(y_pred_raw.reshape(-1, 1)).ravel()
        else:
            y_pred = y_pred_raw

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


def temporal_cross_validate(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    model_factory: Callable[[], Any],
    *,
    min_train_years: int = 3,
    target_transform: str = "none",
    sample_weight: np.ndarray | None = None,
    monotonic_constraints: list[int] | None = None,
) -> CVResult:
    """Expanding-window temporal CV grouped by retirement year."""
    groups = np.asarray(groups, dtype=float)
    finite_mask = ~np.isnan(groups)
    unique_years = sorted(set(groups[finite_mask].astype(int)))

    if len(unique_years) < min_train_years + 1:
        return cross_validate_model(
            X, y, model_factory, n_splits=5, n_repeats=3,
            target_transform=target_transform,
            sample_weight=sample_weight,
            monotonic_constraints=monotonic_constraints,
        )

    r2_scores: list[float] = []
    mae_scores: list[float] = []
    rmse_scores: list[float] = []

    groups_int = np.full(len(groups), -9999, dtype=int)
    groups_int[finite_mask] = groups[finite_mask].astype(int)

    for i in range(min_train_years, len(unique_years)):
        test_year = unique_years[i]
        train_years = set(unique_years[:i])

        train_mask = np.isin(groups_int, list(train_years))
        test_mask = groups_int == test_year

        if test_mask.sum() < 5:
            continue

        X_tr, X_te = X[train_mask], X[test_mask]
        y_tr, y_te = y[train_mask], y[test_mask]
        w_tr = sample_weight[train_mask] if sample_weight is not None else None

        pt = None
        if target_transform == "yeo-johnson":
            from sklearn.preprocessing import PowerTransformer

            pt = PowerTransformer(method="yeo-johnson", standardize=False)
            y_tr_fit = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()
        else:
            y_tr_fit = y_tr

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)

        model = model_factory()
        if monotonic_constraints and hasattr(model, "set_params"):
            model.set_params(monotone_constraints=monotonic_constraints)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            _fit_with_early_stopping(
                model, X_tr_s, y_tr_fit, X_te_s, y_te, sample_weight=w_tr,
            )
            y_pred_raw = model.predict(X_te_s)

        if pt is not None:
            y_pred = pt.inverse_transform(y_pred_raw.reshape(-1, 1)).ravel()
        else:
            y_pred = y_pred_raw

        ss_res = np.sum((y_te - y_pred) ** 2)
        ss_tot = np.sum((y_te - y_te.mean()) ** 2)
        r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

        r2_scores.append(r2)
        mae_scores.append(float(mean_absolute_error(y_te, y_pred)))
        rmse_scores.append(float(np.sqrt(mean_squared_error(y_te, y_pred))))

        logger.info(
            "  Temporal fold: train %s -> test %d (%d sets): R2=%.3f",
            sorted(train_years), test_year, test_mask.sum(), r2,
        )

    if not r2_scores:
        return cross_validate_model(
            X, y, model_factory, n_splits=5, n_repeats=3,
            target_transform=target_transform,
            sample_weight=sample_weight,
            monotonic_constraints=monotonic_constraints,
        )

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
# Hyperparameter tuning (Optuna)
# ---------------------------------------------------------------------------


def _get_search_space(trial: Any) -> dict:
    """Optuna-sampled LightGBM hyperparameters."""
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
        "alpha": trial.suggest_float("alpha", 0.5, 5.0),  # Huber delta
    }


def tune_and_select(
    X: np.ndarray,
    y: np.ndarray,
    *,
    n_trials: int = 75,
    n_splits: int = 5,
    n_repeats: int = 3,
    target_transform: str = "none",
    sample_weight: np.ndarray | None = None,
    monotonic_constraints: list[int] | None = None,
) -> tuple[dict, CVResult]:
    """Tune LightGBM with Optuna. Returns (best_params, cv_result)."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    best_params: dict = {}
    best_cv: CVResult | None = None

    def objective(trial: optuna.Trial) -> float:
        nonlocal best_params, best_cv
        params = _get_search_space(trial)
        cv = cross_validate_model(
            X, y,
            lambda p=params: build_model(p),
            n_splits=n_splits,
            n_repeats=n_repeats,
            target_transform=target_transform,
            sample_weight=sample_weight,
            monotonic_constraints=monotonic_constraints,
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

    # Re-evaluate best for clean CVResult
    final_cv = cross_validate_model(
        X, y,
        lambda: build_model(best_params),
        n_splits=n_splits,
        n_repeats=n_repeats,
        target_transform=target_transform,
        sample_weight=sample_weight,
        monotonic_constraints=monotonic_constraints,
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
        model_name="lightgbm",
        best_params=best_params,
    )
