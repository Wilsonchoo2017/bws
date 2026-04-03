"""Growth prediction scoring provider.

Wraps the ML growth model (services.ml.growth_model) as a pluggable
ScoringProvider. Models are trained on first call and cached.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)

# Module-level cache for trained models
_cache: dict = {}


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
            tier1, tier2, ts, ss = self._get_models(conn)
            predictions = predict_growth(conn, tier1, tier2, ts, ss)
        except Exception:
            logger.warning("Growth model failed", exc_info=True)
            return {}

        return {
            p.set_number: {
                "growth_pct": p.predicted_growth_pct,
                "confidence": p.confidence,
                "tier": p.tier,
            }
            for p in predictions
        }

    def retrain(self, conn: DuckDBPyConnection) -> dict:
        """Force retrain and return model stats."""
        _cache.clear()
        tier1, tier2, _, _ = self._get_models(conn)
        result = {
            "tier1_n_train": tier1.n_train,
            "tier1_r2": round(tier1.train_r2, 3),
            "tier1_features": len(tier1.feature_names),
        }
        if tier2:
            result["tier2_n_train"] = tier2.n_train
            result["tier2_r2"] = round(tier2.train_r2, 3)
            result["tier2_features"] = len(tier2.feature_names)
        return result

    def _get_models(self, conn: DuckDBPyConnection) -> tuple:
        if not _cache:
            from services.ml.growth_model import train_growth_models

            tier1, tier2, ts, ss = train_growth_models(conn)
            _cache["tier1"] = tier1
            _cache["tier2"] = tier2
            _cache["theme_stats"] = ts
            _cache["subtheme_stats"] = ss
            logger.info("Growth models trained and cached")

        return (
            _cache["tier1"],
            _cache["tier2"],
            _cache["theme_stats"],
            _cache["subtheme_stats"],
        )


# Singleton instance
growth_provider = GrowthScoringProvider()
