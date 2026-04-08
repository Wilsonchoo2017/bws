"""Feature selection for the growth model.

Uses mutual information, correlation-based filtering, and LOFO pruning
to select the most predictive non-redundant features.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression

logger = logging.getLogger(__name__)


def select_features(
    X: pd.DataFrame,
    y: np.ndarray,
    *,
    min_mi_score: float = 0.01,
    max_correlation: float = 0.90,
    min_coverage: float = 0.3,
    lofo_prune: bool = True,
) -> list[str]:
    """Select features using MI + redundancy filtering + LOFO pruning.

    Steps:
    1. Drop features with too many missing values (< min_coverage)
    2. Rank by mutual information with target
    3. Remove features below min_mi_score
    4. Greedily remove redundant features (pairwise |corr| > max_correlation)
    5. LOFO pruning: iteratively drop features that hurt CV R2

    Returns list of selected feature names.
    """
    # Step 1: Coverage filter
    coverage = X.notna().mean()
    low_coverage = coverage[coverage < min_coverage].index.tolist()
    if low_coverage:
        logger.info("Dropped %d features with <%.0f%% coverage: %s",
                     len(low_coverage), min_coverage * 100, low_coverage)

    candidates = [c for c in X.columns if c not in low_coverage]
    if not candidates:
        return []

    # Prepare data for MI (impute NaN with median for MI computation)
    X_filled = X[candidates].copy()
    for c in X_filled.columns:
        X_filled[c] = pd.to_numeric(X_filled[c], errors="coerce")
    X_filled = X_filled.fillna(X_filled.median())

    # Step 2: Mutual information scores
    n_samples = len(X_filled)
    if n_samples <= 1:
        logger.warning("Only %d sample(s) — skipping feature selection, returning all candidates", n_samples)
        return candidates
    n_neighbors = min(5, n_samples - 1)
    mi_scores = mutual_info_regression(X_filled, y, random_state=42, n_neighbors=n_neighbors)
    mi_df = pd.DataFrame({
        "feature": candidates,
        "mi_score": mi_scores,
    }).sort_values("mi_score", ascending=False)

    logger.info("MI scores:\n%s", mi_df.to_string(index=False))

    # Step 3: Filter by MI threshold
    selected = mi_df[mi_df["mi_score"] >= min_mi_score]["feature"].tolist()
    dropped_mi = mi_df[mi_df["mi_score"] < min_mi_score]["feature"].tolist()
    if dropped_mi:
        logger.info("Dropped %d features below MI threshold %.3f: %s",
                     len(dropped_mi), min_mi_score, dropped_mi)

    if len(selected) < 2:
        return selected

    # Step 4: Redundancy filter (greedy)
    corr_matrix = X_filled[selected].corr().abs()
    to_drop: set[str] = set()
    mi_lookup = dict(zip(mi_df["feature"], mi_df["mi_score"]))

    for i, feat_i in enumerate(selected):
        if feat_i in to_drop:
            continue
        for feat_j in selected[i + 1:]:
            if feat_j in to_drop:
                continue
            if corr_matrix.loc[feat_i, feat_j] > max_correlation:
                drop = feat_j if mi_lookup[feat_i] >= mi_lookup[feat_j] else feat_i
                to_drop.add(drop)
                logger.info("Redundancy: %s vs %s (corr=%.2f) -> dropped %s",
                            feat_i, feat_j, corr_matrix.loc[feat_i, feat_j], drop)

    after_redundancy = [f for f in selected if f not in to_drop]
    logger.info("After MI + redundancy: %d -> %d features", len(candidates), len(after_redundancy))

    # Step 5: LOFO pruning (iteratively drop features that hurt CV R2)
    if lofo_prune and len(after_redundancy) > 5:
        final = _lofo_prune(X_filled, y, after_redundancy)
    else:
        final = after_redundancy

    logger.info("Feature selection: %d -> %d features", len(candidates), len(final))
    return final


def _lofo_prune(
    X: pd.DataFrame,
    y: np.ndarray,
    features: list[str],
    *,
    max_rounds: int = 5,
) -> list[str]:
    """Iteratively drop the feature whose removal most improves CV R2.

    Stops when no feature removal improves the score.
    Uses fast 5-fold CV (no repeats) for speed.
    """
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler

    def _cv_r2(feat_list: list[str]) -> float:
        from services.ml.growth.model_selection import build_model
        Xs = StandardScaler().fit_transform(X[feat_list].values)
        scores = cross_val_score(
            build_model(), Xs, y,
            cv=5, scoring="r2",
        )
        return float(np.mean(scores))

    current = list(features)
    baseline = _cv_r2(current)
    logger.info("LOFO prune baseline: R2=%.4f with %d features", baseline, len(current))

    for round_num in range(max_rounds):
        best_drop = None
        best_r2 = baseline

        for feat in current:
            without = [f for f in current if f != feat]
            r2 = _cv_r2(without)
            if r2 > best_r2:
                best_r2 = r2
                best_drop = feat

        if best_drop is None:
            logger.info("LOFO prune round %d: no improvement, stopping", round_num + 1)
            break

        improvement = best_r2 - baseline
        current = [f for f in current if f != best_drop]
        logger.info(
            "LOFO prune round %d: dropped %s (R2 %.4f -> %.4f, +%.4f)",
            round_num + 1, best_drop, baseline, best_r2, improvement,
        )
        baseline = best_r2

    return current
