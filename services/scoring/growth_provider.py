"""Growth prediction scoring provider.

Wraps the ML models (regressor + classifier) as a pluggable ScoringProvider.
Pre-trained models are loaded from disk. Data is fetched from PostgreSQL.

The score_all() method accepts a database conn for protocol compatibility
and uses PostgreSQL internally for candidate data.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.ml.growth.classifier import TrainedClassifier
    from services.ml.growth.types import GrowthPrediction, TrainedGrowthModel

logger = logging.getLogger(__name__)

import time

_cache: dict = {}
_cache_lock = threading.Lock()
_prediction_cache: dict = {}  # cached score_all results
_PREDICTION_TTL = 6 * 3600  # 6 hours — retrain cadence, not dataset cadence
_warmup_stage: str = "idle"  # idle | loading_models | scoring | ready | failed
_progress_lock = threading.Lock()
_progress: dict = {}  # {total: int, scored: int, start_time: float}
_scoring_lock = threading.Lock()
_scoring_event = threading.Event()
_scoring_event.set()  # Start as "not scoring"

# Entry-price gates per buy category. If the current trailing-6m sold price
# (in USD, from bricklink_monthly_sales) already exceeds this multiple of
# RRP, the market has priced in the upside — buying today eats the alpha.
# GREAT allows slightly over RRP because the target already bakes in a
# ≥20% annualized move; GOOD is stricter because a ~15% APR target has
# less room to absorb entry slippage.
_ENTRY_PRICE_MAX_RATIO: dict[str, float] = {
    "GREAT": 1.05,
    "GOOD": 1.00,
}


def _build_entry(
    p: "GrowthPrediction",
    model_version: str | None,
    market_prices: dict[str, tuple[float, float]] | None = None,
    keepa_set_numbers: set[str] | None = None,
) -> dict:
    """Build the provider-shape dict from a GrowthPrediction.

    Populates every field the snapshot table cares about. Classifier-only
    paths leave `growth_pct` at 0.0 as a sentinel; downstream consumers
    should read `buy_category` + probabilities, not `growth_pct`.

    Gate: the keepa_bl model is trained on Keepa price history AND
    BrickLink sold-price rows, so a set missing either input gets its
    category demoted to NONE. The model can still emit a probability from
    zero-sentinel features, but that probability is blind to the
    strongest trained signals and shouldn't drive buy decisions.
    """
    # Coverage gate first — NONE overrides whatever the classifier said.
    has_keepa = keepa_set_numbers is None or p.set_number in keepa_set_numbers
    has_bl = market_prices is not None and p.set_number in market_prices
    gated_category: str | None = p.buy_category
    gated_confidence = p.confidence
    if not (has_keepa and has_bl):
        gated_category = "NONE"
        gated_confidence = "none"

    ap = p.avoid_probability
    is_avoid = gated_category == "WORST"
    # OOF walk-forward (2026-04-15) showed GOOD hits the 10% hurdle only
    # 52% of the time out-of-fold — a coin flip. GREAT is the only
    # bucket with reliable signal, so buy_signal surfaces GREAT only.
    # GOOD stays as a category label for the UI watchlist but does not
    # trigger buy_signal / cart inclusion.
    is_buy = gated_category == "GREAT"

    entry: dict = {
        "growth_pct": p.predicted_growth_pct,
        "confidence": gated_confidence,
        "tier": p.tier,
        "buy_signal": is_buy,
        "avoid": is_avoid,
        "buy_category": gated_category,
        "model_version": model_version,
        "has_keepa_data": has_keepa,
        "has_bl_data": has_bl,
    }
    if ap is not None:
        entry["avoid_probability"] = round(ap, 3)
    if p.great_buy_probability is not None:
        entry["great_buy_probability"] = round(p.great_buy_probability, 3)
    if p.good_buy_probability is not None:
        entry["good_buy_probability"] = round(p.good_buy_probability, 3)
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

    # Entry-price filter (execution layer, not classifier).
    #
    # The classifier says "this set's effective APR will be great/good"
    # but it says nothing about whether the market has ALREADY priced it
    # in. Buying a 30% APR set at 1.3x RRP leaves you near zero alpha.
    #
    # Missing price data → entry_price_ok = None, caller decides whether
    # to treat unknown as buyable or not.
    if market_prices is not None:
        price_entry = market_prices.get(p.set_number)
        if price_entry is not None:
            current_usd, rrp_usd = price_entry
            if rrp_usd > 0:
                ratio = current_usd / rrp_usd
                entry["price_vs_rrp_ratio"] = round(ratio, 3)
                entry["current_price_usd_cents"] = int(current_usd)
                if gated_category == "NONE":
                    entry["entry_price_ok"] = None
                    entry["recommended_action"] = "NONE"
                else:
                    gate = _ENTRY_PRICE_MAX_RATIO.get(gated_category or "")
                    if gate is not None:
                        entry["entry_price_ok"] = ratio <= gate
                        entry["recommended_action"] = "BUY" if ratio <= gate else "WAIT"
                    elif gated_category == "WORST":
                        entry["entry_price_ok"] = False
                        entry["recommended_action"] = "SKIP"
                    else:
                        entry["entry_price_ok"] = None
                        entry["recommended_action"] = "HOLD"

    return entry


class GrowthScoringProvider:
    """Scoring provider backed by the growth model + classifier."""

    @property
    def name(self) -> str:
        return "ml_growth"

    @property
    def prefix(self) -> str:
        return "ml_"

    def score_all(self, conn: Any = None) -> dict[str, dict]:
        """Score all sets with growth predictions.

        Cache is valid until either (a) `_PREDICTION_TTL` elapses, or
        (b) the on-disk model file mtime advances past the cached value
        — whichever comes first. Mtime check ensures a retrain blows
        the cache instantly so the next request sees the new model.

        Only one scoring run at a time; concurrent requests wait or return
        previous cache to avoid duplicate work.
        """
        from services.ml.growth.prediction import LIVE_GREAT_BUY_THRESHOLD

        now = time.time()
        ttl_ok = _prediction_cache.get("expires", 0) > now
        if ttl_ok:
            cached_mtime = _prediction_cache.get("model_mtime")
            cached_override = _prediction_cache.get("great_threshold_override")
            current_mtime = self._current_model_mtime()
            if (
                cached_mtime == current_mtime
                and cached_override == LIVE_GREAT_BUY_THRESHOLD
            ):
                return _prediction_cache["data"]
            logger.info(
                "Prediction cache invalidated: mtime %s->%s, live_great_thr %s->%s",
                cached_mtime, current_mtime,
                cached_override, LIVE_GREAT_BUY_THRESHOLD,
            )

        # Try to acquire lock; if another thread is scoring, wait or return cache
        if not _scoring_lock.acquire(blocking=False):
            # Another thread is already scoring — wait for it to finish, then
            # return whatever it produced. If the winner produced an empty
            # result (or didn't write at all), fall through and retry instead
            # of handing callers an empty dict that downstream treats as a
            # failed prediction run.
            logger.debug("Scoring already in progress, waiting for completion...")
            _scoring_event.wait(timeout=600)
            cached = _prediction_cache.get("data") or {}
            if cached:
                return cached
            logger.warning(
                "score_all: waited on concurrent run but cache is empty; retrying"
            )
            _scoring_lock.acquire(blocking=True, timeout=600)

        try:
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

            model_version = self._model_version(clf, gb_clf, tier1)

            # Load current market prices once for the entry-price filter.
            # A missing table or empty result just skips the annotation —
            # scoring must keep working even if BL sales data is thin.
            try:
                from services.ml.pg_queries import load_current_market_prices
                market_prices = load_current_market_prices(engine)
            except Exception:
                logger.warning("Entry-price filter: price load failed", exc_info=True)
                market_prices = {}

            # Ground truth for "has Keepa data" — any set_number with a row
            # in keepa_snapshots is considered covered. Sets missing from
            # this set are gated to buy_category=NONE in _build_entry.
            try:
                keepa_set_numbers: set[str] = set(
                    keepa_df["set_number"].astype(str).tolist()
                ) if not keepa_df.empty else set()
            except Exception:
                logger.warning("Keepa coverage set build failed", exc_info=True)
                keepa_set_numbers = set()

            # Initialize progress tracking only if there are sets to score
            total_sets = len(predictions)
            if total_sets > 0:
                start_time = time.time()
                with _progress_lock:
                    _progress.update({
                        "total": total_sets,
                        "scored": 0,
                        "start_time": start_time,
                    })

            try:
                result: dict[str, dict] = {}
                for idx, p in enumerate(predictions, start=1):
                    result[p.set_number] = _build_entry(
                        p, model_version,
                        market_prices=market_prices,
                        keepa_set_numbers=keepa_set_numbers,
                    )
                    # Batch progress updates every 50 sets to reduce lock contention
                    if total_sets > 0 and (idx % 50 == 0 or idx == total_sets):
                        with _progress_lock:
                            _progress["scored"] = idx
            finally:
                # Always clear progress, even if an exception occurred
                with _progress_lock:
                    _progress.clear()

            # Never cache an empty result — it would stick for _PREDICTION_TTL
            # (6h) and every subsequent caller would skip scoring entirely.
            # An empty result is always a failure mode (transient DB race,
            # missing feature rows, etc.); let the next call retry.
            if not result:
                logger.warning(
                    "score_all produced 0 predictions (candidates=%d); "
                    "refusing to cache empty result",
                    len(predictions),
                )
                return result

            _prediction_cache["data"] = result
            _prediction_cache["expires"] = now + _PREDICTION_TTL
            _prediction_cache["model_mtime"] = self._current_model_mtime()
            _prediction_cache["great_threshold_override"] = LIVE_GREAT_BUY_THRESHOLD

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
                logger.error("Auto-snapshot persist failed", exc_info=True)

            return result
        finally:
            _scoring_event.set()
            _scoring_lock.release()

    def get_progress(self) -> dict:
        """Return current prediction progress or {is_running: false} if not running."""
        with _progress_lock:
            if not _progress or _progress.get("total", 0) == 0:
                return {"is_running": False}

            total = _progress.get("total", 0)
            scored = _progress.get("scored", 0)
            start_time = _progress.get("start_time", 0)

            elapsed = time.time() - start_time
            percentage = (scored / total * 100) if total > 0 else 0

            # Estimate ETA: (total - scored) / (scored / elapsed)
            eta_seconds = 0
            if scored > 0 and elapsed > 0:
                rate = scored / elapsed
                remaining = total - scored
                eta_seconds = int(remaining / rate) if rate > 0 else 0

            return {
                "is_running": True,
                "total": total,
                "scored": scored,
                "percentage": round(percentage, 1),
                "eta_seconds": eta_seconds,
            }

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

        # Entry-price annotation for the single set (cheap lookup: one row
        # from the trailing-6m weighted-avg view).
        try:
            from services.ml.pg_queries import load_current_market_prices
            market_prices = load_current_market_prices(engine)
        except Exception:
            market_prices = {}

        try:
            keepa_set_numbers: set[str] = set(
                keepa_df["set_number"].astype(str).tolist()
            ) if not keepa_df.empty else set()
        except Exception:
            keepa_set_numbers = set()

        entry = _build_entry(
            predictions[0],
            self._model_version(clf, gb_clf, tier1),
            market_prices=market_prices,
            keepa_set_numbers=keepa_set_numbers,
        )

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
        # Re-load if cache empty OR on-disk model file has been refreshed
        # (e.g. an external retrain process). The mtime check avoids
        # serving stale models after a /retrain endpoint or scripted retrain.
        current_mtime = self._current_model_mtime()
        cached_mtime = _cache.get("model_mtime")
        if not _cache or cached_mtime != current_mtime:
            with _cache_lock:
                # Re-check inside lock to avoid duplicate loads.
                cached_mtime = _cache.get("model_mtime")
                if not _cache or cached_mtime != current_mtime:
                    from services.ml.growth.persistence import load_growth_models

                    loaded = load_growth_models(max_age_hours=0)
                    if loaded is not None:
                        tier1, tier2, ts, ss, clf, ensemble, gb_clf = loaded
                        logger.info(
                            "Growth models loaded from disk (mtime=%s)",
                            current_mtime,
                        )
                    else:
                        raise RuntimeError(
                            "No pre-trained growth models found. Run ./train first."
                        )

                    from config.model_registry import ACTIVE_MODEL
                    _cache.clear()
                    _cache["tier1"] = tier1
                    _cache["tier2"] = tier2
                    _cache["classifier"] = clf
                    _cache["ensemble"] = ensemble
                    _cache["great_buy_classifier"] = gb_clf
                    _cache["theme_stats"] = ts
                    _cache["subtheme_stats"] = ss
                    _cache["model_type"] = ACTIVE_MODEL
                    _cache["model_mtime"] = current_mtime
                    _prediction_cache.clear()

        return (
            _cache["tier1"],
            _cache["tier2"],
            _cache["theme_stats"],
            _cache["subtheme_stats"],
            _cache.get("classifier"),
            _cache.get("ensemble"),
            _cache.get("great_buy_classifier"),
        )

    @staticmethod
    def _current_model_mtime() -> float | None:
        """Return mtime of the active model artifact, or None if missing."""
        try:
            from services.ml.growth.persistence import _artifact_path
            path = _artifact_path()
            return path.stat().st_mtime if path.exists() else None
        except Exception:
            return None

    def _model_version(
        self,
        clf: "TrainedClassifier | None",
        gb_clf: "TrainedClassifier | None",
        tier1: "TrainedGrowthModel | None",
    ) -> str:
        """Human-readable model version derived from whatever heads are active.

        Classifier-only: kbl_clf<N>_gb<N>_<trained_at_date>
        With regressor:  gbm_t1n<N>_<trained_at_date>
        """
        from config.model_registry import ACTIVE_MODEL

        if tier1 is not None:
            stamp = (tier1.trained_at or "")[:10]
            return f"gbm_t1n{tier1.n_train}_{stamp}".rstrip("_")

        clf_n = clf.n_train if clf else 0
        gb_n = gb_clf.n_train if gb_clf else 0
        stamp = (clf.trained_at if clf else "")[:10]
        prefix = "kbl" if ACTIVE_MODEL == "keepa_bl" else "clf"
        return f"{prefix}_clf{clf_n}_gb{gb_n}_{stamp}".rstrip("_")


# Singleton
growth_provider = GrowthScoringProvider()
