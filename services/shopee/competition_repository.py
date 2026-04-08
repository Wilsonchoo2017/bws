"""Repository for Shopee competition tracking snapshots."""

from __future__ import annotations

import statistics
from typing import Any

from services.shopee.competition_types import CompetitionListing, CompetitionSnapshot
from services.shopee.parser import parse_sold_count
from services.shopee.repository import _parse_price_cents


def save_competition_snapshot(
    conn: Any,
    snapshot: CompetitionSnapshot,
) -> int:
    """Insert a competition snapshot and its listings. Returns snapshot id."""
    conn.execute(
        """
        INSERT INTO shopee_competition_snapshots (
            id, set_number, listings_count, unique_sellers,
            total_sold_count, min_price_cents, max_price_cents,
            avg_price_cents, median_price_cents,
            saturation_score, saturation_level, scraped_at
        ) VALUES (
            nextval('shopee_competition_snapshots_id_seq'),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            snapshot.set_number,
            snapshot.listings_count,
            snapshot.unique_sellers,
            snapshot.total_sold_count,
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
        "SELECT currval('shopee_competition_snapshots_id_seq')"
    ).fetchone()
    snapshot_id: int = row[0]

    for listing in snapshot.listings:
        conn.execute(
            """
            INSERT INTO shopee_competition_listings (
                id, snapshot_id, set_number, product_url, shop_id,
                title, price_cents, price_display,
                sold_count_raw, sold_count_numeric, rating, image_url,
                is_sold_out, is_delisted, discovery_method, scraped_at
            ) VALUES (
                nextval('shopee_competition_listings_id_seq'),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                snapshot_id,
                snapshot.set_number,
                listing.product_url,
                listing.shop_id,
                listing.title,
                listing.price_cents,
                listing.price_display,
                listing.sold_count_raw,
                listing.sold_count_numeric,
                listing.rating,
                listing.image_url,
                listing.is_sold_out,
                listing.is_delisted,
                listing.discovery_method,
                snapshot.scraped_at,
            ],
        )

    return snapshot_id


def get_competition_history(
    conn: Any,
    set_number: str,
    limit: int = 50,
) -> list[dict]:
    """Get all competition snapshots for trend charts."""
    result = conn.execute(
        """
        SELECT set_number, listings_count, unique_sellers,
               total_sold_count, min_price_cents, max_price_cents,
               avg_price_cents, median_price_cents,
               saturation_score, saturation_level, scraped_at
        FROM shopee_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT ?
        """,
        [set_number, limit],
    ).fetchall()

    columns = [
        "set_number", "listings_count", "unique_sellers",
        "total_sold_count", "min_price_cents", "max_price_cents",
        "avg_price_cents", "median_price_cents",
        "saturation_score", "saturation_level", "scraped_at",
    ]
    return [dict(zip(columns, row)) for row in result]


def get_latest_competition_listings(
    conn: Any,
    set_number: str,
) -> list[dict]:
    """Get individual listings from the most recent snapshot."""
    # Find latest snapshot id
    row = conn.execute(
        """
        SELECT id FROM shopee_competition_snapshots
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
        SELECT product_url, shop_id, title, price_cents, price_display,
               sold_count_raw, sold_count_numeric, rating, image_url,
               is_sold_out, is_delisted, discovery_method, scraped_at
        FROM shopee_competition_listings
        WHERE snapshot_id = ?
        ORDER BY sold_count_numeric DESC NULLS LAST
        """,
        [snapshot_id],
    ).fetchall()

    columns = [
        "product_url", "shop_id", "title", "price_cents", "price_display",
        "sold_count_raw", "sold_count_numeric", "rating", "image_url",
        "is_sold_out", "is_delisted", "discovery_method", "scraped_at",
    ]
    return [dict(zip(columns, row)) for row in result]


def get_previous_listing_urls(
    conn: Any,
    set_number: str,
) -> list[dict]:
    """Get product URLs and shop IDs from the most recent snapshot.

    Used by the scraper to know which URLs to revisit if they don't
    appear in the current search results.
    """
    row = conn.execute(
        """
        SELECT id FROM shopee_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC LIMIT 1
        """,
        [set_number],
    ).fetchone()

    if not row:
        return []

    result = conn.execute(
        """
        SELECT product_url, shop_id, title, sold_count_numeric
        FROM shopee_competition_listings
        WHERE snapshot_id = ? AND is_delisted = FALSE
        """,
        [row[0]],
    ).fetchall()

    return [
        {
            "product_url": r[0],
            "shop_id": r[1],
            "title": r[2],
            "sold_count_numeric": r[3],
        }
        for r in result
    ]


def get_portfolio_items_needing_competition_check(
    conn: Any,
    stale_days: int = 30,
    limit: int = 20,
) -> list[dict]:
    """Find portfolio holdings that need a competition check.

    Returns items where the user holds stock and either:
    - Never checked (no row in shopee_competition_snapshots)
    - Last checked more than stale_days ago
    """
    if not isinstance(stale_days, int) or not isinstance(limit, int):
        raise TypeError("stale_days and limit must be integers")

    query = f"""
        WITH holdings AS (
            SELECT pt.set_number,
                   SUM(CASE WHEN pt.txn_type = 'BUY' THEN pt.quantity ELSE -pt.quantity END) AS qty
            FROM portfolio_transactions pt
            GROUP BY pt.set_number
            HAVING SUM(CASE WHEN pt.txn_type = 'BUY' THEN pt.quantity ELSE -pt.quantity END) > 0
        )
        SELECT h.set_number, li.title, li.rrp_cents
        FROM holdings h
        JOIN lego_items li ON li.set_number = h.set_number
        LEFT JOIN (
            SELECT set_number, MAX(scraped_at) AS last_checked
            FROM shopee_competition_snapshots
            GROUP BY set_number
        ) cs ON cs.set_number = h.set_number
        WHERE cs.last_checked IS NULL
           OR cs.last_checked < now() - INTERVAL '{stale_days} days'
        ORDER BY cs.last_checked ASC NULLS FIRST
        LIMIT {limit}
    """  # noqa: S608 -- stale_days and limit are validated ints above
    result = conn.execute(query).fetchall()

    return [
        {"set_number": row[0], "title": row[1], "rrp_cents": row[2]}
        for row in result
    ]


def get_listing_sold_deltas(
    conn: Any,
    set_number: str,
) -> dict[str, int | None]:
    """Get sold count deltas between the two most recent snapshots.

    Returns {product_url: delta} where delta = latest - previous.
    """
    rows = conn.execute(
        """
        SELECT id FROM shopee_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC LIMIT 2
        """,
        [set_number],
    ).fetchall()

    if len(rows) < 2:
        return {}

    latest_id, prev_id = rows[0][0], rows[1][0]

    latest = conn.execute(
        "SELECT product_url, sold_count_numeric FROM shopee_competition_listings WHERE snapshot_id = ?",
        [latest_id],
    ).fetchall()

    prev = conn.execute(
        "SELECT product_url, sold_count_numeric FROM shopee_competition_listings WHERE snapshot_id = ?",
        [prev_id],
    ).fetchall()

    prev_map = {r[0]: r[1] for r in prev}
    deltas: dict[str, int | None] = {}

    for url, sold in latest:
        prev_sold = prev_map.get(url)
        if sold is not None and prev_sold is not None:
            deltas[url] = sold - prev_sold
        else:
            deltas[url] = None

    return deltas
