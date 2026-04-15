"""Repository for Carousell competition tracking snapshots."""

from __future__ import annotations

from typing import Any

from services.carousell.competition_types import (
    CarousellCompetitionListing,
    CarousellCompetitionSnapshot,
)
from services.marketplace_competition.tiered_selection import (
    get_tiered_items_needing_check,
)


def get_items_needing_competition_check_tiered(
    conn: Any,
    limit: int = 20,
) -> list[dict]:
    """Find items needing a Carousell competition check, tiered by source.

    Same tier logic as Shopee (see marketplace_competition.tiered_selection)
    but reads staleness from `carousell_competition_snapshots`.
    """
    return get_tiered_items_needing_check(
        conn,
        snapshots_table="carousell_competition_snapshots",
        limit=limit,
    )


def save_competition_snapshot(
    conn: Any,
    snapshot: CarousellCompetitionSnapshot,
) -> int:
    """Insert a Carousell competition snapshot and its listings.

    Returns the new snapshot id.
    """
    conn.execute(
        """
        INSERT INTO carousell_competition_snapshots (
            id, set_number, listings_count, unique_sellers,
            flipped_to_sold_count,
            min_price_cents, max_price_cents,
            avg_price_cents, median_price_cents,
            saturation_score, saturation_level, scraped_at
        ) VALUES (
            nextval('carousell_competition_snapshots_id_seq'),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            snapshot.set_number,
            snapshot.listings_count,
            snapshot.unique_sellers,
            snapshot.flipped_to_sold_count,
            snapshot.min_price_cents,
            snapshot.max_price_cents,
            snapshot.avg_price_cents,
            snapshot.median_price_cents,
            snapshot.saturation_score,
            snapshot.saturation_level.value,
            snapshot.scraped_at,
        ],
    )

    row = conn.execute(
        "SELECT currval('carousell_competition_snapshots_id_seq')"
    ).fetchone()
    snapshot_id: int = row[0]

    for listing in snapshot.listings:
        conn.execute(
            """
            INSERT INTO carousell_competition_listings (
                id, snapshot_id, set_number,
                listing_id, listing_url, shop_id, seller_name,
                title, price_cents, price_display,
                condition, image_url, time_ago,
                is_sold, is_reserved, is_delisted, scraped_at
            ) VALUES (
                nextval('carousell_competition_listings_id_seq'),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                snapshot_id,
                snapshot.set_number,
                listing.listing_id,
                listing.listing_url,
                listing.shop_id,
                listing.seller_name,
                listing.title,
                listing.price_cents,
                listing.price_display,
                listing.condition,
                listing.image_url,
                listing.time_ago,
                listing.is_sold,
                listing.is_reserved,
                listing.is_delisted,
                snapshot.scraped_at,
            ],
        )

    return snapshot_id


def get_competition_history(
    conn: Any,
    set_number: str,
    limit: int = 50,
) -> list[dict]:
    """Return past Carousell competition snapshots for trend charts."""
    result = conn.execute(
        """
        SELECT set_number, listings_count, unique_sellers,
               flipped_to_sold_count,
               min_price_cents, max_price_cents,
               avg_price_cents, median_price_cents,
               saturation_score, saturation_level, scraped_at
        FROM carousell_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT ?
        """,
        [set_number, limit],
    ).fetchall()

    columns = [
        "set_number", "listings_count", "unique_sellers",
        "flipped_to_sold_count",
        "min_price_cents", "max_price_cents",
        "avg_price_cents", "median_price_cents",
        "saturation_score", "saturation_level", "scraped_at",
    ]
    return [dict(zip(columns, row)) for row in result]


def get_latest_competition_listings(
    conn: Any,
    set_number: str,
) -> list[dict]:
    """Return individual listings from the most recent Carousell snapshot."""
    row = conn.execute(
        """
        SELECT id FROM carousell_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC LIMIT 1
        """,
        [set_number],
    ).fetchone()

    if not row:
        return []

    snapshot_id = row[0]
    result = conn.execute(
        """
        SELECT listing_id, listing_url, shop_id, seller_name,
               title, price_cents, price_display, condition,
               image_url, time_ago, is_sold, is_reserved, is_delisted,
               scraped_at
        FROM carousell_competition_listings
        WHERE snapshot_id = ?
        ORDER BY is_sold ASC, is_reserved ASC, price_cents ASC NULLS LAST
        """,
        [snapshot_id],
    ).fetchall()

    columns = [
        "listing_id", "listing_url", "shop_id", "seller_name",
        "title", "price_cents", "price_display", "condition",
        "image_url", "time_ago", "is_sold", "is_reserved", "is_delisted",
        "scraped_at",
    ]
    return [dict(zip(columns, row)) for row in result]


def get_previous_listing_ids(
    conn: Any,
    set_number: str,
) -> dict[str, dict]:
    """Return {listing_id: {is_sold, is_reserved, is_delisted}} from prior snapshot.

    Used to compute `flipped_to_sold_count` \u2014 how many listings
    transitioned from active -> sold between snapshots.
    """
    row = conn.execute(
        """
        SELECT id FROM carousell_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC LIMIT 1
        """,
        [set_number],
    ).fetchone()
    if not row:
        return {}

    result = conn.execute(
        """
        SELECT listing_id, is_sold, is_reserved, is_delisted
        FROM carousell_competition_listings
        WHERE snapshot_id = ?
        """,
        [row[0]],
    ).fetchall()

    return {
        r[0]: {
            "is_sold": bool(r[1]),
            "is_reserved": bool(r[2]),
            "is_delisted": bool(r[3]),
        }
        for r in result
    }


def get_flipped_to_sold_in_window(
    conn: Any,
    set_number: str,
    window_days: int,
) -> dict[str, Any] | None:
    """Count active->sold transitions over a trailing window.

    Picks the latest snapshot and the newest prior snapshot at or
    before (latest - window_days). A listing counts as "flipped" if
    its row in the prior snapshot had `is_sold=False AND is_reserved=False
    AND is_delisted=False` and its row in the latest snapshot has
    `is_sold=True`. Returns None when no snapshots exist; returns a
    dict with `flipped=None` when only one snapshot exists.
    """
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    latest = conn.execute(
        """
        SELECT id, scraped_at
        FROM carousell_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        [set_number],
    ).fetchone()
    if latest is None:
        return None

    latest_id, latest_at = latest

    prior = conn.execute(
        """
        SELECT id, scraped_at
        FROM carousell_competition_snapshots
        WHERE set_number = ?
          AND scraped_at <= ? - make_interval(days => ?)
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        [set_number, latest_at, window_days],
    ).fetchone()

    if prior is None:
        prior = conn.execute(
            """
            SELECT id, scraped_at
            FROM carousell_competition_snapshots
            WHERE set_number = ? AND scraped_at < ?
            ORDER BY scraped_at ASC
            LIMIT 1
            """,
            [set_number, latest_at],
        ).fetchone()

    if prior is None:
        return {
            "flipped": None,
            "latest_at": latest_at,
            "prior_at": None,
        }

    prior_id, prior_at = prior

    flipped_row = conn.execute(
        """
        SELECT COUNT(*)
        FROM carousell_competition_listings prev
        JOIN carousell_competition_listings cur
          ON cur.listing_id = prev.listing_id
         AND cur.snapshot_id = ?
        WHERE prev.snapshot_id = ?
          AND prev.is_sold = FALSE
          AND prev.is_reserved = FALSE
          AND prev.is_delisted = FALSE
          AND cur.is_sold = TRUE
        """,
        [latest_id, prior_id],
    ).fetchone()

    flipped = int(flipped_row[0]) if flipped_row else 0

    return {
        "flipped": flipped,
        "latest_at": latest_at,
        "prior_at": prior_at,
    }


def get_latest_snapshot(
    conn: Any,
    set_number: str,
) -> dict[str, Any] | None:
    """Return the latest Carousell snapshot row as a plain dict, or None."""
    row = conn.execute(
        """
        SELECT listings_count, unique_sellers, flipped_to_sold_count,
               min_price_cents, max_price_cents,
               avg_price_cents, median_price_cents,
               saturation_score, saturation_level, scraped_at
        FROM carousell_competition_snapshots
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
        flipped_to_sold_count,
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
        "flipped_to_sold_count": flipped_to_sold_count,
        "min_price_cents": min_price_cents,
        "max_price_cents": max_price_cents,
        "avg_price_cents": avg_price_cents,
        "median_price_cents": median_price_cents,
        "saturation_score": saturation_score,
        "saturation_level": saturation_level,
        "scraped_at": scraped_at.isoformat() if scraped_at else None,
    }


def count_active_to_sold_flips(
    conn: Any,
    set_number: str,
    current_listings: list[CarousellCompetitionListing],
) -> int | None:
    """Count listings that were active in the prior snapshot and are
    sold in the current `current_listings` list.

    Returns None when no prior snapshot exists (no baseline to diff).
    Returns 0 when prior snapshot exists but no flips occurred.
    """
    prior_state = get_previous_listing_ids(conn, set_number)
    if not prior_state:
        return None

    flips = 0
    for listing in current_listings:
        prior = prior_state.get(listing.listing_id)
        if prior is None:
            continue
        was_active = not (
            prior["is_sold"] or prior["is_reserved"] or prior["is_delisted"]
        )
        if was_active and listing.is_sold:
            flips += 1
    return flips
