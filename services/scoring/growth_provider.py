"""Growth prediction scoring provider.

Wraps the ML models (regressor + classifier) as a pluggable ScoringProvider.
Pre-trained models are loaded from disk. Data is fetched from PostgreSQL.

The score_all() method accepts a database conn for protocol compatibility
and uses PostgreSQL internally for candidate data.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_cache: dict = {}
_cache_lock = threading.Lock()
_prediction_cache: dict = {}  # cached score_all results
_PREDICTION_TTL = 30 * 24 * 3600  # 30 days


class GrowthScoringProvider:
    """Scoring provider backed by the growth model + classifier."""

    @property
    def name(self) -> str:
        return "ml_growth"

    @property
    def prefix(self) -> str:
        return "ml_"

    def score_all(self, conn: Any = None) -> dict[str, dict]:
        """Score all sets with growth predictions. Cached for 10 minutes."""
        import time

        now = time.time()
        if _prediction_cache.get("expires", 0) > now:
            return _prediction_cache["data"]

        from services.ml.growth.prediction import predict_growth
        from services.ml.pg_queries import load_growth_candidate_sets, load_keepa_timelines

        try:
            tier1, tier2, ts, ss, clf, ensemble = self._get_models()

            from db.pg.engine import get_engine
            engine = get_engine()
            candidates = load_growth_candidate_sets(engine)
            keepa_df = load_keepa_timelines(engine)

            predictions = predict_growth(
                candidates, keepa_df,
                tier1, tier2, ts, ss,
                classifier=clf, ensemble=ensemble,
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
            if p.avoid_probability is not None:
                entry["avoid_probability"] = round(p.avoid_probability, 3)
            if p.raw_growth_pct is not None:
                entry["raw_growth_pct"] = p.raw_growth_pct
            if p.kelly_fraction is not None:
                entry["kelly_fraction"] = p.kelly_fraction
            if p.win_probability is not None:
                entry["win_probability"] = round(p.win_probability, 3)
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

        _prediction_cache["data"] = result
        _prediction_cache["expires"] = now + _PREDICTION_TTL
        return result

    def predict_single(self, set_number: str) -> dict | None:
        """Force prediction for a single set and inject into cache."""
        from services.ml.growth.prediction import predict_growth
        from services.ml.pg_queries import load_growth_candidate_sets, load_keepa_timelines

        try:
            tier1, tier2, ts, ss, clf, ensemble = self._get_models()

            from db.pg.engine import get_engine
            engine = get_engine()

            # Load candidates filtered to this one set
            all_candidates = load_growth_candidate_sets(engine)
            candidate = all_candidates[all_candidates["set_number"] == set_number]

            if candidate.empty:
                # Try loading base metadata as fallback (looser criteria)
                from services.ml.pg_queries import load_base_metadata
                candidate = load_base_metadata(engine, [set_number])

            if candidate.empty:
                return None

            keepa_df = load_keepa_timelines(engine)

            predictions = predict_growth(
                candidate, keepa_df,
                tier1, tier2, ts, ss,
                classifier=clf, ensemble=ensemble,
            )
        except Exception:
            logger.warning("predict_single failed for %s", set_number, exc_info=True)
            return None

        if not predictions:
            return None

        p = predictions[0]
        entry: dict = {
            "growth_pct": p.predicted_growth_pct,
            "confidence": p.confidence,
            "tier": p.tier,
        }
        if p.avoid_probability is not None:
            entry["avoid_probability"] = round(p.avoid_probability, 3)
        if p.raw_growth_pct is not None:
            entry["raw_growth_pct"] = p.raw_growth_pct
        if p.kelly_fraction is not None:
            entry["kelly_fraction"] = p.kelly_fraction
        if p.win_probability is not None:
            entry["win_probability"] = round(p.win_probability, 3)
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

        # Inject into prediction cache so subsequent GET requests pick it up
        if "data" in _prediction_cache:
            _prediction_cache["data"][set_number] = entry

        return entry

    def retrain(self) -> dict:
        """Force retrain and return model stats."""
        from db.pg.engine import get_engine
        from services.ml.growth.persistence import save_growth_models
        from services.ml.growth.training import train_growth_models
        from services.ml.pg_queries import load_growth_training_data, load_keepa_timelines

        _cache.clear()
        _prediction_cache.clear()

        engine = get_engine()
        df_raw = load_growth_training_data(engine)
        keepa_df = load_keepa_timelines(engine)

        tier1, tier2, ts, ss, clf, ensemble = train_growth_models(
            df_raw=df_raw, keepa_df=keepa_df,
        )
        save_growth_models(tier1, tier2, ts, ss, clf, ensemble)

        _cache["tier1"] = tier1
        _cache["tier2"] = tier2
        _cache["classifier"] = clf
        _cache["ensemble"] = ensemble
        _cache["theme_stats"] = ts
        _cache["subtheme_stats"] = ss

        result = {
            "tier1_n_train": tier1.n_train,
            "tier1_cv_r2": round(tier1.cv_r2_mean or 0, 3),
            "tier1_features": len(tier1.feature_names),
        }
        if tier2:
            result["tier2_n_train"] = tier2.n_train
            result["tier2_cv_r2"] = round(tier2.cv_r2_mean or 0, 3)
        if clf:
            result["classifier_auc"] = round(clf.cv_auc, 3)
            result["classifier_recall"] = round(clf.cv_recall, 3)
            result["n_avoid"] = clf.n_avoid
        if ensemble:
            result["ensemble_r2"] = round(ensemble.oos_r2, 3)
        return result

    def warm_cache(self) -> None:
        """Eagerly load models and pre-compute predictions."""
        self._get_models()
        # Pre-fill prediction cache so first request is instant
        try:
            self.score_all()
            logger.info("Prediction cache warmed (%d sets)", len(_prediction_cache.get("data", {})))
        except Exception:
            logger.warning("Prediction cache warmup failed", exc_info=True)

    def _get_models(self) -> tuple:
        if not _cache:
            with _cache_lock:
                if not _cache:
                    from services.ml.growth.persistence import load_growth_models

                    loaded = load_growth_models(max_age_hours=0)
                    if loaded is not None:
                        tier1, tier2, ts, ss, clf, ensemble = loaded
                        logger.info("Growth models loaded from disk")
                    else:
                        raise RuntimeError(
                            "No pre-trained growth models found. Run ./train first."
                        )

                    _cache["tier1"] = tier1
                    _cache["tier2"] = tier2
                    _cache["classifier"] = clf
                    _cache["ensemble"] = ensemble
                    _cache["theme_stats"] = ts
                    _cache["subtheme_stats"] = ss

        return (
            _cache["tier1"],
            _cache["tier2"],
            _cache["theme_stats"],
            _cache["subtheme_stats"],
            _cache.get("classifier"),
            _cache.get("ensemble"),
        )


# Singleton
growth_provider = GrowthScoringProvider()
