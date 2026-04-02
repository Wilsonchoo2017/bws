"""DuckDB persistence for Shopee saturation snapshots."""

from typing import TYPE_CHECKING

from services.shopee.saturation_types import SaturationSnapshot

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def save_saturation_snapshot(
    conn: "DuckDBPyConnection",
    snapshot: SaturationSnapshot,
) -> None:
    """Insert a saturation snapshot row (append-only for trend history)."""
    conn.execute(
        """
        INSERT INTO shopee_saturation (
            id, set_number, listings_count, unique_sellers,
            min_price_cents, max_price_cents, avg_price_cents,
            median_price_cents, price_spread_pct,
            saturation_score, saturation_level, search_query, scraped_at
        ) VALUES (
            nextval('shopee_saturation_id_seq'),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            snapshot.set_number,
            snapshot.listings_count,
            snapshot.unique_sellers,
            snapshot.min_price_cents,
            snapshot.max_price_cents,
            snapshot.avg_price_cents,
            snapshot.median_price_cents,
            snapshot.price_spread_pct,
            snapshot.saturation_score,
            snapshot.saturation_level.value,
            snapshot.search_query,
            snapshot.scraped_at,
        ],
    )


def get_latest_saturation(
    conn: "DuckDBPyConnection",
    set_number: str,
) -> dict | None:
    """Get the most recent saturation snapshot for a set."""
    from db.queries import get_latest_row

    _SATURATION_COLUMNS = (
        "set_number, listings_count, unique_sellers, "
        "min_price_cents, max_price_cents, avg_price_cents, "
        "median_price_cents, price_spread_pct, "
        "saturation_score, saturation_level, search_query, scraped_at"
    )
    return get_latest_row(
        conn, "shopee_saturation", key_value=set_number, columns=_SATURATION_COLUMNS,
    )


def get_all_latest_saturations(
    conn: "DuckDBPyConnection",
) -> list[dict]:
    """Get the latest saturation snapshot for every set."""
    result = conn.execute(
        """
        SELECT set_number, listings_count, unique_sellers,
               min_price_cents, max_price_cents, avg_price_cents,
               median_price_cents, price_spread_pct,
               saturation_score, saturation_level, search_query, scraped_at
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY set_number ORDER BY scraped_at DESC
                   ) AS rn
            FROM shopee_saturation
        ) ranked
        WHERE rn = 1
        ORDER BY saturation_score DESC
        """
    ).fetchall()

    columns = [
        "set_number", "listings_count", "unique_sellers",
        "min_price_cents", "max_price_cents", "avg_price_cents",
        "median_price_cents", "price_spread_pct",
        "saturation_score", "saturation_level", "search_query", "scraped_at",
    ]
    return [dict(zip(columns, row)) for row in result]


def get_items_needing_saturation_check(
    conn: "DuckDBPyConnection",
    stale_days: int = 7,
    limit: int = 50,
) -> list[dict]:
    """Find items with RRP that haven't been saturation-checked recently.

    Returns items where rrp_cents IS NOT NULL and either:
    - Never checked (no row in shopee_saturation)
    - Last checked more than stale_days ago
    """
    if not isinstance(stale_days, int) or not isinstance(limit, int):
        raise TypeError("stale_days and limit must be integers")

    query = f"""
        SELECT li.set_number, li.title, li.rrp_cents
        FROM lego_items li
        LEFT JOIN (
            SELECT set_number, MAX(scraped_at) AS last_checked
            FROM shopee_saturation
            GROUP BY set_number
        ) ss ON ss.set_number = li.set_number
        WHERE li.rrp_cents IS NOT NULL
          AND (ss.last_checked IS NULL
               OR ss.last_checked < now() - INTERVAL '{stale_days} days')
        ORDER BY ss.last_checked ASC NULLS FIRST
        LIMIT {limit}
    """  # noqa: S608 -- stale_days and limit are validated ints above
    result = conn.execute(query).fetchall()

    return [
        {"set_number": row[0], "title": row[1], "rrp_cents": row[2]}
        for row in result
    ]
