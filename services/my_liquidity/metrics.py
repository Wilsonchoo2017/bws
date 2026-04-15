"""Per-item composite of Malaysian exit-liquidity signals.

Combines MY premium (premium.py) with Shopee sold-count velocity
(velocity.py) and Carousell active\u2192sold flip counts into a single
dict consumed by the /my-liquidity API route and the detail-bundle.

All inputs come from existing tables:
- shopee_competition_snapshots / shopee_competition_listings
- carousell_competition_snapshots / carousell_competition_listings
- bricklink_monthly_sales
- brickeconomy_snapshots
No schema changes, no persistence.
"""

from __future__ import annotations

from typing import Any, Literal

from services.carousell.competition_repository import (
    get_flipped_to_sold_in_window,
    get_latest_snapshot as get_latest_carousell_snapshot,
)
from services.my_liquidity.premium import compute_premium
from services.my_liquidity.velocity import compute_velocity

DataSufficiency = Literal["full", "partial", "insufficient"]


def build_my_liquidity_data(conn: Any, set_number: str) -> dict[str, Any]:
    """Return the per-item MY exit-liquidity payload.

    Shape:
        {
          "set_number": str,
          "data_sufficiency": "full" | "partial" | "insufficient",
          "premium": {... MyPremium dict ...},
          "shopee": {
            "velocity_30d": {...},
            "velocity_7d": {...},
            "latest_snapshot": {...} | None,
          },
          "carousell": {
            "latest_snapshot": {...} | None,
            "flipped_to_sold_30d": int | None,
            "flipped_to_sold_7d": int | None,
          },
          "warnings": [str, ...],
        }

    "insufficient" means neither marketplace has any snapshots for this
    set. "partial" means at least one marketplace has data but velocity
    or premium is missing. "full" means Shopee premium is resolved AND
    at least one platform has a usable velocity signal.
    """
    shopee_latest = _fetch_shopee_latest(conn, set_number)
    carousell_latest = get_latest_carousell_snapshot(conn, set_number)

    premium = compute_premium(conn, set_number)
    vel_30 = compute_velocity(conn, set_number, window_days=30)
    vel_7 = compute_velocity(conn, set_number, window_days=7)

    carousell_flip_30 = get_flipped_to_sold_in_window(conn, set_number, 30)
    carousell_flip_7 = get_flipped_to_sold_in_window(conn, set_number, 7)

    shopee_payload = {
        "velocity_30d": vel_30.to_dict(),
        "velocity_7d": vel_7.to_dict(),
        "latest_snapshot": shopee_latest,
    }
    carousell_payload = {
        "latest_snapshot": carousell_latest,
        "flipped_to_sold_30d": _flip_count(carousell_flip_30),
        "flipped_to_sold_7d": _flip_count(carousell_flip_7),
    }

    sufficiency, warnings = _classify_sufficiency(
        shopee_latest=shopee_latest,
        carousell_latest=carousell_latest,
        shopee_velocity_delta=vel_30.total_sold_delta,
        carousell_flip_30=_flip_count(carousell_flip_30),
        premium_pct=premium.premium_median_pct,
        premium_bl_usd_cents=premium.bl_usd_cents,
        premium_bl_source=premium.bl_source,
    )

    return {
        "set_number": set_number,
        "data_sufficiency": sufficiency,
        "premium": premium.to_dict(),
        "shopee": shopee_payload,
        "carousell": carousell_payload,
        "warnings": warnings,
    }


def _flip_count(flip_row: dict[str, Any] | None) -> int | None:
    """Extract the scalar flip count from a get_flipped_to_sold_in_window result."""
    if flip_row is None:
        return None
    return flip_row.get("flipped")


def _classify_sufficiency(
    *,
    shopee_latest: dict[str, Any] | None,
    carousell_latest: dict[str, Any] | None,
    shopee_velocity_delta: int | None,
    carousell_flip_30: int | None,
    premium_pct: float | None,
    premium_bl_usd_cents: int | None,
    premium_bl_source: str,
) -> tuple[DataSufficiency, list[str]]:
    """Decide the overall data sufficiency tier and assemble warnings."""
    warnings: list[str] = []

    if shopee_latest is None and carousell_latest is None:
        warnings.append(
            "No Shopee or Carousell competition snapshots for this set."
        )
        return "insufficient", warnings

    has_velocity = (
        shopee_velocity_delta is not None or carousell_flip_30 is not None
    )
    has_premium = premium_pct is not None

    if has_velocity and has_premium:
        sufficiency: DataSufficiency = "full"
    else:
        sufficiency = "partial"
        if not has_velocity:
            warnings.append(
                "Only one competition snapshot per platform \u2014 velocity delta not yet available."
            )
        if not has_premium and premium_bl_usd_cents is None:
            warnings.append(
                "No BrickLink or BrickEconomy USD benchmark for this set \u2014 premium unavailable."
            )

    if premium_bl_source == "brickeconomy_rrp_usd":
        warnings.append(
            "Premium computed against retail RRP (no market price available) \u2014 treat as indicative only."
        )

    if shopee_latest is None:
        warnings.append("No Shopee listings observed yet for this set.")
    if carousell_latest is None:
        warnings.append("No Carousell listings observed yet for this set.")

    return sufficiency, warnings


def _fetch_shopee_latest(conn: Any, set_number: str) -> dict[str, Any] | None:
    """Pull the single latest Shopee competition snapshot row as a plain dict."""
    row = conn.execute(
        """
        SELECT listings_count, unique_sellers, total_sold_count,
               min_price_cents, max_price_cents,
               avg_price_cents, median_price_cents,
               saturation_score, saturation_level, scraped_at
        FROM shopee_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        [set_number],
    ).fetchone()

    if row is None:
        return None

    (
        listings_count,
        unique_sellers,
        total_sold_count,
        min_price_cents,
        max_price_cents,
        avg_price_cents,
        median_price_cents,
        saturation_score,
        saturation_level,
        scraped_at,
    ) = row
    return {
        "listings_count": listings_count,
        "unique_sellers": unique_sellers,
        "total_sold_count": total_sold_count,
        "min_price_cents": min_price_cents,
        "max_price_cents": max_price_cents,
        "avg_price_cents": avg_price_cents,
        "median_price_cents": median_price_cents,
        "saturation_score": saturation_score,
        "saturation_level": saturation_level,
        "scraped_at": scraped_at.isoformat() if scraped_at else None,
    }
