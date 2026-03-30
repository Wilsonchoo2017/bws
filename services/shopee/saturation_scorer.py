"""Compute Shopee market saturation score from search results."""

import re
import statistics
from datetime import datetime, timezone

from services.shopee.parser import ShopeeProduct
from services.shopee.repository import _parse_price_cents
from services.shopee.saturation_types import SaturationLevel, SaturationSnapshot


def _is_relevant(product: ShopeeProduct, set_number: str) -> bool:
    """Check if a product listing is actually for the target LEGO set.

    Matches the set number anywhere in the title (with optional hyphen/space
    separators). This filters out non-LEGO items, accessories, and
    compatible-but-not-genuine listings that Shopee mixes into results.
    """
    title = product.title.upper()
    # Match set number with optional separators (e.g. "10281", "10-281")
    pattern = re.escape(set_number)
    return bool(re.search(pattern, title))


def filter_relevant_products(
    products: tuple[ShopeeProduct, ...],
    set_number: str,
) -> tuple[ShopeeProduct, ...]:
    """Keep only products whose title contains the target set number."""
    return tuple(p for p in products if _is_relevant(p, set_number))


# Scoring weights
_MAX_LISTING_POINTS = 60.0
_MAX_SELLER_POINTS = 25.0
_MAX_PRICE_COMP_POINTS = 15.0

# Thresholds
_LISTINGS_CAP = 50  # 50+ listings = max listing score
_SELLERS_CAP = 20   # 20+ unique sellers = max seller score


def _listing_score(count: int) -> float:
    """0-60 points: linear scale from 0 to _LISTINGS_CAP listings."""
    return min(count / _LISTINGS_CAP, 1.0) * _MAX_LISTING_POINTS


def _seller_score(unique_sellers: int) -> float:
    """0-25 points: linear scale from 0 to _SELLERS_CAP unique sellers."""
    return min(unique_sellers / _SELLERS_CAP, 1.0) * _MAX_SELLER_POINTS


def _price_competition_score(prices_cents: list[int]) -> float:
    """0-15 points: tight price spread = high competition = high saturation.

    Spread is (max - min) / avg * 100.
    <20% spread = 15 pts (price war), >80% spread = 0 pts (differentiated).
    """
    if len(prices_cents) < 2:
        return 0.0

    avg = statistics.mean(prices_cents)
    if avg <= 0:
        return 0.0

    spread_pct = (max(prices_cents) - min(prices_cents)) / avg * 100

    if spread_pct <= 20:
        return _MAX_PRICE_COMP_POINTS
    if spread_pct >= 80:
        return 0.0

    # Linear interpolation: 20% -> 15 pts, 80% -> 0 pts
    return _MAX_PRICE_COMP_POINTS * (1.0 - (spread_pct - 20) / 60)


def _classify(score: float) -> SaturationLevel:
    """Map numeric score to saturation level."""
    if score < 25:
        return SaturationLevel.VERY_LOW
    if score < 50:
        return SaturationLevel.LOW
    if score < 75:
        return SaturationLevel.MODERATE
    return SaturationLevel.HIGH


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

    Returns:
        Frozen SaturationSnapshot with score and price statistics
    """
    # Filter to only listings that mention the target set number
    relevant = filter_relevant_products(products, set_number)
    listings_count = len(relevant)

    # Extract unique sellers (filter None shop names)
    seller_names = frozenset(
        p.shop_name for p in relevant if p.shop_name
    )
    unique_sellers = len(seller_names)

    # Parse prices from display strings
    prices_cents = [
        c for p in relevant
        if (c := _parse_price_cents(p.price_display)) is not None
    ]

    # Price statistics
    min_price = min(prices_cents) if prices_cents else None
    max_price = max(prices_cents) if prices_cents else None
    avg_price = int(statistics.mean(prices_cents)) if prices_cents else None
    median_price = int(statistics.median(prices_cents)) if prices_cents else None

    # Price spread percentage
    spread_pct: float | None = None
    if prices_cents and avg_price and avg_price > 0 and len(prices_cents) >= 2:
        spread_pct = round(
            (max(prices_cents) - min(prices_cents)) / avg_price * 100, 1
        )

    # Composite score (0-100)
    raw_score = (
        _listing_score(listings_count)
        + _seller_score(unique_sellers)
        + _price_competition_score(prices_cents)
    )
    score = round(max(0.0, min(100.0, raw_score)), 1)

    return SaturationSnapshot(
        set_number=set_number,
        listings_count=listings_count,
        unique_sellers=unique_sellers,
        min_price_cents=min_price,
        max_price_cents=max_price,
        avg_price_cents=avg_price,
        median_price_cents=median_price,
        price_spread_pct=spread_pct,
        saturation_score=score,
        saturation_level=_classify(score),
        search_query=search_query,
        scraped_at=datetime.now(timezone.utc),
    )
