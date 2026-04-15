"""Platform-agnostic marketplace competition types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

Platform = Literal["shopee", "carousell", "facebook"]


class SaturationLevel(Enum):
    """Saturation classification from a 0-100 composite score."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


@dataclass(frozen=True)
class MarketplaceListing:
    """A single listing on any supported marketplace.

    Field meanings:
    - price_cents: price in the marketplace's native currency cents
      (MYR for all three MY marketplaces).
    - sold_count: Shopee-specific cumulative sold count per listing;
      None for Carousell/FB which do not expose this.
    - is_sold / is_reserved: explicit transaction-state flags. Shopee
      uses only `is_sold_out` / `is_delisted` under different names;
      Carousell has reserved as a distinct state.
    """

    listing_id: str
    platform: Platform
    title: str
    price_cents: int | None
    shop_id: str | None
    sold_count: int | None = None
    is_sold: bool = False
    is_reserved: bool = False
    is_delisted: bool = False
