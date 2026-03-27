"""DuckDB persistence for Shopee scraped products."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from services.shopee.parser import ShopeeProduct

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def _parse_price_cents(price_display: str) -> int | None:
    """Parse 'RM1,234.56' to cents (123456)."""
    match = re.search(r"RM([\d,]+\.?\d*)", price_display)
    if not match:
        return None
    cleaned = match.group(1).replace(",", "")
    try:
        return int(float(cleaned) * 100)
    except ValueError:
        return None


def upsert_products(
    conn: "DuckDBPyConnection",
    products: tuple[ShopeeProduct, ...],
    source_url: str,
) -> int:
    """Insert or update Shopee products in the database.

    Uses product_url as the unique key for upserts.

    Args:
        conn: DuckDB connection
        products: Tuple of ShopeeProduct to save
        source_url: The URL that was scraped (shop/collection page)

    Returns:
        Number of products saved
    """
    saved = 0
    for product in products:
        if not product.product_url:
            continue

        price_cents = _parse_price_cents(product.price_display)

        conn.execute(
            """
            INSERT INTO shopee_products (
                id, title, price_display, price_cents,
                sold_count, rating, shop_name,
                product_url, image_url, source_url, scraped_at
            ) VALUES (
                nextval('shopee_products_id_seq'),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
            )
            ON CONFLICT (product_url) DO UPDATE SET
                title = EXCLUDED.title,
                price_display = EXCLUDED.price_display,
                price_cents = EXCLUDED.price_cents,
                sold_count = EXCLUDED.sold_count,
                rating = EXCLUDED.rating,
                shop_name = EXCLUDED.shop_name,
                image_url = EXCLUDED.image_url,
                source_url = EXCLUDED.source_url,
                scraped_at = CURRENT_TIMESTAMP
            """,
            [
                product.title,
                product.price_display,
                price_cents,
                product.sold_count,
                product.rating,
                product.shop_name,
                product.product_url,
                product.image_url,
                source_url,
            ],
        )
        saved += 1

    return saved


def record_scrape(
    conn: "DuckDBPyConnection",
    source_url: str,
    items_found: int,
    success: bool,
    error: str | None = None,
) -> None:
    """Record a scrape attempt in the history table."""
    conn.execute(
        """
        INSERT INTO shopee_scrape_history (
            id, source_url, items_found, success, error, scraped_at
        ) VALUES (
            nextval('shopee_scrape_history_id_seq'),
            ?, ?, ?, ?, CURRENT_TIMESTAMP
        )
        """,
        [source_url, items_found, success, error],
    )


def get_all_products(conn: "DuckDBPyConnection") -> list[dict]:
    """Get all Shopee products ordered by most recent scrape."""
    result = conn.execute(
        """
        SELECT
            title, price_display, price_cents,
            sold_count, rating, shop_name,
            product_url, image_url, source_url, scraped_at
        FROM shopee_products
        ORDER BY scraped_at DESC
        """
    ).fetchall()

    columns = [
        "title", "price_display", "price_cents",
        "sold_count", "rating", "shop_name",
        "product_url", "image_url", "source_url", "scraped_at",
    ]
    return [dict(zip(columns, row)) for row in result]
