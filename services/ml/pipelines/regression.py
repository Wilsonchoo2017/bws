"""Regression pipeline builder.

Builds Ridge, Lasso, and HistGradientBoostingRegressor pipelines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.ml import MLPipelineConfig


class RegressionPipelineBuilder:
    """Builds sklearn pipelines for regression tasks."""

    @property
    def task(self) -> str:
        return "regression"

    def build(self, config: MLPipelineConfig) -> list[tuple[str, object]]:
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Lasso, Ridge
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        return [
            (
                "Ridge",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler()),
                    ("model", Ridge(alpha=1.0, random_state=config.random_state)),
                ]),
            ),
            (
                "Lasso",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler()),
                    ("model", Lasso(alpha=0.01, random_state=config.random_state, max_iter=5000)),
                ]),
            ),
            (
                "GBRT",
                HistGradientBoostingRegressor(
                    max_iter=200,
                    max_depth=4,
                    learning_rate=0.05,
                    random_state=config.random_state,
                ),
            ),
        ]
