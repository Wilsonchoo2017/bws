"""Bricklink repository functions for database operations.

Pure functions for CRUD operations on Bricklink data in DuckDB.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from db.queries import get_next_id, parse_timestamp
from services.items.repository import get_or_create_item, record_price
from bws_types.models import (
    BricklinkData,
    BricklinkItem,
    Condition,
    MonthlySale,
    PriceData,
    PricingBox,
    WatchStatus,
)
from bws_types.price import Cents


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

# Ensure UTC is used
_UTC = UTC


def _pricing_box_to_json(box: PricingBox | None) -> str | None:
    """Convert PricingBox to JSON string for storage."""
    if box is None:
        return None

    data = {
        "times_sold": box.times_sold,
        "total_lots": box.total_lots,
        "total_qty": box.total_qty,
    }

    if box.min_price:
        data["min_price"] = {"currency": box.min_price.currency, "amount": box.min_price.amount}
    if box.avg_price:
        data["avg_price"] = {"currency": box.avg_price.currency, "amount": box.avg_price.amount}
    if box.qty_avg_price:
        data["qty_avg_price"] = {
            "currency": box.qty_avg_price.currency,
            "amount": box.qty_avg_price.amount,
        }
    if box.max_price:
        data["max_price"] = {"currency": box.max_price.currency, "amount": box.max_price.amount}

    return json.dumps(data)


def _json_to_pricing_box(json_str: str | None) -> PricingBox | None:
    """Convert JSON string to PricingBox."""
    if not json_str:
        return None

    data = json.loads(json_str) if isinstance(json_str, str) else json_str

    def parse_price(d: dict | None) -> PriceData | None:
        if not d:
            return None
        return PriceData(currency=d["currency"], amount=Cents(d["amount"]))

    return PricingBox(
        times_sold=data.get("times_sold"),
        total_lots=data.get("total_lots"),
        total_qty=data.get("total_qty"),
        min_price=parse_price(data.get("min_price")),
        avg_price=parse_price(data.get("avg_price")),
        qty_avg_price=parse_price(data.get("qty_avg_price")),
        max_price=parse_price(data.get("max_price")),
    )


def _row_to_bricklink_item(row: tuple) -> BricklinkItem:
    """Convert database row to BricklinkItem."""
    return BricklinkItem(
        id=row[0],
        item_id=row[1],
        item_type=row[2],
        title=row[3],
        weight=row[4],
        year_released=row[5],
        image_url=row[6],
        watch_status=WatchStatus(row[7]) if row[7] else WatchStatus.ACTIVE,
        scrape_interval_days=row[8] or 7,
        last_scraped_at=parse_timestamp(row[9]),
        next_scrape_at=parse_timestamp(row[10]),
        created_at=parse_timestamp(row[11]),
        updated_at=parse_timestamp(row[12]),
    )


def get_item(conn: "DuckDBPyConnection", item_id: str) -> BricklinkItem | None:
    """Get a Bricklink item by item_id.

    Args:
        conn: DuckDB connection
        item_id: Bricklink item ID (e.g., "75192-1")

    Returns:
        BricklinkItem or None if not found
    """
    result = conn.execute(
        """
        SELECT id, item_id, item_type, title, weight, year_released, image_url,
               watch_status, scrape_interval_days, last_scraped_at, next_scrape_at,
               created_at, updated_at
        FROM bricklink_items
        WHERE item_id = ?
        """,
        [item_id],
    ).fetchone()

    return _row_to_bricklink_item(result) if result else None


def get_items_for_scraping(
    conn: "DuckDBPyConnection",
    limit: int = 10,
) -> list[BricklinkItem]:
    """Get items that are due for scraping.

    Args:
        conn: DuckDB connection
        limit: Maximum number of items to return

    Returns:
        List of BricklinkItem objects due for scraping
    """
    now = datetime.now(tz=_UTC).isoformat()

    results = conn.execute(
        """
        SELECT id, item_id, item_type, title, weight, year_released, image_url,
               watch_status, scrape_interval_days, last_scraped_at, next_scrape_at,
               created_at, updated_at
        FROM bricklink_items
        WHERE watch_status = 'active'
          AND (next_scrape_at IS NULL OR next_scrape_at <= ?)
        ORDER BY next_scrape_at ASC NULLS FIRST
        LIMIT ?
        """,
        [now, limit],
    ).fetchall()

    return [_row_to_bricklink_item(row) for row in results]


def upsert_item(conn: "DuckDBPyConnection", data: BricklinkData) -> int:
    """Insert or update a Bricklink item.

    Args:
        conn: DuckDB connection
        data: BricklinkData from scraping

    Returns:
        ID of the inserted/updated item
    """
    now = datetime.now(tz=_UTC).isoformat()
    existing = get_item(conn, data.item_id)

    if existing:
        # Update existing item
        conn.execute(
            """
            UPDATE bricklink_items
            SET title = ?,
                weight = ?,
                year_released = ?,
                image_url = ?,
                last_scraped_at = ?,
                next_scrape_at = ?,
                updated_at = ?
            WHERE item_id = ?
            """,
            [
                data.title,
                data.weight,
                data.year_released,
                data.image_url,
                now,
                (datetime.now(tz=_UTC) + timedelta(days=existing.scrape_interval_days)).isoformat(),
                now,
                data.item_id,
            ],
        )
        return existing.id

    # Insert new item
    item_id = get_next_id(conn, "bricklink_items_id_seq")
    scrape_interval = 7
    next_scrape = (datetime.now(tz=_UTC) + timedelta(days=scrape_interval)).isoformat()

    conn.execute(
        """
        INSERT INTO bricklink_items (
            id, item_id, item_type, title, weight, year_released, image_url,
            watch_status, scrape_interval_days, last_scraped_at, next_scrape_at,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            item_id,
            data.item_id,
            data.item_type,
            data.title,
            data.weight,
            data.year_released,
            data.image_url,
            "active",
            scrape_interval,
            now,
            next_scrape,
            now,
            now,
        ],
    )

    # Write to unified lego_items table
    set_number = data.item_id.split("-")[0]  # "75192-1" -> "75192"
    get_or_create_item(
        conn,
        set_number,
        title=data.title,
        year_released=data.year_released,
        image_url=data.image_url,
    )

    return item_id


def create_price_history(
    conn: "DuckDBPyConnection",
    item_id: str,
    data: BricklinkData,
) -> int:
    """Create a price history record.

    Args:
        conn: DuckDB connection
        item_id: Bricklink item ID
        data: BricklinkData with pricing info

    Returns:
        ID of the created record
    """
    history_id = get_next_id(conn, "bricklink_price_history_id_seq")
    now = datetime.now(tz=_UTC).isoformat()

    conn.execute(
        """
        INSERT INTO bricklink_price_history (
            id, item_id, six_month_new, six_month_used, current_new, current_used, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            history_id,
            item_id,
            _pricing_box_to_json(data.six_month_new),
            _pricing_box_to_json(data.six_month_used),
            _pricing_box_to_json(data.current_new),
            _pricing_box_to_json(data.current_used),
            now,
        ],
    )

    # Write to unified price_records table
    set_number = item_id.split("-")[0]
    for box, condition in [
        (data.six_month_new, "new"),
        (data.six_month_used, "used"),
    ]:
        if box and box.avg_price:
            record_price(
                conn,
                set_number,
                source=f"bricklink_{condition}",
                price_cents=box.avg_price.amount,
                currency=box.avg_price.currency,
                condition=condition,
            )

    return history_id


def upsert_monthly_sales(
    conn: "DuckDBPyConnection",
    item_id: str,
    sales: list[MonthlySale],
) -> int:
    """Insert or update monthly sales records.

    Args:
        conn: DuckDB connection
        item_id: Bricklink item ID
        sales: List of MonthlySale records

    Returns:
        Number of records upserted
    """
    now = datetime.now(tz=_UTC).isoformat()
    count = 0

    for sale in sales:
        # Check if record exists
        existing = conn.execute(
            """
            SELECT id FROM bricklink_monthly_sales
            WHERE item_id = ? AND year = ? AND month = ? AND condition = ?
            """,
            [item_id, sale.year, sale.month, sale.condition.value],
        ).fetchone()

        if existing:
            # Update
            conn.execute(
                """
                UPDATE bricklink_monthly_sales
                SET times_sold = ?,
                    total_quantity = ?,
                    min_price = ?,
                    max_price = ?,
                    avg_price = ?,
                    currency = ?,
                    scraped_at = ?
                WHERE id = ?
                """,
                [
                    sale.times_sold,
                    sale.total_quantity,
                    sale.min_price.amount if sale.min_price else None,
                    sale.max_price.amount if sale.max_price else None,
                    sale.avg_price.amount if sale.avg_price else None,
                    sale.currency,
                    now,
                    existing[0],
                ],
            )
        else:
            # Insert
            sale_id = get_next_id(conn, "bricklink_monthly_sales_id_seq")
            conn.execute(
                """
                INSERT INTO bricklink_monthly_sales (
                    id, item_id, year, month, condition, times_sold, total_quantity,
                    min_price, max_price, avg_price, currency, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    sale_id,
                    item_id,
                    sale.year,
                    sale.month,
                    sale.condition.value,
                    sale.times_sold,
                    sale.total_quantity,
                    sale.min_price.amount if sale.min_price else None,
                    sale.max_price.amount if sale.max_price else None,
                    sale.avg_price.amount if sale.avg_price else None,
                    sale.currency,
                    now,
                ],
            )
        count += 1

    return count


def get_price_history(
    conn: "DuckDBPyConnection",
    item_id: str,
    limit: int = 10,
) -> list[dict]:
    """Get price history for an item.

    Args:
        conn: DuckDB connection
        item_id: Bricklink item ID
        limit: Maximum number of records to return

    Returns:
        List of price history records as dicts
    """
    results = conn.execute(
        """
        SELECT id, item_id, six_month_new, six_month_used, current_new, current_used, scraped_at
        FROM bricklink_price_history
        WHERE item_id = ?
        ORDER BY scraped_at DESC
        LIMIT ?
        """,
        [item_id, limit],
    ).fetchall()

    return [
        {
            "id": row[0],
            "item_id": row[1],
            "six_month_new": _json_to_pricing_box(row[2]),
            "six_month_used": _json_to_pricing_box(row[3]),
            "current_new": _json_to_pricing_box(row[4]),
            "current_used": _json_to_pricing_box(row[5]),
            "scraped_at": parse_timestamp(row[6]),
        }
        for row in results
    ]


def get_monthly_sales(
    conn: "DuckDBPyConnection",
    item_id: str,
    condition: Condition | None = None,
) -> list[MonthlySale]:
    """Get monthly sales for an item.

    Args:
        conn: DuckDB connection
        item_id: Bricklink item ID
        condition: Filter by condition (optional)

    Returns:
        List of MonthlySale records
    """
    query = """
        SELECT id, item_id, year, month, condition, times_sold, total_quantity,
               min_price, max_price, avg_price, currency, scraped_at
        FROM bricklink_monthly_sales
        WHERE item_id = ?
    """
    params: list = [item_id]

    if condition:
        query += " AND condition = ?"
        params.append(condition.value)

    query += " ORDER BY year DESC, month DESC"

    results = conn.execute(query, params).fetchall()

    return [
        MonthlySale(
            item_id=row[1],
            year=row[2],
            month=row[3],
            condition=Condition(row[4]),
            times_sold=row[5],
            total_quantity=row[6],
            min_price=PriceData(currency=row[10], amount=Cents(row[7])) if row[7] else None,
            max_price=PriceData(currency=row[10], amount=Cents(row[8])) if row[8] else None,
            avg_price=PriceData(currency=row[10], amount=Cents(row[9])) if row[9] else None,
            currency=row[10],
        )
        for row in results
    ]


def list_items(
    conn: "DuckDBPyConnection",
    watch_status: WatchStatus | None = None,
    limit: int = 100,
) -> list[BricklinkItem]:
    """List Bricklink items.

    Args:
        conn: DuckDB connection
        watch_status: Filter by watch status (optional)
        limit: Maximum number of items to return

    Returns:
        List of BricklinkItem objects
    """
    query = """
        SELECT id, item_id, item_type, title, weight, year_released, image_url,
               watch_status, scrape_interval_days, last_scraped_at, next_scrape_at,
               created_at, updated_at
        FROM bricklink_items
    """
    params: list = []

    if watch_status:
        query += " WHERE watch_status = ?"
        params.append(watch_status.value)

    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    results = conn.execute(query, params).fetchall()
    return [_row_to_bricklink_item(row) for row in results]


def update_watch_status(
    conn: "DuckDBPyConnection",
    item_id: str,
    status: WatchStatus,
) -> bool:
    """Update the watch status of an item.

    Args:
        conn: DuckDB connection
        item_id: Bricklink item ID
        status: New watch status

    Returns:
        True if item was updated, False if not found
    """
    now = datetime.now(tz=_UTC).isoformat()
    result = conn.execute(
        """
        UPDATE bricklink_items
        SET watch_status = ?, updated_at = ?
        WHERE item_id = ?
        """,
        [status.value, now, item_id],
    )
    return result.rowcount > 0 if hasattr(result, "rowcount") else True
