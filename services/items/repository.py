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
    """Get all LEGO items with best/latest price from each retail source.

    Shopee: picks the cheapest price across all shops (best deal).
    ToysRUs, Mighty Utan: picks the latest price.
    BrickLink: picks the latest new/used price.
    """
    result = conn.execute("""
        WITH best_shopee AS (
            SELECT set_number, price_cents, currency, url, shop_name, recorded_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY set_number
                       ORDER BY price_cents ASC, recorded_at DESC
                   ) AS rn
            FROM price_records WHERE source = 'shopee'
        ),
        latest_toysrus AS (
            SELECT set_number, price_cents, currency, url, recorded_at,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
            FROM price_records WHERE source = 'toysrus'
        ),
        latest_mightyutan AS (
            SELECT set_number, price_cents, currency, url, recorded_at,
                   ROW_NUMBER() OVER (PARTITION BY set_number ORDER BY recorded_at DESC) AS rn
            FROM price_records WHERE source = 'mightyutan'
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
        ),
        shopee_listing_counts AS (
            SELECT set_number, COUNT(DISTINCT shop_name) AS shopee_shop_count
            FROM price_records
            WHERE source = 'shopee' AND shop_name IS NOT NULL
            GROUP BY set_number
        )
        SELECT
            li.set_number,
            li.title,
            li.theme,
            li.year_released,
            li.year_retired,
            li.retiring_soon,
            CASE
                WHEN ia.status = 'downloaded' THEN '/api/images/set/' || li.set_number
                ELSE COALESCE(li.image_url, 'https://img.bricklink.com/ItemImage/SN/0/' || li.set_number || '-1.png')
            END AS image_url,
            li.rrp_cents,
            li.rrp_currency,
            li.updated_at,
            li.minifig_count,
            li.dimensions,
            s.price_cents AS shopee_price_cents,
            s.currency AS shopee_currency,
            s.url AS shopee_url,
            s.shop_name AS shopee_shop_name,
            s.recorded_at AS shopee_last_seen,
            COALESCE(sc.shopee_shop_count, 0) AS shopee_shop_count,
            tr.price_cents AS toysrus_price_cents,
            tr.currency AS toysrus_currency,
            tr.url AS toysrus_url,
            tr.recorded_at AS toysrus_last_seen,
            mu.price_cents AS mightyutan_price_cents,
            mu.currency AS mightyutan_currency,
            mu.url AS mightyutan_url,
            mu.recorded_at AS mightyutan_last_seen,
            bn.price_cents AS bricklink_new_cents,
            bn.currency AS bricklink_new_currency,
            bn.recorded_at AS bricklink_new_last_seen,
            bu.price_cents AS bricklink_used_cents,
            bu.currency AS bricklink_used_currency,
            bu.recorded_at AS bricklink_used_last_seen
        FROM lego_items li
        LEFT JOIN best_shopee s ON s.set_number = li.set_number AND s.rn = 1
        LEFT JOIN shopee_listing_counts sc ON sc.set_number = li.set_number
        LEFT JOIN latest_toysrus tr ON tr.set_number = li.set_number AND tr.rn = 1
        LEFT JOIN latest_mightyutan mu ON mu.set_number = li.set_number AND mu.rn = 1
        LEFT JOIN latest_bricklink_new bn ON bn.set_number = li.set_number AND bn.rn = 1
        LEFT JOIN latest_bricklink_used bu ON bu.set_number = li.set_number AND bu.rn = 1
        LEFT JOIN image_assets ia ON ia.asset_type = 'set' AND ia.item_id = li.set_number
        ORDER BY li.updated_at DESC
    """).fetchall()  # noqa: S608

    columns = [
        "set_number", "title", "theme", "year_released", "year_retired", "retiring_soon", "image_url",
        "rrp_cents", "rrp_currency", "updated_at", "minifig_count", "dimensions",
        "shopee_price_cents", "shopee_currency", "shopee_url", "shopee_shop_name",
        "shopee_last_seen", "shopee_shop_count",
        "toysrus_price_cents", "toysrus_currency", "toysrus_url", "toysrus_last_seen",
        "mightyutan_price_cents", "mightyutan_currency", "mightyutan_url", "mightyutan_last_seen",
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

    # Resolve local image URL if downloaded
    ia_row = conn.execute(
        "SELECT status FROM image_assets WHERE asset_type = 'set' AND item_id = ?",
        [set_number],
    ).fetchone()
    if ia_row and ia_row[0] == "downloaded":
        item["image_url"] = f"/api/images/set/{set_number}"
    elif not item.get("image_url"):
        item["image_url"] = _bricklink_image_url(set_number)

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
