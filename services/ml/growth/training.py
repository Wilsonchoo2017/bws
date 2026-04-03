"""Growth model training.

Trains Tier 1 (intrinsics), Tier 2 (intrinsics + Keepa), and
Tier 3 (all available features from plugin extractors) models.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

from config.ml import FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
from services.ml.extractors import extract_all as _extract_all_plugin
from services.ml.growth.evaluation import CIRCULAR_FEATURES
from services.ml.growth.features import (
    TIER1_FEATURES,
    TIER2_FEATURES,
    engineer_intrinsic_features,
    engineer_keepa_features,
)
from services.ml.growth.types import TrainedGrowthModel
from services.ml.helpers import compute_cutoff_dates
from services.ml.queries import (
    load_base_metadata,
    load_growth_training_data,
    load_keepa_timelines,
)

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
) -> tuple[TrainedGrowthModel, TrainedGrowthModel | None, dict, dict, TrainedGrowthModel | None]:
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

    # Tier 2: intrinsics + Keepa (with temporal cutoff for training)
    base_meta = load_base_metadata(conn, df_raw["set_number"].tolist())
    base_meta = compute_cutoff_dates(base_meta, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT)
    cutoff_dates: dict[str, str] = {}
    for _, row in base_meta.iterrows():
        cy, cm = row.get("cutoff_year"), row.get("cutoff_month")
        if pd.notna(cy) and pd.notna(cm):
            cutoff_dates[row["set_number"]] = f"{int(cy)}-{int(cm):02d}"

    df_kp = engineer_keepa_features(df_feat, keepa_df, cutoff_dates=cutoff_dates)
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

    # Tier 3: all extractor-based features
    tier3 = _train_tier3(conn, df_raw)

    return tier1, tier2, theme_stats, subtheme_stats, tier3


def _train_tier3(
    conn: DuckDBPyConnection,
    df_raw: pd.DataFrame,
) -> TrainedGrowthModel | None:
    """Train Tier 3 model using all plugin extractor features.

    Combines Tier 1 intrinsics with BrickLink momentum, BE charts,
    full Keepa timeline, and other extractor features.
    """
    set_numbers = df_raw["set_number"].tolist()

    # Build base metadata with cutoff dates
    base = load_base_metadata(conn, set_numbers)
    if base.empty:
        logger.info("Tier 3 skipped: no base metadata")
        return None

    base = compute_cutoff_dates(base, FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT)

    # Run all extractors
    extractor_features = _extract_all_plugin(conn, base)
    if extractor_features.empty:
        logger.info("Tier 3 skipped: no extractor features")
        return None

    # Merge extractor features with the training target
    target_df = df_raw[["set_number", "annual_growth_pct"]].drop_duplicates(subset=["set_number"])
    # Drop annual_growth_pct from extractor_features if it exists (avoid conflict)
    ext_cols = [c for c in extractor_features.columns if c != "annual_growth_pct"]
    merged = target_df.merge(
        extractor_features[ext_cols], on="set_number", how="inner"
    )

    if len(merged) < 30:
        logger.info("Tier 3 skipped: only %d sets with features (need 30+)", len(merged))
        return None

    y = merged["annual_growth_pct"].values.astype(float)

    # Use all numeric columns as features (excluding target, identifiers,
    # and CIRCULAR features that leak target information)
    exclude_cols = {"set_number", "annual_growth_pct"} | CIRCULAR_FEATURES
    feature_cols = [
        c for c in merged.columns
        if c not in exclude_cols
        and merged[c].dtype in ("float64", "int64", "float32", "int32")
    ]

    # Drop features with <10% non-null coverage
    min_coverage = 0.10
    feature_cols = [
        c for c in feature_cols
        if merged[c].notna().sum() / len(merged) >= min_coverage
    ]

    if len(feature_cols) < 5:
        logger.info("Tier 3 skipped: only %d features with coverage (need 5+)", len(feature_cols))
        return None

    X = merged[feature_cols].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    fill = X.median()
    X = X.fillna(fill)

    # Drop highly correlated features (keep the one with higher variance)
    corr_matrix = X.corr().abs()
    upper = corr_matrix.where(
        np.triu(np.ones(corr_matrix.shape, dtype=bool), k=1)
    )
    to_drop = set()
    for col in upper.columns:
        highly_corr = upper.index[upper[col] > 0.95].tolist()
        for hc in highly_corr:
            if hc not in to_drop:
                # Drop the one with lower variance
                if X[col].var() >= X[hc].var():
                    to_drop.add(hc)
                else:
                    to_drop.add(col)

    feature_cols = [c for c in feature_cols if c not in to_drop]
    X = X[feature_cols]

    logger.info(
        "Tier 3: %d sets, %d features after filtering (excluded %d circular)",
        len(y), len(feature_cols),
        sum(1 for c in merged.columns if c in CIRCULAR_FEATURES),
    )

    # -- Temporal OOS validation (80/20 split) for honest metrics --
    yr_map = base.set_index("set_number").get("year_released")
    if yr_map is not None:
        merged["_yr"] = merged["set_number"].map(yr_map)
        sorted_merged = merged.sort_values("_yr")
    else:
        sorted_merged = merged.sample(frac=1, random_state=42)

    split_idx = int(len(sorted_merged) * 0.8)
    train_idx = sorted_merged.index[:split_idx]
    test_idx = sorted_merged.index[split_idx:]

    X_tr_oos = X.loc[train_idx]
    X_te_oos = X.loc[test_idx]
    y_tr_oos = merged.loc[train_idx, "annual_growth_pct"].values.astype(float)
    y_te_oos = merged.loc[test_idx, "annual_growth_pct"].values.astype(float)

    scaler_oos = StandardScaler()
    X_tr_s = scaler_oos.fit_transform(X_tr_oos)
    X_te_s = scaler_oos.transform(X_te_oos)

    model_oos = _build_model()
    model_oos.fit(X_tr_s, y_tr_oos)
    y_pred_oos = model_oos.predict(X_te_s)
    ss_res = np.sum((y_te_oos - y_pred_oos) ** 2)
    ss_tot = np.sum((y_te_oos - y_te_oos.mean()) ** 2)
    oos_r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    logger.info(
        "Tier 3 OOS validation: train=%d, test=%d, OOS R2=%.3f",
        len(y_tr_oos), len(y_te_oos), oos_r2,
    )

    # -- Train final production model on ALL data --
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = _build_model()
    model.fit(X_scaled, y)
    y_pred = model.predict(X_scaled)
    r2 = float(1 - np.sum((y - y_pred) ** 2) / np.sum((y - y.mean()) ** 2))

    tier3 = TrainedGrowthModel(
        tier=3,
        model=model,
        scaler=scaler,
        feature_names=tuple(feature_cols),
        fill_values=tuple((f, float(fill[f])) for f in feature_cols),
        n_train=len(y),
        train_r2=r2,
        trained_at=datetime.now().isoformat(),
    )
    logger.info(
        "Tier 3 trained: %d sets, %d features, train R2=%.3f (OOS R2=%.3f)",
        len(y), len(feature_cols), r2, oos_r2,
    )

    # Log top 10 feature importances
    importances = model.feature_importances_
    ranked = sorted(zip(feature_cols, importances), key=lambda x: -x[1])[:10]
    for name, imp in ranked:
        logger.info("  Tier 3 feature: %-30s  %.4f", name, imp)

    return tier3
