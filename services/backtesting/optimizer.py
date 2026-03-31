"""ML-based signal weight optimization.

Trains multiple models (Ridge, Lasso, HistGradientBoosting) using
time-series cross-validation to learn optimal signal weights from
historical backtest data. Avoids look-ahead bias by ensuring training
data always precedes test data chronologically.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from services.backtesting.features import DEFAULT_INTERACTION_PAIRS
from services.backtesting.types import SIGNAL_NAMES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OptimizerConfig:
    """Configuration for the ML optimizer."""

    target_column: str = "best_hold_apr"
    min_samples: int = 50
    n_cv_splits: int = 5
    test_fraction: float = 0.2
    random_state: int = 42


@dataclass(frozen=True)
class OptimizationResult:
    """Result of one model optimization run."""

    model_name: str
    weights: dict[str, float]
    train_score: float
    test_score: float
    test_apr_mean: float
    test_hit_rate: float
    test_quintile_spread: float
    feature_importances: dict[str, float]
    n_train: int
    n_test: int


def optimize_weights(
    df: pd.DataFrame,
    feature_columns: list[str],
    config: OptimizerConfig | None = None,
) -> list[OptimizationResult]:
    """Run multiple models and return ranked optimization results.

    Data is sorted chronologically, split into train (first 80%) and
    test (last 20%). TimeSeriesSplit is used for cross-validation within
    the training set to select hyperparameters.

    Models trained:
        1. Ridge (L2) - interpretable linear weights
        2. Lasso (L1) - sparse weights, automatic feature selection
        3. HistGradientBoostingRegressor - non-linear patterns

    Returns results sorted by test_quintile_spread (descending).
    """
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Lasso, Ridge
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if config is None:
        config = OptimizerConfig()

    # Sort chronologically
    sorted_df = df.sort_values(["entry_year", "entry_month"]).reset_index(
        drop=True
    )

    # Drop rows where target is missing
    valid = sorted_df.dropna(subset=[config.target_column])
    available_features = [c for c in feature_columns if c in valid.columns]

    if len(valid) < config.min_samples:
        logger.warning(
            "Only %d samples (need %d). Skipping optimization.",
            len(valid),
            config.min_samples,
        )
        return []

    # Train/test split (chronological, no shuffle)
    split_idx = int(len(valid) * (1 - config.test_fraction))
    train_df = valid.iloc[:split_idx]
    test_df = valid.iloc[split_idx:]

    if len(train_df) < 20 or len(test_df) < 10:
        logger.warning(
            "Train=%d, test=%d: too small for reliable results.",
            len(train_df),
            len(test_df),
        )
        return []

    x_train = train_df[available_features]
    y_train = train_df[config.target_column].values
    x_test = test_df[available_features]
    y_test = test_df[config.target_column].values

    cv = TimeSeriesSplit(n_splits=min(config.n_cv_splits, len(train_df) // 10))

    results: list[OptimizationResult] = []

    # 1. Ridge regression
    ridge_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", Ridge(alpha=1.0, random_state=config.random_state)),
    ])
    ridge_result = _train_linear_model(
        ridge_pipe,
        x_train,
        y_train,
        x_test,
        y_test,
        test_df,
        available_features,
        cv,
        config,
        "Ridge",
    )
    if ridge_result is not None:
        results.append(ridge_result)

    # 2. Lasso regression
    lasso_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", Lasso(alpha=0.01, random_state=config.random_state, max_iter=5000)),
    ])
    lasso_result = _train_linear_model(
        lasso_pipe,
        x_train,
        y_train,
        x_test,
        y_test,
        test_df,
        available_features,
        cv,
        config,
        "Lasso",
    )
    if lasso_result is not None:
        results.append(lasso_result)

    # 3. HistGradientBoostingRegressor (handles NaN natively)
    gbrt_result = _train_tree_model(
        x_train,
        y_train,
        x_test,
        y_test,
        test_df,
        available_features,
        config,
    )
    if gbrt_result is not None:
        results.append(gbrt_result)

    # Sort by test quintile spread (descending)
    results.sort(key=lambda r: r.test_quintile_spread, reverse=True)
    return results


def extract_signal_weights(
    result: OptimizationResult,
    signal_names: tuple[str, ...] = SIGNAL_NAMES,
) -> dict[str, float]:
    """Extract weights for the 14 base signals from an OptimizationResult.

    For interaction features, importance is split equally between the
    constituent signals. Weights are normalized so the mean = 1.0,
    matching the convention in config/kelly.py.
    """
    # Build interaction -> constituent signals mapping
    interaction_map: dict[str, tuple[str, str]] = {
        pair[2]: (pair[0], pair[1]) for pair in DEFAULT_INTERACTION_PAIRS
    }

    raw_weights: dict[str, float] = {}
    for signal in signal_names:
        raw_weights[signal] = 0.0

    for feature, importance in result.feature_importances.items():
        abs_importance = abs(importance)
        if feature in signal_names:
            raw_weights[feature] += abs_importance
        elif feature in interaction_map:
            sig_a, sig_b = interaction_map[feature]
            if sig_a in raw_weights:
                raw_weights[sig_a] += abs_importance / 2.0
            if sig_b in raw_weights:
                raw_weights[sig_b] += abs_importance / 2.0

    # Normalize so mean = 1.0
    values = list(raw_weights.values())
    if not values:
        return raw_weights

    mean_val = sum(values) / len(values)
    if mean_val <= 0:
        return {k: 1.0 for k in raw_weights}

    return {k: round(v / mean_val, 3) for k, v in raw_weights.items()}


def compare_with_handtuned(
    df: pd.DataFrame,
    ml_weights: dict[str, float],
    handtuned_weights: dict[str, float],
    target_column: str,
) -> dict[str, dict[str, float]]:
    """Compare ML-optimized vs hand-tuned weights on the DataFrame.

    Returns dict with keys 'ml' and 'handtuned', each containing:
        top_quintile_apr, bottom_quintile_apr, quintile_spread,
        hit_rate, mean_apr
    """
    valid = df.dropna(subset=[target_column])
    if len(valid) < 10:
        return {}

    result: dict[str, dict[str, float]] = {}
    for label, weights in [("ml", ml_weights), ("handtuned", handtuned_weights)]:
        scores = _score_items(valid, weights)
        metrics = _compute_quintile_metrics(scores, valid[target_column])
        result[label] = metrics

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _train_linear_model(
    pipeline: "Pipeline",
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    x_test: pd.DataFrame,
    y_test: np.ndarray,
    test_df: pd.DataFrame,
    feature_names: list[str],
    cv: "TimeSeriesSplit",
    config: OptimizerConfig,
    model_name: str,
) -> OptimizationResult | None:
    """Train a linear model pipeline and evaluate."""
    from sklearn.model_selection import cross_val_score

    try:
        cv_scores = cross_val_score(
            pipeline, x_train, y_train, cv=cv, scoring="r2"
        )
        pipeline.fit(x_train, y_train)
        test_score = pipeline.score(x_test, y_test)

        # Extract coefficients from the model step
        model = pipeline.named_steps["model"]
        scaler = pipeline.named_steps["scaler"]

        # Unscale coefficients to original feature space
        coefs = model.coef_ / scaler.scale_
        importances = dict(zip(feature_names, coefs))

        predictions = pipeline.predict(x_test)
        metrics = _evaluate_predictions(
            predictions, y_test, test_df, config.target_column
        )

        return OptimizationResult(
            model_name=model_name,
            weights=importances,
            train_score=float(np.mean(cv_scores)),
            test_score=float(test_score),
            test_apr_mean=metrics["mean_apr"],
            test_hit_rate=metrics["hit_rate"],
            test_quintile_spread=metrics["quintile_spread"],
            feature_importances=importances,
            n_train=len(x_train),
            n_test=len(x_test),
        )
    except Exception:
        logger.warning("Failed to train %s", model_name, exc_info=True)
        return None


def _train_tree_model(
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    x_test: pd.DataFrame,
    y_test: np.ndarray,
    test_df: pd.DataFrame,
    feature_names: list[str],
    config: OptimizerConfig,
) -> OptimizationResult | None:
    """Train HistGradientBoostingRegressor and evaluate."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.inspection import permutation_importance
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score

    try:
        model = HistGradientBoostingRegressor(
            max_iter=200,
            max_depth=4,
            learning_rate=0.05,
            random_state=config.random_state,
        )

        # Fill NaN for cross_val_score (HGBR handles NaN natively in fit/predict
        # but cross_val_score may not propagate this correctly)
        x_train_vals = x_train.values
        x_test_vals = x_test.values

        cv = TimeSeriesSplit(
            n_splits=min(config.n_cv_splits, len(x_train) // 10)
        )
        cv_scores = cross_val_score(model, x_train_vals, y_train, cv=cv, scoring="r2")

        model.fit(x_train_vals, y_train)
        test_score = model.score(x_test_vals, y_test)

        perm = permutation_importance(
            model, x_test_vals, y_test, n_repeats=10,
            random_state=config.random_state,
        )
        importances = dict(zip(feature_names, perm.importances_mean))

        predictions = model.predict(x_test_vals)
        metrics = _evaluate_predictions(
            predictions, y_test, test_df, config.target_column
        )

        return OptimizationResult(
            model_name="GBRT",
            weights=importances,
            train_score=float(np.mean(cv_scores)),
            test_score=float(test_score),
            test_apr_mean=metrics["mean_apr"],
            test_hit_rate=metrics["hit_rate"],
            test_quintile_spread=metrics["quintile_spread"],
            feature_importances=importances,
            n_train=len(x_train),
            n_test=len(x_test),
        )
    except Exception:
        logger.warning("Failed to train GBRT", exc_info=True)
        return None


def _evaluate_predictions(
    predictions: np.ndarray,
    y_true: np.ndarray,
    test_df: pd.DataFrame,
    target_column: str,
) -> dict[str, float]:
    """Compute evaluation metrics from model predictions."""
    # Sort test data by predicted score (higher = better)
    order = np.argsort(predictions)[::-1]
    sorted_actual = y_true[order]

    n = len(sorted_actual)
    if n < 5:
        return {"mean_apr": 0.0, "hit_rate": 0.0, "quintile_spread": 0.0}

    q_size = max(1, n // 5)
    top_q = sorted_actual[:q_size]
    bottom_q = sorted_actual[-q_size:]

    mean_apr = float(np.nanmean(top_q))
    hit_rate = float(np.nanmean(top_q > 0)) if len(top_q) > 0 else 0.0
    quintile_spread = float(np.nanmedian(top_q) - np.nanmedian(bottom_q))

    return {
        "mean_apr": mean_apr,
        "hit_rate": hit_rate,
        "quintile_spread": quintile_spread,
    }


def _score_items(
    df: pd.DataFrame,
    weights: dict[str, float],
) -> np.ndarray:
    """Score items using weighted signal sum."""
    scores = np.zeros(len(df))
    weight_sum = 0.0

    for signal, weight in weights.items():
        if signal not in df.columns:
            continue
        values = df[signal].fillna(0).values
        scores += values * weight
        weight_sum += abs(weight)

    if weight_sum > 0:
        scores /= weight_sum

    return scores


def _compute_quintile_metrics(
    scores: np.ndarray,
    actual_returns: pd.Series,
) -> dict[str, float]:
    """Compute quintile-based evaluation metrics."""
    order = np.argsort(scores)[::-1]
    sorted_returns = actual_returns.values[order]

    n = len(sorted_returns)
    if n < 5:
        return {
            "top_quintile_apr": 0.0,
            "bottom_quintile_apr": 0.0,
            "quintile_spread": 0.0,
            "hit_rate": 0.0,
            "mean_apr": 0.0,
        }

    q_size = max(1, n // 5)
    top_q = sorted_returns[:q_size]
    bottom_q = sorted_returns[-q_size:]

    top_median = float(np.nanmedian(top_q))
    bottom_median = float(np.nanmedian(bottom_q))

    return {
        "top_quintile_apr": top_median,
        "bottom_quintile_apr": bottom_median,
        "quintile_spread": top_median - bottom_median,
        "hit_rate": float(np.nanmean(top_q > 0)),
        "mean_apr": float(np.nanmean(top_q)),
    }
