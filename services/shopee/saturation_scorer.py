"""Compute Shopee market saturation score from search results.

Delegates the scoring math and price-stat aggregation to
`services.marketplace_competition` so the same recipe is reused
across Shopee, Carousell, and (eventually) Facebook. This module
owns the Shopee-specific bits: relevance filtering and the bridge
into `ShopeeProduct` / `SaturationSnapshot`.
"""

import re
from datetime import datetime, timezone

from services.marketplace_competition import scorer as _shared_scorer
from services.marketplace_competition.scorer import (
    SHOPEE_CAPS,
    classify,
    compute_composite_score,
    compute_price_stats,
)
from services.marketplace_competition.types import (
    SaturationLevel as MpSaturationLevel,
)
from services.shopee.parser import ShopeeProduct
from services.shopee.repository import _parse_price_cents
from services.shopee.saturation_types import SaturationLevel, SaturationSnapshot

_LEVEL_MAP: dict[MpSaturationLevel, SaturationLevel] = {
    MpSaturationLevel.VERY_LOW: SaturationLevel.VERY_LOW,
    MpSaturationLevel.LOW: SaturationLevel.LOW,
    MpSaturationLevel.MODERATE: SaturationLevel.MODERATE,
    MpSaturationLevel.HIGH: SaturationLevel.HIGH,
}


def _listing_score(count: int) -> float:
    """Backward-compat shim \u2014 delegates to shared scorer with Shopee caps."""
    return _shared_scorer._listing_score(count, SHOPEE_CAPS.listings_cap)


def _seller_score(unique_sellers: int) -> float:
    """Backward-compat shim \u2014 delegates to shared scorer with Shopee caps."""
    return _shared_scorer._seller_score(unique_sellers, SHOPEE_CAPS.sellers_cap)


def _price_competition_score(prices_cents: list[int]) -> float:
    """Backward-compat shim \u2014 delegates to shared scorer with Shopee spread."""
    return _shared_scorer._price_competition_score(
        prices_cents,
        tight_pct=SHOPEE_CAPS.tight_spread_pct,
        wide_pct=SHOPEE_CAPS.wide_spread_pct,
    )


def _classify(score: float) -> SaturationLevel:
    """Backward-compat shim \u2014 maps shared level enum to the Shopee one."""
    return _LEVEL_MAP[classify(score)]


def _is_relevant(product: ShopeeProduct, set_number: str) -> bool:
    """Check if a product listing is actually for the target LEGO set.

    Matches the set number anywhere in the title (with optional hyphen/space
    separators). This filters out non-LEGO items, accessories, and
    compatible-but-not-genuine listings that Shopee mixes into results.
    """
    title = product.title.upper()
    pattern = re.escape(set_number)
    return bool(re.search(pattern, title))


def filter_relevant_products(
    products: tuple[ShopeeProduct, ...],
    set_number: str,
) -> tuple[ShopeeProduct, ...]:
    """Keep only products whose title contains the target set number."""
    return tuple(p for p in products if _is_relevant(p, set_number))


def compute_saturation(
    set_number: str,
    search_query: str,
    products: tuple[ShopeeProduct, ...],
    rrp_cents: int | None = None,
) -> SaturationSnapshot:
    """Compute a saturation snapshot from Shopee search results.

    Args:
        set_number: LEGO set number
        search_query: The search term used
        products: Parsed product listings from the first page
        rrp_cents: Recommended retail price in cents (for future use)
    """
    relevant = filter_relevant_products(products, set_number)
    listings_count = len(relevant)

    seller_names = frozenset(p.shop_name for p in relevant if p.shop_name)
    unique_sellers = len(seller_names)

    prices_cents = [
        c
        for p in relevant
        if (c := _parse_price_cents(p.price_display)) is not None
    ]

    stats = compute_price_stats(prices_cents)
    score = compute_composite_score(
        listings_count=listings_count,
        unique_sellers=unique_sellers,
        prices_cents=prices_cents,
        caps=SHOPEE_CAPS,
    )

    return SaturationSnapshot(
        set_number=set_number,
        listings_count=listings_count,
        unique_sellers=unique_sellers,
        min_price_cents=stats.min_cents,
        max_price_cents=stats.max_cents,
        avg_price_cents=stats.avg_cents,
        median_price_cents=stats.median_cents,
        price_spread_pct=stats.spread_pct,
        saturation_score=score,
        saturation_level=_LEVEL_MAP[classify(score)],
        search_query=search_query,
        scraped_at=datetime.now(timezone.utc),
    )
