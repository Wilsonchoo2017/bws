"""Classification pipeline builder.

Builds LogisticRegression and HistGradientBoostingClassifier pipelines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.ml import MLPipelineConfig


class ClassificationPipelineBuilder:
    """Builds sklearn pipelines for binary classification tasks."""

    @property
    def task(self) -> str:
        return "classification"

    def build(self, config: MLPipelineConfig) -> list[tuple[str, object]]:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        return [
            (
                "LogisticRegression",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler()),
                    ("model", LogisticRegression(
                        C=1.0, random_state=config.random_state, max_iter=1000
                    )),
                ]),
            ),
            (
                "GBClassifier",
                HistGradientBoostingClassifier(
                    max_iter=200,
                    max_depth=4,
                    learning_rate=0.05,
                    random_state=config.random_state,
                ),
            ),
        ]
