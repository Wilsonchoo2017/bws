"""Growth model training.

Trains Tier 1 (intrinsics) and Tier 2 (intrinsics + Keepa) models.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

from services.ml.growth.features import (
    TIER1_FEATURES,
    TIER2_FEATURES,
    engineer_intrinsic_features,
    engineer_keepa_features,
)
from services.ml.growth.types import TrainedGrowthModel
from services.ml.queries import load_growth_training_data, load_keepa_timelines

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


def _build_model() -> GradientBoostingRegressor:
    return GradientBoostingRegressor(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=5,
        learning_rate=0.02,
        random_state=42,
    )


def train_growth_models(
    conn: DuckDBPyConnection,
) -> tuple[TrainedGrowthModel, TrainedGrowthModel | None, dict, dict]:
    """Train Tier 1 and Tier 2 growth models.

    Returns:
        (tier1_model, tier2_model_or_none, theme_stats, subtheme_stats)
    """
    df_raw = load_growth_training_data(conn)
    keepa_df = load_keepa_timelines(conn)

    y = df_raw["annual_growth_pct"].values.astype(float)

    # Tier 1: intrinsics
    df_feat, theme_stats, subtheme_stats = engineer_intrinsic_features(
        df_raw, training_target=pd.Series(y),
    )

    tier1_features = [f for f in TIER1_FEATURES if f in df_feat.columns]
    X1 = df_feat[tier1_features].copy()
    for c in X1.columns:
        X1[c] = pd.to_numeric(X1[c], errors="coerce")
    fill1 = X1.median()
    X1 = X1.fillna(fill1)

    scaler1 = StandardScaler()
    X1s = scaler1.fit_transform(X1)

    model1 = _build_model()
    model1.fit(X1s, y)
    y_pred1 = model1.predict(X1s)
    r2_1 = float(1 - np.sum((y - y_pred1) ** 2) / np.sum((y - y.mean()) ** 2))

    tier1 = TrainedGrowthModel(
        tier=1,
        model=model1,
        scaler=scaler1,
        feature_names=tuple(tier1_features),
        fill_values=tuple((f, float(fill1[f])) for f in tier1_features),
        n_train=len(y),
        train_r2=r2_1,
        trained_at=datetime.now().isoformat(),
    )
    logger.info(
        "Tier 1 trained: %d sets, %d features, train R2=%.3f",
        len(y), len(tier1_features), r2_1,
    )

    # Tier 2: intrinsics + Keepa
    df_kp = engineer_keepa_features(df_feat, keepa_df)
    has_keepa = df_kp["kp_bb_premium"].notna() | df_kp["kp_below_rrp_pct"].notna()
    df_kp_sub = df_kp[has_keepa].copy()
    y_kp = df_kp_sub["annual_growth_pct"].values.astype(float)

    tier2 = None
    if len(y_kp) >= 50:
        tier2_features = [f for f in TIER2_FEATURES if f in df_kp_sub.columns]
        X2 = df_kp_sub[tier2_features].copy()
        for c in X2.columns:
            X2[c] = pd.to_numeric(X2[c], errors="coerce")
        fill2 = X2.median()
        X2 = X2.fillna(fill2)

        scaler2 = StandardScaler()
        X2s = scaler2.fit_transform(X2)

        model2 = _build_model()
        model2.fit(X2s, y_kp)
        y_pred2 = model2.predict(X2s)
        r2_2 = float(1 - np.sum((y_kp - y_pred2) ** 2) / np.sum((y_kp - y_kp.mean()) ** 2))

        tier2 = TrainedGrowthModel(
            tier=2,
            model=model2,
            scaler=scaler2,
            feature_names=tuple(tier2_features),
            fill_values=tuple((f, float(fill2[f])) for f in tier2_features),
            n_train=len(y_kp),
            train_r2=r2_2,
            trained_at=datetime.now().isoformat(),
        )
        logger.info(
            "Tier 2 trained: %d sets, %d features, train R2=%.3f",
            len(y_kp), len(tier2_features), r2_2,
        )
    else:
        logger.info("Tier 2 skipped: only %d Keepa sets (need 50+)", len(y_kp))

    return tier1, tier2, theme_stats, subtheme_stats
