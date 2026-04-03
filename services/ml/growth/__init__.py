"""Growth prediction model package.

Re-exports the public API for backward compatibility with existing
imports from services.ml.growth_model.
"""

from services.ml.growth.prediction import predict_growth, run_pipeline
from services.ml.growth.training import train_growth_models
from services.ml.growth.types import GrowthPrediction, TrainedGrowthModel

__all__ = [
    "GrowthPrediction",
    "TrainedGrowthModel",
    "predict_growth",
    "run_pipeline",
    "train_growth_models",
]
