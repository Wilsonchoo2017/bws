"""Growth prediction model -- backward compatibility wrapper.

All implementation has moved to services.ml.growth/ package.
This file re-exports the public API so existing imports continue to work.
"""

from services.ml.growth.features import (  # noqa: F401
    TIER1_FEATURES,
    TIER2_FEATURES,
    engineer_intrinsic_features as _engineer_intrinsic_features,
    engineer_keepa_features as _engineer_keepa_features,
)
from services.ml.growth.prediction import predict_growth  # noqa: F401
from services.ml.growth.training import train_growth_models  # noqa: F401
from services.ml.growth.types import GrowthPrediction, TrainedGrowthModel  # noqa: F401

from config.ml import LICENSED_THEMES  # noqa: F401

__all__ = [
    "GrowthPrediction",
    "TrainedGrowthModel",
    "predict_growth",
    "train_growth_models",
    "TIER1_FEATURES",
    "TIER2_FEATURES",
    "LICENSED_THEMES",
]
