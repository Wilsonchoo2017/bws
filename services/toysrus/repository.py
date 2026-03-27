"""ToysRUs repository functions for database operations.

Pure functions for CRUD operations on ToysRUs data in DuckDB.
"""


from datetime import datetime, timezone
from typing import TYPE_CHECKING

from db.queries import get_next_id
from services.toysrus.parser import ToysRUsProduct


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


_UTC = timezone.utc


def upsert_product(conn: "DuckDBPyConnection", product: ToysRUsProduct) -> int:
    """Insert or update a ToysRUs product.

    Also creates a price history record for tracking price changes.

    Returns:
        ID of the inserted/updated product.
    """
    now = datetime.now(tz=_UTC).isoformat()

    existing = conn.execute(
        "SELECT id FROM toysrus_products WHERE sku = ?",
        [product.sku],
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE toysrus_products
            SET name = ?,
                price_myr = ?,
                brand = ?,
                category = ?,
                age_range = ?,
                url = ?,
                image_url = ?,
                available = ?,
                last_scraped_at = ?,
                updated_at = ?
            WHERE sku = ?
            """,
            [
                product.name,
                product.price_myr,
                product.brand,
                product.category,
                product.age_range,
                product.url,
                product.image_url,
                product.available,
                now,
                now,
                product.sku,
            ],
        )
        product_id = existing[0]
    else:
        product_id = get_next_id(conn, "toysrus_products_id_seq")
        conn.execute(
            """
            INSERT INTO toysrus_products (
                id, sku, name, price_myr, brand, category, age_range,
                url, image_url, available, last_scraped_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                product_id,
                product.sku,
                product.name,
                product.price_myr,
                product.brand,
                product.category,
                product.age_range,
                product.url,
                product.image_url,
                product.available,
                now,
                now,
                now,
            ],
        )

    # Always record price history
    _create_price_history(conn, product.sku, product.price_myr, product.available)

    return product_id


def _create_price_history(
    conn: "DuckDBPyConnection",
    sku: str,
    price_myr: str,
    available: bool,
) -> int:
    """Create a price history record."""
    history_id = get_next_id(conn, "toysrus_price_history_id_seq")
    now = datetime.now(tz=_UTC).isoformat()

    conn.execute(
        """
        INSERT INTO toysrus_price_history (id, sku, price_myr, available, scraped_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [history_id, sku, price_myr, available, now],
    )

    return history_id


def upsert_products(
    conn: "DuckDBPyConnection",
    products: tuple[ToysRUsProduct, ...],
) -> int:
    """Bulk upsert products.

    Returns:
        Number of products upserted.
    """
    count = 0
    for product in products:
        upsert_product(conn, product)
        count += 1
    return count


def get_all_products(
    conn: "DuckDBPyConnection",
    available_only: bool = False,
) -> list[dict]:
    """Get all ToysRUs products.

    Returns:
        List of product dicts.
    """
    query = """
        SELECT sku, name, price_myr, brand, category, age_range,
               url, image_url, available, last_scraped_at
        FROM toysrus_products
    """
    if available_only:
        query += " WHERE available = TRUE"
    query += " ORDER BY name"

    results = conn.execute(query).fetchall()
    return [
        {
            "sku": row[0],
            "name": row[1],
            "price_myr": row[2],
            "brand": row[3],
            "category": row[4],
            "age_range": row[5],
            "url": row[6],
            "image_url": row[7],
            "available": row[8],
            "last_scraped_at": row[9],
        }
        for row in results
    ]
