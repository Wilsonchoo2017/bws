"""Unified LEGO items repository -- master catalog + price records."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def item_exists(conn: "DuckDBPyConnection", set_number: str) -> bool:
    """Check whether a lego_items row exists for this set number."""
    row = conn.execute(
        "SELECT 1 FROM lego_items WHERE set_number = ?", [set_number]
    ).fetchone()
    return row is not None


def _bricklink_image_url(set_number: str) -> str:
    """Construct BrickLink image URL from set number."""
    return f"https://img.bricklink.com/ItemImage/SN/0/{set_number}-1.png"


def get_or_create_item(
    conn: "DuckDBPyConnection",
    set_number: str,
    *,
    title: str | None = None,
    theme: str | None = None,
    year_released: int | None = None,
    year_retired: int | None = None,
    parts_count: int | None = None,
    weight: str | None = None,
    image_url: str | None = None,
    rrp_cents: int | None = None,
    rrp_currency: str | None = None,
    retiring_soon: bool | None = None,
    minifig_count: int | None = None,
    dimensions: str | None = None,
) -> None:
    """Ensure a lego_items row exists for this set number.

    On conflict, updates fields only if the new value is not None
    (preserves existing data, enriches with new sources).
    If no image_url is provided, falls back to BrickLink constructed URL
    for new inserts only -- existing image_urls are never overwritten by fallback.
    """
    # For INSERT: use BrickLink fallback when no image provided.
    # For UPDATE: only pass caller's original value so COALESCE preserves existing.
    insert_image_url = image_url if image_url is not None else _bricklink_image_url(set_number)

    conn.execute(
        """
        INSERT INTO lego_items (
            id, set_number, title, theme, year_released, year_retired,
            parts_count, weight, image_url, rrp_cents, rrp_currency,
            retiring_soon, minifig_count, dimensions
        )
        VALUES (nextval('lego_items_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (set_number) DO UPDATE SET
            title = COALESCE(EXCLUDED.title, lego_items.title),
            theme = COALESCE(EXCLUDED.theme, lego_items.theme),
            year_released = COALESCE(EXCLUDED.year_released, lego_items.year_released),
            year_retired = COALESCE(EXCLUDED.year_retired, lego_items.year_retired),
            parts_count = COALESCE(EXCLUDED.parts_count, lego_items.parts_count),
            weight = COALESCE(EXCLUDED.weight, lego_items.weight),
            image_url = COALESCE(?, lego_items.image_url),
            rrp_cents = COALESCE(EXCLUDED.rrp_cents, lego_items.rrp_cents),
            rrp_currency = COALESCE(EXCLUDED.rrp_currency, lego_items.rrp_currency),
            retiring_soon = COALESCE(EXCLUDED.retiring_soon, lego_items.retiring_soon),
            minifig_count = COALESCE(EXCLUDED.minifig_count, lego_items.minifig_count),
            dimensions = COALESCE(EXCLUDED.dimensions, lego_items.dimensions),
            updated_at = now()
        """,
        [set_number, title, theme, year_released, year_retired, parts_count, weight, insert_image_url,
         rrp_cents, rrp_currency, retiring_soon, minifig_count, dimensions,
         image_url],  # for ON CONFLICT update -- None lets COALESCE keep existing
    )


def record_price(
    conn: "DuckDBPyConnection",
    set_number: str,
    source: str,
    price_cents: int,
    *,
    currency: str = "MYR",
    title: str | None = None,
    url: str | None = None,
    shop_name: str | None = None,
    condition: str | None = None,
) -> None:
    """Record a price observation from any source."""
    conn.execute(
        """
        INSERT INTO price_records (
            id, set_number, source, price_cents, currency,
            title, url, shop_name, condition, recorded_at
        ) VALUES (
            nextval('price_records_id_seq'),
            ?, ?, ?, ?, ?, ?, ?, ?, now()
        )
        """,
        [set_number, source, price_cents, currency, title, url, shop_name, condition],
    )


def get_all_items(conn: "DuckDBPyConnection") -> list[dict]:
    """Get all LEGO items with latest price from each source."""
    result = conn.execute("""
        WITH latest_shopee AS (
            SELECT set_number, price_cents, currency, url, recorded_at,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
            FROM price_records WHERE source = 'shopee'
        ),
        latest_toysrus AS (
            SELECT set_number, price_cents, currency, url, recorded_at,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
            FROM price_records WHERE source = 'toysrus'
        ),
        latest_bricklink_new AS (
            SELECT set_number, price_cents, currency, recorded_at,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
            FROM price_records WHERE source = 'bricklink_new'
        ),
        latest_bricklink_used AS (
            SELECT set_number, price_cents, currency, recorded_at,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
            FROM price_records WHERE source = 'bricklink_used'
        )
        SELECT
            li.set_number,
            li.title,
            li.theme,
            li.year_released,
            li.year_retired,
            li.retiring_soon,
            COALESCE(li.image_url, 'https://img.bricklink.com/ItemImage/SN/0/' || li.set_number || '-1.png') AS image_url,
            li.rrp_cents,
            li.rrp_currency,
            li.updated_at,
            li.minifig_count,
            s.price_cents AS shopee_price_cents,
            s.currency AS shopee_currency,
            s.url AS shopee_url,
            s.recorded_at AS shopee_last_seen,
            tr.price_cents AS toysrus_price_cents,
            tr.currency AS toysrus_currency,
            tr.url AS toysrus_url,
            tr.recorded_at AS toysrus_last_seen,
            bn.price_cents AS bricklink_new_cents,
            bn.currency AS bricklink_new_currency,
            bn.recorded_at AS bricklink_new_last_seen,
            bu.price_cents AS bricklink_used_cents,
            bu.currency AS bricklink_used_currency,
            bu.recorded_at AS bricklink_used_last_seen
        FROM lego_items li
        LEFT JOIN latest_shopee s ON s.set_number = li.set_number AND s.rn = 1
        LEFT JOIN latest_toysrus tr ON tr.set_number = li.set_number AND tr.rn = 1
        LEFT JOIN latest_bricklink_new bn ON bn.set_number = li.set_number AND bn.rn = 1
        LEFT JOIN latest_bricklink_used bu ON bu.set_number = li.set_number AND bu.rn = 1
        ORDER BY li.updated_at DESC
    """).fetchall()

    columns = [
        "set_number", "title", "theme", "year_released", "year_retired", "retiring_soon", "image_url",
        "rrp_cents", "rrp_currency", "updated_at", "minifig_count",
        "shopee_price_cents", "shopee_currency", "shopee_url", "shopee_last_seen",
        "toysrus_price_cents", "toysrus_currency", "toysrus_url", "toysrus_last_seen",
        "bricklink_new_cents", "bricklink_new_currency", "bricklink_new_last_seen",
        "bricklink_used_cents", "bricklink_used_currency", "bricklink_used_last_seen",
    ]
    return [dict(zip(columns, row)) for row in result]


def get_item_detail(conn: "DuckDBPyConnection", set_number: str) -> dict | None:
    """Get a single item with all its price records."""
    row = conn.execute(
        "SELECT * FROM lego_items WHERE set_number = ?", [set_number]
    ).fetchone()
    if not row:
        return None

    desc = conn.execute("SELECT * FROM lego_items LIMIT 0").description
    item = dict(zip([d[0] for d in desc], row))

    prices = conn.execute(
        """
        SELECT source, price_cents, currency, title, url,
               shop_name, condition, recorded_at
        FROM price_records
        WHERE set_number = ?
        ORDER BY recorded_at ASC
        """,
        [set_number],
    ).fetchall()

    price_columns = [
        "source", "price_cents", "currency", "title", "url",
        "shop_name", "condition", "recorded_at",
    ]
    item["prices"] = [dict(zip(price_columns, p)) for p in prices]
    return item
