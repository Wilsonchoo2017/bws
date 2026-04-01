"""Automated feature selection for the ML pipeline.

Combines multiple methods (correlation filter, mutual information, L1)
and selects features that survive at least 2 out of 3 methods.
"""

import logging

import numpy as np
import pandas as pd

from config.ml import MLPipelineConfig
from services.ml.types import SelectionResult

logger = logging.getLogger(__name__)


def select_features(
    df: pd.DataFrame,
    target_column: str,
    feature_columns: list[str],
    config: MLPipelineConfig | None = None,
) -> SelectionResult:
    """Run multiple feature selection methods and combine results.

    Methods:
    1. Correlation filter: drop one from pairs with r > threshold
    2. Mutual information: rank by MI with target, keep top N
    3. L1 (Lasso): features surviving Lasso regularization

    Features selected by >= 2 methods are kept.
    """
    if config is None:
        config = MLPipelineConfig()

    available = [c for c in feature_columns if c in df.columns]
    valid = df[available + [target_column]].dropna(subset=[target_column])

    if len(valid) < 20 or len(available) < 2:
        logger.warning(
            "Too few samples (%d) or features (%d) for selection",
            len(valid),
            len(available),
        )
        return SelectionResult(
            selected_features=available,
            dropped_features=[],
            method_results={},
        )

    # Fill NaN with median for selection algorithms
    filled = valid[available].fillna(valid[available].median())
    target = valid[target_column].values

    # 1. Correlation filter
    corr_survivors = _drop_high_correlation(
        filled, available, config.correlation_threshold
    )

    # 2. Mutual information ranking
    mi_scores = _mutual_info_ranking(filled, available, target)
    mi_top_n = min(config.max_features, len(available))
    mi_sorted = sorted(mi_scores.items(), key=lambda x: x[1], reverse=True)
    mi_survivors = [name for name, _ in mi_sorted[:mi_top_n]]

    # 3. L1 (Lasso) selection
    l1_survivors = _l1_selection(filled, available, target, config)

    # Combine by voting: keep features selected by >= 2 methods
    votes: dict[str, int] = {}
    for feat in available:
        count = 0
        if feat in corr_survivors:
            count += 1
        if feat in mi_survivors:
            count += 1
        if feat in l1_survivors:
            count += 1
        votes[feat] = count

    selected = [f for f in available if votes.get(f, 0) >= 2]
    dropped = [f for f in available if f not in selected]

    # If selection is too aggressive, fall back to MI top N
    if len(selected) < 5 and len(mi_survivors) >= 5:
        logger.warning(
            "Voting selected only %d features, falling back to MI top %d",
            len(selected),
            mi_top_n,
        )
        selected = mi_survivors[:mi_top_n]
        dropped = [f for f in available if f not in selected]

    logger.info(
        "Feature selection: %d selected, %d dropped (corr=%d, MI=%d, L1=%d)",
        len(selected),
        len(dropped),
        len(corr_survivors),
        len(mi_survivors),
        len(l1_survivors),
    )

    return SelectionResult(
        selected_features=selected,
        dropped_features=dropped,
        method_results={
            "correlation": {f: 1.0 for f in corr_survivors},
            "mutual_info": mi_scores,
            "l1": {f: 1.0 for f in l1_survivors},
            "votes": {f: float(v) for f, v in votes.items()},
        },
    )


def _drop_high_correlation(
    df: pd.DataFrame,
    features: list[str],
    threshold: float,
) -> list[str]:
    """Remove one feature from each pair with abs correlation > threshold.

    Keeps the feature that appears first in the input list (arbitrary but
    deterministic).
    """
    if len(features) < 2:
        return list(features)

    corr_matrix = df[features].corr().abs()
    to_drop: set[str] = set()

    for i in range(len(features)):
        if features[i] in to_drop:
            continue
        for j in range(i + 1, len(features)):
            if features[j] in to_drop:
                continue
            if corr_matrix.iloc[i, j] > threshold:
                to_drop.add(features[j])
                logger.debug(
                    "Dropping %s (corr=%.3f with %s)",
                    features[j],
                    corr_matrix.iloc[i, j],
                    features[i],
                )

    return [f for f in features if f not in to_drop]


def _mutual_info_ranking(
    df: pd.DataFrame,
    features: list[str],
    target: np.ndarray,
) -> dict[str, float]:
    """Rank features by mutual information with the target."""
    from sklearn.feature_selection import mutual_info_regression

    x = df[features].values
    mi = mutual_info_regression(x, target, random_state=42, n_neighbors=5)
    return dict(zip(features, [float(v) for v in mi]))


def _l1_selection(
    df: pd.DataFrame,
    features: list[str],
    target: np.ndarray,
    config: MLPipelineConfig,
) -> list[str]:
    """Return features with non-zero Lasso coefficients."""
    from sklearn.linear_model import Lasso
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(df[features].values)

    # Use LassoCV-like alpha search: try a range and pick one that
    # keeps a reasonable number of features
    for alpha in [0.1, 0.05, 0.01, 0.005, 0.001]:
        model = Lasso(
            alpha=alpha,
            random_state=config.random_state,
            max_iter=5000,
        )
        model.fit(x_scaled, target)
        non_zero = [
            features[i]
            for i in range(len(features))
            if abs(model.coef_[i]) > 1e-6
        ]
        if len(non_zero) >= 5:
            return non_zero

    # If no alpha gives >= 5 features, return all non-zero from loosest alpha
    model = Lasso(alpha=0.001, random_state=config.random_state, max_iter=5000)
    model.fit(x_scaled, target)
    return [
        features[i]
        for i in range(len(features))
        if abs(model.coef_[i]) > 1e-6
    ]
