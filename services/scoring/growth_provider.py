"""Growth prediction scoring provider.

Wraps the ML growth model (services.ml.growth_model) as a pluggable
ScoringProvider. Models are trained on first call and cached.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# Module-level cache for trained models
_cache: dict = {}
_cache_lock = threading.Lock()


class GrowthScoringProvider:
    """Scoring provider backed by the tiered GBM growth model."""

    @property
    def name(self) -> str:
        return "ml_growth"

    @property
    def prefix(self) -> str:
        return "ml_"

    def score_all(self, conn: DuckDBPyConnection) -> dict[str, dict]:
        """Train (if needed) and score all sets with growth predictions."""
        from services.ml.growth_model import predict_growth, train_growth_models

        try:
            tier1, tier2, ts, ss, tier3, ensemble = self._get_models(conn)
            predictions = predict_growth(
                conn, tier1, tier2, ts, ss,
                tier3=tier3, ensemble=ensemble,
            )
        except Exception:
            logger.warning("Growth model failed", exc_info=True)
            return {}

        result: dict[str, dict] = {}
        for p in predictions:
            entry: dict = {
                "growth_pct": p.predicted_growth_pct,
                "confidence": p.confidence,
                "tier": p.tier,
            }
            if p.prediction_interval:
                entry["interval_lower"] = p.prediction_interval.lower
                entry["interval_upper"] = p.prediction_interval.upper
            if p.feature_contributions:
                entry["drivers"] = [
                    {"feature": f, "impact": round(float(v), 4)}
                    for f, v in p.feature_contributions[:5]
                ]
            if p.shap_base_value is not None:
                entry["shap_base"] = p.shap_base_value
            result[p.set_number] = entry

        return result

    def retrain(self, conn: DuckDBPyConnection) -> dict:
        """Force retrain and return model stats."""
        _cache.clear()
        tier1, tier2, _, _, tier3, ensemble = self._get_models(conn, force_train=True)
        result = {
            "tier1_n_train": tier1.n_train,
            "tier1_r2": round(tier1.train_r2, 3),
            "tier1_features": len(tier1.feature_names),
        }
        if tier2:
            result["tier2_n_train"] = tier2.n_train
            result["tier2_r2"] = round(tier2.train_r2, 3)
            result["tier2_features"] = len(tier2.feature_names)
        if tier3:
            result["tier3_n_train"] = tier3.n_train
            result["tier3_r2"] = round(tier3.train_r2, 3)
            result["tier3_features"] = len(tier3.feature_names)
        if ensemble:
            result["ensemble_r2"] = round(ensemble.oos_r2, 3)
        return result

    def warm_cache(self, conn: DuckDBPyConnection) -> None:
        """Eagerly load or train models so first score_all() is instant."""
        self._get_models(conn)

    def _get_models(self, conn: DuckDBPyConnection, *, force_train: bool = False) -> tuple:
        if not _cache:
            with _cache_lock:
                if not _cache:  # double-check after acquiring lock
                    from services.ml.growth.persistence import load_growth_models, save_growth_models
                    from services.ml.growth_model import train_growth_models

                    # Try loading pre-trained models from disk first
                    loaded = None if force_train else load_growth_models()

                    if loaded is not None:
                        tier1, tier2, ts, ss, tier3, ensemble = loaded
                        logger.info("Growth models loaded from disk (skipped training)")
                    else:
                        tier1, tier2, ts, ss, tier3, ensemble = train_growth_models(conn)
                        save_growth_models(tier1, tier2, ts, ss, tier3, ensemble)
                        logger.info("Growth models trained and saved to disk")

                    _cache["tier1"] = tier1
                    _cache["tier2"] = tier2
                    _cache["tier3"] = tier3
                    _cache["ensemble"] = ensemble
                    _cache["theme_stats"] = ts
                    _cache["subtheme_stats"] = ss

        return (
            _cache["tier1"],
            _cache["tier2"],
            _cache["theme_stats"],
            _cache["subtheme_stats"],
            _cache.get("tier3"),
            _cache.get("ensemble"),
        )


# Singleton instance
growth_provider = GrowthScoringProvider()
