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
_warmup_stage: str = "idle"  # idle | loading_models | scoring | ready | failed


class GrowthScoringProvider:
    """Scoring provider backed by the growth model + classifier."""

    @property
    def name(self) -> str:
        return "ml_growth"

    @property
    def prefix(self) -> str:
        return "ml_"

    def score_all(self, conn: Any = None) -> dict[str, dict]:
        """Score all sets with growth predictions. Cached for 30 days."""
        import time

        now = time.time()
        if _prediction_cache.get("expires", 0) > now:
            return _prediction_cache["data"]

        from services.ml.growth.prediction import predict_growth

        try:
            tier1, tier2, ts, ss, clf, ensemble, gb_clf = self._get_models()

            from db.pg.engine import get_engine
            engine = get_engine()

            candidates, keepa_df, gt_df = self._load_candidate_data(engine)

            predictions = predict_growth(
                candidates, keepa_df,
                tier1, tier2, ts, ss,
                classifier=clf, ensemble=ensemble,
                great_buy_classifier=gb_clf,
                gt_df=gt_df,
            )
        except Exception:
            logger.warning("Growth model failed", exc_info=True)
            return {}

        result: dict[str, dict] = {}
        for p in predictions:
            ap = p.avoid_probability
            is_avoid = p.buy_category == "WORST"
            is_buy = p.buy_category in ("GREAT", "GOOD")

            entry: dict = {
                "growth_pct": p.predicted_growth_pct,
                "confidence": p.confidence,
                "buy_signal": is_buy,
                "avoid": is_avoid,
                "buy_category": p.buy_category,
            }
            if ap is not None:
                entry["avoid_probability"] = round(ap, 3)
            if p.great_buy_probability is not None:
                entry["great_buy_probability"] = round(p.great_buy_probability, 3)
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

        # Auto-persist snapshot for time series tracking
        try:
            from db.connection import get_connection
            from services.ml.prediction_tracker import save_scored_snapshot

            snap_conn = get_connection()
            try:
                save_scored_snapshot(snap_conn, result)
            finally:
                snap_conn.close()
        except Exception:
            logger.debug("Auto-snapshot failed (non-critical)", exc_info=True)

        return result

    def predict_single(self, set_number: str) -> dict | None:
        """Force prediction for a single set and inject into cache."""
        from services.ml.growth.prediction import predict_growth

        try:
            tier1, tier2, ts, ss, clf, ensemble, gb_clf = self._get_models()

            from db.pg.engine import get_engine
            engine = get_engine()

            all_candidates, keepa_df, gt_df = self._load_candidate_data(engine)
            candidate = all_candidates[all_candidates["set_number"] == set_number]

            if candidate.empty:
                from services.ml.pg_queries import load_base_metadata
                candidate = load_base_metadata(engine, [set_number])

            if candidate.empty:
                return None

            predictions = predict_growth(
                candidate, keepa_df,
                tier1, tier2, ts, ss,
                classifier=clf, ensemble=ensemble,
                great_buy_classifier=gb_clf,
                gt_df=gt_df,
            )
        except Exception:
            logger.warning("predict_single failed for %s", set_number, exc_info=True)
            return None

        if not predictions:
            return None

        p = predictions[0]
        ap = p.avoid_probability
        is_avoid = p.buy_category == "WORST"
        is_buy = p.buy_category in ("GREAT", "GOOD")

        entry: dict = {
            "growth_pct": p.predicted_growth_pct,
            "confidence": p.confidence,
            "buy_signal": is_buy,
            "avoid": is_avoid,
            "buy_category": p.buy_category,
        }
        if ap is not None:
            entry["avoid_probability"] = round(ap, 3)
        if p.great_buy_probability is not None:
            entry["great_buy_probability"] = round(p.great_buy_probability, 3)
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
        """Force retrain using the active model from registry."""
        from config.model_registry import ACTIVE_MODEL
        from db.pg.engine import get_engine
        from services.ml.growth.persistence import save_growth_models

        _cache.clear()
        _prediction_cache.clear()

        engine = get_engine()

        gb_clf = None
        if ACTIVE_MODEL == "keepa_bl":
            from services.ml.growth.keepa_training import train_keepa_bl_models
            from services.ml.pg_queries import load_google_trends_data, load_keepa_bl_training_data

            base_df, keepa_df, target_series = load_keepa_bl_training_data(engine)
            gt_df = load_google_trends_data(engine)
            tier1, tier2, ts, ss, clf, ensemble, gb_clf = train_keepa_bl_models(
                base_df=base_df, keepa_df=keepa_df, target_series=target_series,
                gt_df=gt_df,
            )
        else:
            from services.ml.growth.training import train_growth_models
            from services.ml.pg_queries import load_growth_training_data, load_keepa_timelines

            df_raw = load_growth_training_data(engine)
            keepa_df = load_keepa_timelines(engine)
            tier1, tier2, ts, ss, clf, ensemble = train_growth_models(
                df_raw=df_raw, keepa_df=keepa_df,
            )

        save_growth_models(tier1, tier2, ts, ss, clf, ensemble,
                           great_buy_classifier=gb_clf)

        _cache["tier1"] = tier1
        _cache["tier2"] = tier2
        _cache["classifier"] = clf
        _cache["ensemble"] = ensemble
        _cache["great_buy_classifier"] = gb_clf
        _cache["theme_stats"] = ts
        _cache["subtheme_stats"] = ss

        result: dict[str, object] = {}
        if tier1 is not None:
            result["n_train"] = tier1.n_train
            result["regressor_cv_r2"] = round(tier1.cv_r2_mean or 0, 3)
            result["regressor_features"] = len(tier1.feature_names)
        else:
            result["architecture"] = "classifier-only"
        if clf:
            result["classifier_auc"] = round(clf.cv_auc, 3)
            result["classifier_recall"] = round(clf.cv_recall, 3)
            result["n_avoid"] = clf.n_avoid
        if gb_clf:
            result["great_buy_auc"] = round(gb_clf.cv_auc, 3)
            result["great_buy_recall"] = round(gb_clf.cv_recall, 3)
        return result

    def warm_cache(self) -> None:
        """Eagerly load models and pre-compute predictions."""
        global _warmup_stage
        _warmup_stage = "loading_models"
        try:
            self._get_models()
        except Exception:
            _warmup_stage = "failed"
            raise
        _warmup_stage = "scoring"
        # Pre-fill prediction cache so first request is instant
        try:
            self.score_all()
            _warmup_stage = "ready"
            logger.info("Prediction cache warmed (%d sets)", len(_prediction_cache.get("data", {})))
        except Exception:
            _warmup_stage = "failed"
            logger.warning("Prediction cache warmup failed", exc_info=True)

    def _load_candidate_data(self, engine: Any) -> tuple:
        """Load candidate sets + Keepa + GT data, routing by active model type."""
        from services.ml.growth.prediction import _is_keepa_bl_model
        from services.ml.pg_queries import load_google_trends_data

        gt_df = load_google_trends_data(engine)

        tier1 = _cache.get("tier1")
        model_type = _cache.get("model_type")

        # Classifier-only (tier1=None) or keepa_bl model
        if model_type == "keepa_bl" or (tier1 and _is_keepa_bl_model(tier1)):
            from services.ml.pg_queries import load_keepa_bl_training_data
            base_df, keepa_df, _ = load_keepa_bl_training_data(engine)
            return base_df, keepa_df, gt_df

        from services.ml.pg_queries import load_growth_candidate_sets, load_keepa_timelines
        return load_growth_candidate_sets(engine), load_keepa_timelines(engine), gt_df

    def _get_models(self) -> tuple:
        if not _cache:
            with _cache_lock:
                if not _cache:
                    from services.ml.growth.persistence import load_growth_models

                    loaded = load_growth_models(max_age_hours=0)
                    if loaded is not None:
                        tier1, tier2, ts, ss, clf, ensemble, gb_clf = loaded
                        logger.info("Growth models loaded from disk")
                    else:
                        raise RuntimeError(
                            "No pre-trained growth models found. Run ./train first."
                        )

                    from config.model_registry import ACTIVE_MODEL
                    _cache["tier1"] = tier1
                    _cache["tier2"] = tier2
                    _cache["classifier"] = clf
                    _cache["ensemble"] = ensemble
                    _cache["great_buy_classifier"] = gb_clf
                    _cache["theme_stats"] = ts
                    _cache["subtheme_stats"] = ss
                    _cache["model_type"] = ACTIVE_MODEL

        return (
            _cache["tier1"],
            _cache["tier2"],
            _cache["theme_stats"],
            _cache["subtheme_stats"],
            _cache.get("classifier"),
            _cache.get("ensemble"),
            _cache.get("great_buy_classifier"),
        )


# Singleton
growth_provider = GrowthScoringProvider()
