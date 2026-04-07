"""Mighty Utan repository functions for database operations.

Pure functions for CRUD operations on Mighty Utan data in the database.
"""

from datetime import datetime, timezone

from db.pg.writes import (
    _get_pg,
    pg_insert_mightyutan_price_history,
    pg_upsert_mightyutan_product,
)
from db.queries import get_next_id
from services.items.repository import get_or_create_item, record_price
from services.items.set_number import extract_set_number
from services.mightyutan.parser import MightyUtanProduct
from services.pricing import parse_myr_cents as _parse_myr_cents
from typing import Any



_UTC = timezone.utc


def upsert_product(conn: Any, product: MightyUtanProduct) -> int:
    """Insert or update a Mighty Utan product.

    Also creates a price history record for tracking price changes.

    Returns:
        ID of the inserted/updated product.
    """
    now = datetime.now(tz=_UTC).isoformat()

    existing = conn.execute(
        "SELECT id FROM mightyutan_products WHERE sku = ?",
        [product.sku],
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE mightyutan_products
            SET name = ?,
                price_myr = ?,
                original_price_myr = ?,
                url = ?,
                image_url = ?,
                available = ?,
                quantity = ?,
                total_sold = ?,
                rating = ?,
                rating_count = ?,
                last_scraped_at = ?,
                updated_at = ?
            WHERE sku = ?
            """,
            [
                product.name,
                product.price_myr,
                product.original_price_myr,
                product.url,
                product.image_url,
                product.available,
                product.quantity,
                product.total_sold,
                product.rating,
                product.rating_count,
                now,
                now,
                product.sku,
            ],
        )
        product_id = existing[0]

        # Write to Postgres
        pg = _get_pg(conn)
        if pg is not None:
            pg_upsert_mightyutan_product(
                pg,
                sku=product.sku,
                name=product.name,
                price_myr=product.price_myr,
                original_price_myr=product.original_price_myr,
                url=product.url,
                image_url=product.image_url,
                available=product.available,
                quantity=product.quantity,
                total_sold=product.total_sold,
                rating=product.rating,
                rating_count=product.rating_count,
                last_scraped_at=now,
                updated_at=now,
            )
    else:
        product_id = get_next_id(conn, "mightyutan_products_id_seq")
        conn.execute(
            """
            INSERT INTO mightyutan_products (
                id, sku, name, price_myr, original_price_myr,
                url, image_url, available, quantity, total_sold,
                rating, rating_count,
                last_scraped_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                product_id,
                product.sku,
                product.name,
                product.price_myr,
                product.original_price_myr,
                product.url,
                product.image_url,
                product.available,
                product.quantity,
                product.total_sold,
                product.rating,
                product.rating_count,
                now,
                now,
                now,
            ],
        )

        # Write to Postgres
        pg = _get_pg(conn)
        if pg is not None:
            pg_upsert_mightyutan_product(
                pg,
                sku=product.sku,
                name=product.name,
                price_myr=product.price_myr,
                original_price_myr=product.original_price_myr,
                url=product.url,
                image_url=product.image_url,
                available=product.available,
                quantity=product.quantity,
                total_sold=product.total_sold,
                rating=product.rating,
                rating_count=product.rating_count,
                last_scraped_at=now,
                created_at=now,
                updated_at=now,
            )

    _create_price_history(conn, product.sku, product.price_myr, product.available)

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
                source="mightyutan",
                price_cents=price_cents,
                currency="MYR",
                title=product.name,
                url=product.url,
            )

    return product_id


def _create_price_history(
    conn: Any,
    sku: str,
    price_myr: str,
    available: bool,
) -> int:
    """Create a price history record."""
    history_id = get_next_id(conn, "mightyutan_price_history_id_seq")
    now = datetime.now(tz=_UTC).isoformat()

    conn.execute(
        """
        INSERT INTO mightyutan_price_history (id, sku, price_myr, available, scraped_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [history_id, sku, price_myr, available, now],
    )

    # Write to Postgres
    pg = _get_pg(conn)
    if pg is not None:
        pg_insert_mightyutan_price_history(
            pg,
            sku=sku,
            price_myr=price_myr,
            available=available,
            scraped_at=now,
        )

    return history_id


def upsert_products(
    conn: Any,
    products: tuple[MightyUtanProduct, ...],
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
    """Get all Mighty Utan products.

    Returns:
        List of product dicts.
    """
    query = """
        SELECT sku, name, price_myr, original_price_myr,
               url, image_url, available, quantity, total_sold,
               rating, rating_count, last_scraped_at
        FROM mightyutan_products
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
            "original_price_myr": row[3],
            "url": row[4],
            "image_url": row[5],
            "available": row[6],
            "quantity": row[7],
            "total_sold": row[8],
            "rating": row[9],
            "rating_count": row[10],
            "last_scraped_at": row[11],
        }
        for row in results
    ]
