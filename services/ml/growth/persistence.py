"""Persist and load trained growth models to/from disk.

Saves the full model bundle (tier1, tier2, classifier, ensemble,
theme/subtheme stats) as a single joblib file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_MODELS_DIR = _PROJECT_ROOT / "models"
_GROWTH_FILENAME = "growth_models.joblib"


def _artifact_path() -> Path:
    return _MODELS_DIR / _GROWTH_FILENAME


def save_growth_models(
    tier1: Any,
    tier2: Any | None,
    theme_stats: dict,
    subtheme_stats: dict,
    classifier: Any | None,
    ensemble: Any | None,
) -> Path:
    """Serialize the full growth model bundle to disk."""
    import joblib

    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = _artifact_path()

    bundle = {
        "tier1": tier1,
        "tier2": tier2,
        "theme_stats": theme_stats,
        "subtheme_stats": subtheme_stats,
        "classifier": classifier,
        "ensemble": ensemble,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "version": 2,  # v2 = hurdle model
    }
    joblib.dump(bundle, path, compress=3)
    logger.info("Growth models saved to %s", path)
    return path


def load_growth_models(
    max_age_hours: float = 168,
) -> tuple[Any, Any | None, dict, dict, Any | None, Any | None] | None:
    """Load growth models from disk.

    Returns (tier1, tier2, theme_stats, subtheme_stats, classifier, ensemble)
    or None if no valid artifact exists.
    """
    import joblib

    path = _artifact_path()
    if not path.exists():
        logger.info("No saved growth models at %s", path)
        return None

    try:
        bundle = joblib.load(path)
    except Exception:
        logger.warning("Failed to load growth models from %s", path, exc_info=True)
        return None

    saved_at = bundle.get("saved_at")
    if saved_at and max_age_hours > 0:
        saved_dt = datetime.fromisoformat(saved_at)
        now = datetime.now(timezone.utc)
        if saved_dt.tzinfo is None:
            saved_dt = saved_dt.replace(tzinfo=timezone.utc)
        age_hours = (now - saved_dt).total_seconds() / 3600
        if age_hours > max_age_hours:
            logger.info(
                "Growth models are %.1f hours old (max %.0f), need retrain",
                age_hours, max_age_hours,
            )
            return None
        logger.info("Loaded growth models (%.1f hours old)", age_hours)
    else:
        logger.info("Loaded growth models from disk")

    # v2 (hurdle): classifier field. v1: tier3 field (legacy).
    classifier = bundle.get("classifier")
    if classifier is None:
        # Legacy v1 bundle — classifier not available
        classifier = bundle.get("tier3")  # won't be a classifier, but avoids KeyError
        classifier = None  # force None for v1

    return (
        bundle["tier1"],
        bundle.get("tier2"),
        bundle["theme_stats"],
        bundle["subtheme_stats"],
        classifier,
        bundle.get("ensemble"),
    )
