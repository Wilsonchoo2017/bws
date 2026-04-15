"""Composite saturation score for a marketplace listing set.

The score is the same 3-component recipe used originally for Shopee
(listing count + unique sellers + price spread) but parameterized
by per-platform caps so each marketplace can calibrate against its
own listing density. Carousell has far fewer listings per set than
Shopee, so the same absolute count should mean a different score.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from services.marketplace_competition.types import SaturationLevel

_MAX_LISTING_POINTS = 60.0
_MAX_SELLER_POINTS = 25.0
_MAX_PRICE_COMP_POINTS = 15.0


@dataclass(frozen=True)
class ScoringCaps:
    """Per-platform calibration for the saturation score.

    listings_cap: listings_count that yields the full 60 listing pts
    sellers_cap: unique_sellers that yields the full 25 seller pts
    tight_spread_pct / wide_spread_pct: the spread range over which
        the price-competition sub-score interpolates from max to zero.
    """

    listings_cap: int
    sellers_cap: int
    tight_spread_pct: float = 20.0
    wide_spread_pct: float = 80.0


SHOPEE_CAPS = ScoringCaps(listings_cap=50, sellers_cap=20)
CAROUSELL_CAPS = ScoringCaps(listings_cap=20, sellers_cap=10)


def _listing_score(count: int, cap: int) -> float:
    if cap <= 0:
        return 0.0
    return min(count / cap, 1.0) * _MAX_LISTING_POINTS


def _seller_score(unique_sellers: int, cap: int) -> float:
    if cap <= 0:
        return 0.0
    return min(unique_sellers / cap, 1.0) * _MAX_SELLER_POINTS


def _price_competition_score(
    prices_cents: list[int],
    *,
    tight_pct: float,
    wide_pct: float,
) -> float:
    if len(prices_cents) < 2:
        return 0.0

    avg = statistics.mean(prices_cents)
    if avg <= 0:
        return 0.0

    spread_pct = (max(prices_cents) - min(prices_cents)) / avg * 100.0

    if spread_pct <= tight_pct:
        return _MAX_PRICE_COMP_POINTS
    if spread_pct >= wide_pct:
        return 0.0

    span = wide_pct - tight_pct
    if span <= 0:
        return 0.0
    return _MAX_PRICE_COMP_POINTS * (1.0 - (spread_pct - tight_pct) / span)


def classify(score: float) -> SaturationLevel:
    """Map a 0-100 score to a saturation level bucket."""
    if score < 25:
        return SaturationLevel.VERY_LOW
    if score < 50:
        return SaturationLevel.LOW
    if score < 75:
        return SaturationLevel.MODERATE
    return SaturationLevel.HIGH


def compute_composite_score(
    listings_count: int,
    unique_sellers: int,
    prices_cents: list[int],
    caps: ScoringCaps,
) -> float:
    """Return a 0-100 saturation composite score.

    Components: listings (60 pts), sellers (25 pts), price spread
    (15 pts). Score is clamped and rounded to one decimal place.
    """
    raw = (
        _listing_score(listings_count, caps.listings_cap)
        + _seller_score(unique_sellers, caps.sellers_cap)
        + _price_competition_score(
            prices_cents,
            tight_pct=caps.tight_spread_pct,
            wide_pct=caps.wide_spread_pct,
        )
    )
    return round(max(0.0, min(100.0, raw)), 1)


@dataclass(frozen=True)
class PriceStats:
    """Aggregate price statistics from a list of listing prices."""

    min_cents: int | None
    max_cents: int | None
    avg_cents: int | None
    median_cents: int | None
    spread_pct: float | None


def compute_price_stats(prices_cents: list[int]) -> PriceStats:
    """Min/max/avg/median/spread from an unsorted list of listing prices.

    Empty input returns all-None. A single listing returns min=max=avg=median
    with spread_pct=None (spread undefined).
    """
    if not prices_cents:
        return PriceStats(
            min_cents=None,
            max_cents=None,
            avg_cents=None,
            median_cents=None,
            spread_pct=None,
        )

    avg = int(statistics.mean(prices_cents))
    median = int(statistics.median(prices_cents))
    lo = min(prices_cents)
    hi = max(prices_cents)

    spread_pct: float | None = None
    if len(prices_cents) >= 2 and avg > 0:
        spread_pct = round((hi - lo) / avg * 100.0, 1)

    return PriceStats(
        min_cents=lo,
        max_cents=hi,
        avg_cents=avg,
        median_cents=median,
        spread_pct=spread_pct,
    )
