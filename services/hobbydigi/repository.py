"""HobbyDigi repository functions for database operations."""

from datetime import datetime, timezone
from typing import Any

from services.hobbydigi.parser import HobbyDigiProduct
from services.items.repository import get_or_create_item, record_price
from services.items.set_number import extract_set_number
from services.pricing import parse_myr_cents as _parse_myr_cents


_UTC = timezone.utc


def upsert_product(conn: Any, product: HobbyDigiProduct) -> int:
    """Insert or update a HobbyDigi product.

    Also creates a price history record for tracking price changes.

    Returns:
        ID of the inserted/updated product.
    """
    now = datetime.now(tz=_UTC).isoformat()

    existing = conn.execute(
        "SELECT id FROM hobbydigi_products WHERE product_id = ?",
        [product.product_id],
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE hobbydigi_products
            SET name = ?,
                price_myr = ?,
                original_price_myr = ?,
                url = ?,
                image_url = ?,
                available = ?,
                rating_pct = ?,
                tags = ?,
                last_scraped_at = ?,
                updated_at = ?
            WHERE product_id = ?
            """,
            [
                product.name,
                product.price_myr,
                product.original_price_myr,
                product.url,
                product.image_url,
                product.available,
                product.rating_pct,
                ",".join(product.tags) if product.tags else None,
                now,
                now,
                product.product_id,
            ],
        )
        row_id = existing[0]
    else:
        row = conn.execute(
            """
            INSERT INTO hobbydigi_products (
                id, product_id, name, price_myr, original_price_myr,
                url, image_url, available, rating_pct, tags,
                last_scraped_at, created_at, updated_at
            ) VALUES (
                nextval('hobbydigi_products_id_seq'),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            RETURNING id
            """,
            [
                product.product_id,
                product.name,
                product.price_myr,
                product.original_price_myr,
                product.url,
                product.image_url,
                product.available,
                product.rating_pct,
                ",".join(product.tags) if product.tags else None,
                now,
                now,
                now,
            ],
        ).fetchone()
        row_id = row[0]

    _create_price_history(conn, product.product_id, product.price_myr, product.available)

    set_number = extract_set_number(product.name)
    if set_number and product.available:
        rrp_source = product.original_price_myr or product.price_myr
        rrp_cents = _parse_myr_cents(rrp_source)

        get_or_create_item(
            conn,
            set_number,
            title=product.name,
            image_url=product.image_url,
            rrp_cents=rrp_cents,
            rrp_currency="MYR",
        )
        price_cents = _parse_myr_cents(product.price_myr)
        if price_cents:
            record_price(
                conn,
                set_number,
                source="hobbydigi",
                price_cents=price_cents,
                currency="MYR",
                title=product.name,
                url=product.url,
            )

    return row_id


def _create_price_history(
    conn: Any,
    product_id: str,
    price_myr: str,
    available: bool,
) -> int:
    """Create a price history record."""
    now = datetime.now(tz=_UTC).isoformat()

    row = conn.execute(
        """
        INSERT INTO hobbydigi_price_history (
            id, product_id, price_myr, available, scraped_at
        ) VALUES (
            nextval('hobbydigi_price_history_id_seq'), ?, ?, ?, ?
        )
        RETURNING id
        """,
        [product_id, price_myr, available, now],
    ).fetchone()
    return row[0]


def upsert_products(
    conn: Any,
    products: tuple[HobbyDigiProduct, ...],
) -> int:
    """Bulk upsert products.

    Returns:
        Number of products upserted.
    """
    for product in products:
        upsert_product(conn, product)
    return len(products)


def get_all_products(
    conn: Any,
    available_only: bool = False,
) -> list[dict]:
    """Get all HobbyDigi products."""
    query = """
        SELECT product_id, name, price_myr, original_price_myr,
               url, image_url, available, rating_pct, tags,
               last_scraped_at
        FROM hobbydigi_products
    """
    if available_only:
        query += " WHERE available = TRUE"
    query += " ORDER BY name"

    results = conn.execute(query).fetchall()
    return [
        {
            "product_id": row[0],
            "name": row[1],
            "price_myr": row[2],
            "original_price_myr": row[3],
            "url": row[4],
            "image_url": row[5],
            "available": row[6],
            "rating_pct": row[7],
            "tags": row[8].split(",") if row[8] else [],
            "last_scraped_at": row[9],
        }
        for row in results
    ]
