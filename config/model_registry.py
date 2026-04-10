"""Model registry -- select which growth model to use.

Change ACTIVE_MODEL to switch between models without code changes.
"""

from __future__ import annotations

# Available models:
#   "legacy_be"  -- Original T1 model trained on BE annual_growth_pct
#   "keepa_bl"   -- Exp 31 model trained on BL current price / RRP
ACTIVE_MODEL: str = "keepa_bl"

# Model artifact filenames
MODEL_FILENAMES: dict[str, str] = {
    "legacy_be": "growth_models.joblib",
    "keepa_bl": "growth_models_keepa_bl.joblib",
}


def get_model_filename() -> str:
    return MODEL_FILENAMES[ACTIVE_MODEL]
