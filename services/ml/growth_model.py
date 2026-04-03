"""Growth prediction model based on research experiments 01-12.

Tiered model:
- Tier 1 (all sets): Intrinsics + theme/subtheme encoding (14 features)
- Tier 2 (sets with Keepa): Adds pre-OOS Amazon + buy box premium (+7 features)

Model: GradientBoostingRegressor (d=4, leaf=6, n=250, lr=0.02)
Target: annual_growth_pct from BrickEconomy

Key features by importance:
- subtheme_loo, theme_bayes (identity dominates)
- kp_bb_premium (free market signal, Tier 2 only)
- minifig_density, usd_gbp_ratio, log_parts
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

LICENSED_THEMES: frozenset[str] = frozenset({
    "Star Wars", "Super Heroes", "Harry Potter", "Jurassic World",
    "Avatar", "The LEGO Movie 2", "Disney", "Minecraft", "BrickHeadz",
})

TIER1_FEATURES: tuple[str, ...] = (
    "log_rrp", "log_parts", "price_per_part", "mfigs", "minifig_density",
    "price_tier", "rating_value", "review_count", "theme_bayes",
    "theme_size", "is_licensed", "usd_gbp_ratio", "subtheme_loo", "sub_size",
)

TIER2_FEATURES: tuple[str, ...] = TIER1_FEATURES + (
    "kp_below_rrp_pct", "kp_avg_discount", "kp_max_discount",
    "kp_price_trend", "kp_price_cv", "kp_months_stock", "kp_bb_premium",
)


@dataclass(frozen=True)
class GrowthPrediction:
    """Prediction result for a single set."""

    set_number: str
    title: str
    theme: str
    predicted_growth_pct: float
    confidence: str  # "high", "moderate", "low"
    tier: int  # 1 or 2
    feature_contributions: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class TrainedGrowthModel:
    """A fitted growth model with scaler and metadata."""

    tier: int
    model: GradientBoostingRegressor
    scaler: StandardScaler
    feature_names: tuple[str, ...]
    fill_values: tuple[tuple[str, float], ...]  # (feature, median) for NaN imputation
    n_train: int
    train_r2: float
    trained_at: str


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_training_data(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load all sets with BrickEconomy growth data."""
    return conn.execute("""
        SELECT
            li.set_number, li.title, li.theme,
            li.parts_count, li.minifig_count,
            be.annual_growth_pct, be.rrp_usd_cents, be.rating_value,
            be.review_count, be.pieces, be.minifigs,
            be.rrp_gbp_cents, be.subtheme
        FROM lego_items li
        JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
        WHERE be.annual_growth_pct IS NOT NULL
          AND be.rrp_usd_cents > 0
    """).fetchdf()


def _load_keepa_timelines(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load Keepa historical price data."""
    return conn.execute("""
        SELECT set_number, amazon_price_json, buy_box_json,
               tracking_users, review_count AS kp_reviews, rating AS kp_rating
        FROM keepa_snapshots
        WHERE amazon_price_json IS NOT NULL
    """).fetchdf()


def _load_candidate_sets(conn: DuckDBPyConnection) -> pd.DataFrame:
    """Load sets eligible for prediction (retiring soon or all with BE data)."""
    return conn.execute("""
        SELECT
            li.set_number, li.title, li.theme,
            li.parts_count, li.minifig_count, li.retiring_soon,
            be.rrp_usd_cents, be.rating_value, be.review_count,
            be.pieces, be.minifigs, be.rrp_gbp_cents, be.subtheme
        FROM lego_items li
        JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
        WHERE be.rrp_usd_cents > 0
    """).fetchdf()


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------


def _engineer_intrinsic_features(
    df: pd.DataFrame,
    *,
    training_target: pd.Series | None = None,
    theme_stats: dict | None = None,
    subtheme_stats: dict | None = None,
) -> tuple[pd.DataFrame, dict, dict]:
    """Build Tier 1 intrinsic features.

    When training_target is provided, computes LOO theme/subtheme encodings.
    When theme_stats/subtheme_stats are provided, uses pre-computed values
    (for prediction on new sets).

    Returns (df_with_features, theme_stats, subtheme_stats).
    """
    result = df.copy()

    for col in ("parts_count", "minifig_count", "rrp_usd_cents",
                "rrp_gbp_cents", "review_count", "pieces", "minifigs",
                "rating_value"):
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    parts_raw = pd.to_numeric(
        result["parts_count"].fillna(result.get("pieces", 0)), errors="coerce"
    ).fillna(0)
    rrp_raw = pd.to_numeric(result["rrp_usd_cents"], errors="coerce").fillna(0)
    mfigs_raw = pd.to_numeric(
        result.get("minifig_count", pd.Series(0, index=result.index)).fillna(
            result.get("minifigs", pd.Series(0, index=result.index))
        ), errors="coerce"
    ).fillna(0)

    result["log_rrp"] = np.log1p(rrp_raw)
    result["log_parts"] = np.log1p(parts_raw)
    result["price_per_part"] = np.where(parts_raw > 0, rrp_raw / parts_raw, np.nan)
    result["mfigs"] = mfigs_raw
    result["minifig_density"] = np.where(
        parts_raw > 0, mfigs_raw / parts_raw * 100, np.nan
    )
    result["price_tier"] = pd.cut(
        rrp_raw / 100,
        bins=[0, 15, 30, 50, 80, 120, 200, 500, 9999],
        labels=range(1, 9),
    ).astype(float)
    result["is_licensed"] = result["theme"].isin(LICENSED_THEMES).astype(int)

    gbp = result["rrp_gbp_cents"].fillna(0) if "rrp_gbp_cents" in result.columns else 0
    result["usd_gbp_ratio"] = np.where(gbp > 0, rrp_raw / gbp, np.nan)

    # Theme encoding
    if training_target is not None and theme_stats is None:
        # Training mode: compute Bayesian LOO theme encoding
        gm = float(training_target.mean())
        alpha = 20

        ts = pd.DataFrame({
            "theme": result["theme"],
            "growth": training_target,
        }).groupby("theme")["growth"].agg(["sum", "count"])

        theme_stats_out = {"global_mean": gm, "alpha": alpha, "themes": {}}
        for theme, row in ts.iterrows():
            theme_stats_out["themes"][theme] = {
                "sum": float(row["sum"]),
                "count": int(row["count"]),
            }

        # LOO Bayesian (vectorized)
        theme_sum_map = result["theme"].map(
            {t: d["sum"] for t, d in theme_stats_out["themes"].items()}
        )
        theme_cnt_map = result["theme"].map(
            {t: d["count"] for t, d in theme_stats_out["themes"].items()}
        )
        loo_sum = theme_sum_map - training_target.values
        loo_cnt = theme_cnt_map - 1
        result["theme_bayes"] = np.where(
            loo_cnt > 0,
            (loo_sum + alpha * gm) / (loo_cnt + alpha),
            gm,
        )

        result["theme_size"] = theme_cnt_map.fillna(1)

        theme_stats = theme_stats_out
    elif theme_stats is not None:
        # Prediction mode: use pre-computed stats
        gm = theme_stats["global_mean"]
        alpha = theme_stats["alpha"]
        for idx in result.index:
            t = result.loc[idx, "theme"]
            t_info = theme_stats["themes"].get(t)
            if t_info:
                result.loc[idx, "theme_bayes"] = (
                    (t_info["sum"] + alpha * gm) / (t_info["count"] + alpha)
                )
                result.loc[idx, "theme_size"] = t_info["count"]
            else:
                result.loc[idx, "theme_bayes"] = gm
                result.loc[idx, "theme_size"] = 1

    # Subtheme encoding
    if training_target is not None and subtheme_stats is None:
        gm = float(training_target.mean())
        sub_df = pd.DataFrame({
            "subtheme": result["subtheme"],
            "growth": training_target,
        })
        sub_agg = sub_df.groupby("subtheme")["growth"].agg(["sum", "count"])
        subtheme_stats_out = {"global_mean": gm, "subthemes": {}}
        for sub, row in sub_agg.iterrows():
            if row["count"] >= 3:
                subtheme_stats_out["subthemes"][sub] = {
                    "sum": float(row["sum"]),
                    "count": int(row["count"]),
                }

        # LOO subtheme (vectorized)
        sub_sum_map = result["subtheme"].map(
            {s: d["sum"] for s, d in subtheme_stats_out["subthemes"].items()}
        )
        sub_cnt_map = result["subtheme"].map(
            {s: d["count"] for s, d in subtheme_stats_out["subthemes"].items()}
        )
        loo_sub_sum = sub_sum_map - training_target.values
        loo_sub_cnt = sub_cnt_map - 1
        result["subtheme_loo"] = np.where(
            loo_sub_cnt.notna() & (loo_sub_cnt > 0),
            loo_sub_sum / loo_sub_cnt,
            gm,
        )

        result["sub_size"] = sub_cnt_map.fillna(0)

        subtheme_stats = subtheme_stats_out
    elif subtheme_stats is not None:
        gm = subtheme_stats["global_mean"]
        for idx in result.index:
            s = result.loc[idx, "subtheme"]
            s_info = subtheme_stats["subthemes"].get(s)
            if s_info:
                result.loc[idx, "subtheme_loo"] = s_info["sum"] / s_info["count"]
                result.loc[idx, "sub_size"] = s_info["count"]
            else:
                result.loc[idx, "subtheme_loo"] = gm
                result.loc[idx, "sub_size"] = 0

    return result, theme_stats, subtheme_stats


def _engineer_keepa_features(
    df: pd.DataFrame,
    keepa_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add Tier 2 Keepa timeline features to the DataFrame."""
    result = df.copy()
    keepa_feats: dict[str, dict] = {}

    # Pre-build RRP lookup to avoid O(N*M) DataFrame scans
    rrp_lookup = dict(zip(result["set_number"], pd.to_numeric(result["rrp_usd_cents"], errors="coerce").fillna(0)))

    for _, kr in keepa_df.iterrows():
        sn = kr["set_number"]
        amz_raw = kr["amazon_price_json"]
        amz = json.loads(amz_raw) if isinstance(amz_raw, str) else amz_raw
        if not isinstance(amz, list) or len(amz) < 5:
            continue

        prices: list[float] = []
        oos_date: str | None = None
        last_p: float | None = None

        for point in amz:
            if point[1] is not None and point[1] > 0:
                prices.append(float(point[1]))
                last_p = float(point[1])
            elif point[1] is None and last_p is not None and oos_date is None:
                oos_date = point[0]

        if not prices:
            continue

        set_rrp = rrp_lookup.get(sn, 0)
        if set_rrp <= 0:
            continue

        rec: dict[str, float] = {
            "kp_price_cv": float(np.std(prices) / np.mean(prices)) if np.mean(prices) > 0 else 0,
            "kp_below_rrp_pct": sum(1 for p in prices if p < set_rrp * 0.98) / len(prices) * 100,
            "kp_avg_discount": (set_rrp - np.mean(prices)) / set_rrp * 100,
            "kp_max_discount": (set_rrp - min(prices)) / set_rrp * 100,
        }

        if len(prices) >= 6:
            early = np.mean(prices[:3])
            late = np.mean(prices[-3:])
            rec["kp_price_trend"] = (late - early) / early * 100 if early > 0 else 0

        if oos_date:
            try:
                d1 = pd.to_datetime(amz[0][0])
                d2 = pd.to_datetime(oos_date)
                rec["kp_months_stock"] = (d2 - d1).days / 30
            except (ValueError, TypeError):
                pass

            bb_raw = kr.get("buy_box_json")
            bb = json.loads(bb_raw) if isinstance(bb_raw, str) else (bb_raw or [])
            if isinstance(bb, list):
                for point in bb:
                    if (len(point) >= 2 and point[0] >= oos_date
                            and point[1] and point[1] > 0):
                        rec["kp_bb_premium"] = (point[1] - set_rrp) / set_rrp * 100
                        break

        keepa_feats[sn] = rec

    for feat in ("kp_below_rrp_pct", "kp_avg_discount", "kp_max_discount",
                 "kp_price_trend", "kp_price_cv", "kp_months_stock", "kp_bb_premium"):
        result[feat] = result["set_number"].map(
            lambda sn, f=feat: keepa_feats.get(sn, {}).get(f, np.nan)
        )

    return result


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def _build_model() -> GradientBoostingRegressor:
    return GradientBoostingRegressor(
        n_estimators=250,
        max_depth=4,
        min_samples_leaf=6,
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
    df_raw = _load_training_data(conn)
    keepa_df = _load_keepa_timelines(conn)

    y = df_raw["annual_growth_pct"].values.astype(float)

    # Tier 1: intrinsics
    df_feat, theme_stats, subtheme_stats = _engineer_intrinsic_features(
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
    df_kp = _engineer_keepa_features(df_feat, keepa_df)
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


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def predict_growth(
    conn: DuckDBPyConnection,
    tier1: TrainedGrowthModel,
    tier2: TrainedGrowthModel | None,
    theme_stats: dict,
    subtheme_stats: dict,
    *,
    only_retiring: bool = False,
) -> list[GrowthPrediction]:
    """Generate growth predictions for candidate sets.

    Uses Tier 2 (with Keepa features) when available, falls back to Tier 1.
    """
    candidates = _load_candidate_sets(conn)
    if only_retiring:
        candidates = candidates[candidates["retiring_soon"] == True]  # noqa: E712

    if candidates.empty:
        return []

    keepa_df = _load_keepa_timelines(conn)

    # Engineer features using pre-computed stats (no LOO leakage)
    df_feat, _, _ = _engineer_intrinsic_features(
        candidates,
        theme_stats=theme_stats,
        subtheme_stats=subtheme_stats,
    )
    df_feat = _engineer_keepa_features(df_feat, keepa_df)

    # Split into tier 2 (has Keepa) and tier 1 (rest)
    has_kp = df_feat["kp_bb_premium"].notna() | df_feat["kp_below_rrp_pct"].notna()
    use_tier2 = tier2 is not None and has_kp.any()

    predictions: list[GrowthPrediction] = []

    for tier_mask, model_obj in [
        (has_kp if use_tier2 else pd.Series(False, index=df_feat.index), tier2),
        (~has_kp if use_tier2 else pd.Series(True, index=df_feat.index), tier1),
    ]:
        if model_obj is None or tier_mask.sum() == 0:
            continue

        df_batch = df_feat[tier_mask].copy()
        fill_map = dict(model_obj.fill_values)

        # Build feature matrix and fill with training medians
        X_batch = df_batch[list(model_obj.feature_names)].copy()
        for c in X_batch.columns:
            X_batch[c] = pd.to_numeric(X_batch[c], errors="coerce")

        # Count missing per row BEFORE filling (for confidence)
        n_missing_per_row = X_batch.isna().sum(axis=1)

        # Fill with stored training medians
        for f in model_obj.feature_names:
            X_batch[f] = X_batch[f].fillna(fill_map.get(f, 0))

        X_scaled = model_obj.scaler.transform(X_batch)
        preds = model_obj.model.predict(X_scaled)

        # Global feature importances (same for all predictions in this tier)
        importances = model_obj.model.feature_importances_
        top_global = tuple(sorted(
            zip(model_obj.feature_names, importances),
            key=lambda x: x[1],
            reverse=True,
        )[:5])

        for i, (orig_idx, row) in enumerate(df_batch.iterrows()):
            n_feat = len(model_obj.feature_names)
            coverage = 1 - (n_missing_per_row.iloc[i] / n_feat) if n_feat > 0 else 0

            if model_obj.tier == 2 and coverage > 0.8:
                confidence = "high"
            elif coverage > 0.7:
                confidence = "moderate"
            else:
                confidence = "low"

            predictions.append(GrowthPrediction(
                set_number=row["set_number"],
                title=str(row.get("title", "")),
                theme=str(row.get("theme", "")),
                predicted_growth_pct=round(float(preds[i]), 1),
                confidence=confidence,
                tier=model_obj.tier,
                feature_contributions=top_global,
            ))

    return sorted(predictions, key=lambda p: p.predicted_growth_pct, reverse=True)


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------


def run_pipeline(conn: DuckDBPyConnection, *, only_retiring: bool = False) -> list[GrowthPrediction]:
    """Train models and generate predictions in one call."""
    tier1, tier2, theme_stats, subtheme_stats = train_growth_models(conn)
    return predict_growth(
        conn, tier1, tier2, theme_stats, subtheme_stats,
        only_retiring=only_retiring,
    )
