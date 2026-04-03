"""Inversion pipeline builder.

Builds pipelines optimized for left-tail prediction (identifying sets to avoid).
Uses balanced class weights and power transforms for skewed features.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.ml import MLPipelineConfig


class InversionPipelineBuilder:
    """Builds sklearn pipelines for inversion (avoid) classification."""

    @property
    def task(self) -> str:
        return "inversion"

    def build(self, config: MLPipelineConfig) -> list[tuple[str, object]]:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import PowerTransformer, StandardScaler

        return [
            (
                "InversionLR",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("power", PowerTransformer(method="yeo-johnson", standardize=False)),
                    ("scaler", StandardScaler()),
                    ("model", LogisticRegression(
                        C=1.0,
                        class_weight="balanced",
                        random_state=config.random_state,
                        max_iter=1000,
                    )),
                ]),
            ),
            (
                "InversionLR_L1",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("power", PowerTransformer(method="yeo-johnson", standardize=False)),
                    ("scaler", StandardScaler()),
                    ("model", LogisticRegression(
                        solver="saga",
                        C=0.5,
                        l1_ratio=1.0,
                        class_weight="balanced",
                        random_state=config.random_state,
                        max_iter=2000,
                    )),
                ]),
            ),
            (
                "InversionGBM",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("model", HistGradientBoostingClassifier(
                        max_iter=200,
                        max_depth=4,
                        learning_rate=0.05,
                        class_weight="balanced",
                        random_state=config.random_state,
                    )),
                ]),
            ),
        ]
