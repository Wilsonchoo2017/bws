"""Platform-agnostic marketplace competition scoring.

Shared primitives for scoring "how saturated is a set's MY market" on
any marketplace (Shopee, Carousell, FB). The scorer takes raw numeric
inputs (listings_count, unique_sellers, prices_cents) and returns a
0-100 composite, parameterized by per-platform caps.

This module replaces the per-platform duplication that would otherwise
grow as more marketplaces are added. It owns the scoring math; each
platform adapter owns how to pull those inputs out of its scraper.
"""

from services.marketplace_competition.scorer import (
    ScoringCaps,
    SHOPEE_CAPS,
    CAROUSELL_CAPS,
    compute_composite_score,
    compute_price_stats,
)
from services.marketplace_competition.types import MarketplaceListing, SaturationLevel

__all__ = [
    "CAROUSELL_CAPS",
    "MarketplaceListing",
    "SHOPEE_CAPS",
    "SaturationLevel",
    "ScoringCaps",
    "compute_composite_score",
    "compute_price_stats",
]
