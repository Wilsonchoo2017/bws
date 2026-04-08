"""Marketplace listing persistence.

Tracks which platforms a LEGO set is actively listed on, the listing
price, and the listing status (active / sold / delisted).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("bws.listing.repository")


def record_listing(
    conn: Any,
    set_number: str,
    platform: str,
    listing_price_cents: int,
    currency: str = "MYR",
) -> bool:
    """Record or update a marketplace listing for a set.

    Uses UPSERT -- if the set is already listed on this platform,
    the price and status are updated.

    Returns True on success.
    """
    conn.execute(
        """
        INSERT INTO marketplace_listings
            (set_number, platform, listing_price_cents, listing_currency, status, listed_at, updated_at)
        VALUES (?, ?, ?, ?, 'active', now(), now())
        ON CONFLICT (set_number, platform)
        DO UPDATE SET
            listing_price_cents = EXCLUDED.listing_price_cents,
            listing_currency = EXCLUDED.listing_currency,
            status = 'active',
            updated_at = now()
        """,
        [set_number, platform, listing_price_cents, currency],
    )
    logger.info(
        "Recorded listing: %s on %s at %d %s",
        set_number, platform, listing_price_cents, currency,
    )
    return True


def update_listing_status(
    conn: Any,
    set_number: str,
    platform: str,
    status: str,
) -> bool:
    """Update listing status (active / sold / delisted).

    Returns True if a row was updated.
    """
    result = conn.execute(
        """
        UPDATE marketplace_listings
        SET status = ?, updated_at = now()
        WHERE set_number = ? AND platform = ?
        """,
        [status, set_number, platform],
    )
    return result.rowcount > 0


def get_listings_for_set(
    conn: Any,
    set_number: str,
) -> list[dict[str, Any]]:
    """Get all marketplace listings for a set (any status)."""
    rows = conn.execute(
        """
        SELECT platform, listing_price_cents, listing_currency,
               status, listed_at, updated_at
        FROM marketplace_listings
        WHERE set_number = ?
        ORDER BY listed_at DESC
        """,
        [set_number],
    ).fetchall()
    return [
        {
            "platform": row[0],
            "listing_price_cents": row[1],
            "listing_currency": row[2],
            "status": row[3],
            "listed_at": row[4],
            "updated_at": row[5],
        }
        for row in rows
    ]


def get_active_listings_for_set(
    conn: Any,
    set_number: str,
) -> list[str]:
    """Get platform names where a set is actively listed."""
    rows = conn.execute(
        """
        SELECT platform FROM marketplace_listings
        WHERE set_number = ? AND status = 'active'
        ORDER BY platform
        """,
        [set_number],
    ).fetchall()
    return [row[0] for row in rows]


def get_active_listings_bulk(
    conn: Any,
    set_numbers: list[str],
) -> dict[str, list[str]]:
    """Get active listing platforms for multiple sets at once.

    Returns {set_number: [platform, ...]} for sets that have listings.
    """
    if not set_numbers:
        return {}

    placeholders = ", ".join(["?"] * len(set_numbers))
    rows = conn.execute(
        f"""
        SELECT set_number, platform FROM marketplace_listings
        WHERE set_number IN ({placeholders}) AND status = 'active'
        ORDER BY set_number, platform
        """,  # noqa: S608
        set_numbers,
    ).fetchall()

    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(row[0], []).append(row[1])
    return result
