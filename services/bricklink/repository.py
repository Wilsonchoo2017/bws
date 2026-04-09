"""Bricklink repository functions for database operations.

Pure functions for CRUD operations on Bricklink data in the database.
"""

import json
from datetime import UTC, datetime, timedelta

from db.queries import parse_timestamp
from services.items.repository import get_or_create_item, record_price
from bws_types.models import (
    BricklinkData,
    BricklinkItem,
    Condition,
    MinifigureData,
    MinifigureInfo,
    MonthlySale,
    PriceData,
    PricingBox,
    WatchStatus,
)
from bws_types.price import Cents
from typing import Any



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


def get_item(conn: Any, item_id: str) -> BricklinkItem | None:
    """Get a Bricklink item by item_id.

    Args:
        conn: Database connection
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
    conn: Any,
    limit: int = 10,
) -> list[BricklinkItem]:
    """Get items that are due for scraping.

    Args:
        conn: Database connection
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


def upsert_item(conn: Any, data: BricklinkData) -> int:
    """Insert or update a Bricklink item.

    Args:
        conn: Database connection
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
                parts_count = ?,
                theme = ?,
                minifig_count = ?,
                dimensions = ?,
                has_instructions = ?,
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
                data.parts_count,
                data.theme,
                data.minifig_count,
                data.dimensions,
                data.has_instructions,
                now,
                (datetime.now(tz=_UTC) + timedelta(days=existing.scrape_interval_days)).isoformat(),
                now,
                data.item_id,
            ],
        )

        return existing.id

    # Insert new item
    scrape_interval = 7
    next_scrape = (datetime.now(tz=_UTC) + timedelta(days=scrape_interval)).isoformat()

    row = conn.execute(
        """
        INSERT INTO bricklink_items (
            id, item_id, item_type, title, weight, year_released, image_url,
            parts_count, theme, minifig_count, dimensions, has_instructions,
            watch_status, scrape_interval_days, last_scraped_at, next_scrape_at,
            created_at, updated_at
        ) VALUES (nextval('bricklink_items_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [
            data.item_id,
            data.item_type,
            data.title,
            data.weight,
            data.year_released,
            data.image_url,
            data.parts_count,
            data.theme,
            data.minifig_count,
            data.dimensions,
            data.has_instructions,
            "active",
            scrape_interval,
            now,
            next_scrape,
            now,
            now,
        ],
    ).fetchone()
    item_id = row[0]

    # Write to unified lego_items table
    set_number = data.item_id.split("-")[0]  # "75192-1" -> "75192"
    get_or_create_item(
        conn,
        set_number,
        title=data.title,
        theme=data.theme,
        year_released=data.year_released,
        image_url=data.image_url,
        minifig_count=data.minifig_count,
        dimensions=data.dimensions,
    )

    return item_id


def _has_recent_record(
    conn: Any,
    table: str,
    key_column: str,
    key_value: str,
    freshness: timedelta,
) -> bool:
    """Check if a recent record exists within the freshness window."""
    from db.queries import is_fresh

    # Table and column names are developer-controlled constants.
    sql = f"SELECT MAX(scraped_at) FROM {table} WHERE {key_column} = ?"  # noqa: S608
    try:
        row = conn.execute(sql, [key_value]).fetchone()
    except Exception:
        return False
    if not row or row[0] is None:
        return False
    return is_fresh(row[0], freshness)


def has_recent_pricing(
    conn: Any,
    item_id: str,
    freshness: timedelta,
) -> bool:
    """Check if a recent price history record exists within the freshness window."""
    return _has_recent_record(conn, "bricklink_price_history", "item_id", item_id, freshness)


def has_recent_minifig_pricing(
    conn: Any,
    minifig_id: str,
    freshness: timedelta,
) -> bool:
    """Check if a recent minifig price history record exists within the freshness window."""
    return _has_recent_record(conn, "minifig_price_history", "minifig_id", minifig_id, freshness)


def create_price_history(
    conn: Any,
    item_id: str,
    data: BricklinkData,
) -> int:
    """Create a price history record.

    Args:
        conn: Database connection
        item_id: Bricklink item ID
        data: BricklinkData with pricing info

    Returns:
        ID of the created record
    """
    now = datetime.now(tz=_UTC).isoformat()

    row = conn.execute(
        """
        INSERT INTO bricklink_price_history (
            id, item_id, six_month_new, six_month_used, current_new, current_used, scraped_at
        ) VALUES (nextval('bricklink_price_history_id_seq'), ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [
            item_id,
            _pricing_box_to_json(data.six_month_new),
            _pricing_box_to_json(data.six_month_used),
            _pricing_box_to_json(data.current_new),
            _pricing_box_to_json(data.current_used),
            now,
        ],
    ).fetchone()
    history_id = row[0]

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
    conn: Any,
    item_id: str,
    sales: list[MonthlySale],
) -> int:
    """Insert or update monthly sales records.

    Args:
        conn: Database connection
        item_id: Bricklink item ID
        sales: List of MonthlySale records

    Returns:
        Number of records upserted
    """
    now = datetime.now(tz=_UTC).isoformat()
    count = 0

    for sale in sales:
        params = [
            sale.times_sold,
            sale.total_quantity,
            sale.min_price.amount if sale.min_price else None,
            sale.max_price.amount if sale.max_price else None,
            sale.avg_price.amount if sale.avg_price else None,
            sale.currency,
            now,
        ]

        conn.execute(
            """INSERT INTO bricklink_monthly_sales (
                   item_id, year, month, condition, times_sold,
                   total_quantity, min_price, max_price, avg_price,
                   currency, scraped_at
               ) VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
               )
               ON CONFLICT (item_id, year, month, condition) DO UPDATE SET
                   times_sold = EXCLUDED.times_sold,
                   total_quantity = EXCLUDED.total_quantity,
                   min_price = EXCLUDED.min_price,
                   max_price = EXCLUDED.max_price,
                   avg_price = EXCLUDED.avg_price,
                   currency = EXCLUDED.currency,
                   scraped_at = EXCLUDED.scraped_at""",
            [item_id, sale.year, sale.month, sale.condition.value, *params],
        )

        count += 1

    return count


def get_price_history(
    conn: Any,
    item_id: str,
    limit: int = 10,
) -> list[dict]:
    """Get price history for an item.

    Args:
        conn: Database connection
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
    conn: Any,
    item_id: str,
    condition: Condition | None = None,
) -> list[MonthlySale]:
    """Get monthly sales for an item.

    Args:
        conn: Database connection
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
    conn: Any,
    watch_status: WatchStatus | None = None,
    limit: int = 100,
) -> list[BricklinkItem]:
    """List Bricklink items.

    Args:
        conn: Database connection
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


def upsert_minifigure(
    conn: Any,
    data: MinifigureData,
) -> int:
    """Insert or update a minifigure in the master catalog.

    Args:
        conn: Database connection
        data: MinifigureData with minifig info and prices

    Returns:
        ID of the inserted/updated minifigure
    """
    now = datetime.now(tz=_UTC).isoformat()
    existing = conn.execute(
        "SELECT id FROM minifigures WHERE minifig_id = ?",
        [data.minifig_id],
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE minifigures
            SET name = COALESCE(?, name),
                image_url = COALESCE(?, image_url),
                year_released = COALESCE(?, year_released),
                last_scraped_at = ?,
                updated_at = ?
            WHERE minifig_id = ?
            """,
            [data.name, data.image_url, data.year_released, now, now, data.minifig_id],
        )

        return existing[0]

    row = conn.execute(
        """
        INSERT INTO minifigures (id, minifig_id, name, image_url, year_released,
                                 last_scraped_at, created_at, updated_at)
        VALUES (nextval('minifigures_id_seq'), ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [data.minifig_id, data.name, data.image_url,
         data.year_released, now, now, now],
    ).fetchone()
    minifig_db_id = row[0]

    return minifig_db_id


def upsert_set_minifigures(
    conn: Any,
    set_item_id: str,
    minifigs: list[MinifigureInfo],
) -> int:
    """Insert or update the minifigure inventory for a set.

    Args:
        conn: Database connection
        set_item_id: Set item ID (e.g., "77256-1")
        minifigs: List of MinifigureInfo

    Returns:
        Number of records upserted
    """
    now = datetime.now(tz=_UTC).isoformat()
    count = 0

    for mf in minifigs:
        conn.execute(
            """
            INSERT INTO set_minifigures (set_item_id, minifig_id, quantity, scraped_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (set_item_id, minifig_id) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                scraped_at = EXCLUDED.scraped_at
            """,
            [set_item_id, mf.minifig_id, mf.quantity, now],
        )

        count += 1

    return count


def create_minifig_price_history(
    conn: Any,
    minifig_id: str,
    data: MinifigureData,
) -> int:
    """Create a price history record for a minifigure.

    Args:
        conn: Database connection
        minifig_id: Minifigure ID
        data: MinifigureData with pricing info

    Returns:
        ID of the created record
    """
    now = datetime.now(tz=_UTC).isoformat()

    row = conn.execute(
        """
        INSERT INTO minifig_price_history (
            id, minifig_id, six_month_new, six_month_used,
            current_new, current_used, scraped_at
        ) VALUES (nextval('minifig_price_history_id_seq'), ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [
            minifig_id,
            _pricing_box_to_json(data.six_month_new),
            _pricing_box_to_json(data.six_month_used),
            _pricing_box_to_json(data.current_new),
            _pricing_box_to_json(data.current_used),
            now,
        ],
    ).fetchone()
    history_id = row[0]

    return history_id


def get_set_minifigures(
    conn: Any,
    set_item_id: str,
) -> list[dict]:
    """Get minifigures for a set with their latest prices.

    Args:
        conn: Database connection
        set_item_id: Set item ID (e.g., "77256-1")

    Returns:
        List of dicts with minifig info and latest prices
    """
    results = conn.execute(
        """
        WITH latest_prices AS (
            SELECT minifig_id,
                   six_month_new, six_month_used, current_new, current_used,
                   scraped_at,
                   ROW_NUMBER() OVER (PARTITION BY minifig_id ORDER BY scraped_at DESC) AS rn
            FROM minifig_price_history
        )
        SELECT
            sm.minifig_id,
            m.name,
            m.image_url,
            sm.quantity,
            m.year_released,
            lp.current_new,
            lp.current_used,
            lp.six_month_new,
            lp.six_month_used,
            lp.scraped_at
        FROM set_minifigures sm
        JOIN minifigures m ON m.minifig_id = sm.minifig_id
        LEFT JOIN latest_prices lp ON lp.minifig_id = sm.minifig_id AND lp.rn = 1
        WHERE sm.set_item_id = ?
        ORDER BY sm.minifig_id
        """,
        [set_item_id],
    ).fetchall()

    minifigs = []
    for row in results:
        current_new = _json_to_pricing_box(row[5])
        current_used = _json_to_pricing_box(row[6])

        minifigs.append({
            "minifig_id": row[0],
            "name": row[1],
            "image_url": row[2],
            "quantity": row[3],
            "year_released": row[4],
            "current_new_avg_cents": (
                current_new.avg_price.amount if current_new and current_new.avg_price else None
            ),
            "current_used_avg_cents": (
                current_used.avg_price.amount if current_used and current_used.avg_price else None
            ),
            "currency": (
                current_new.avg_price.currency
                if current_new and current_new.avg_price
                else "USD"
            ),
            "last_scraped_at": str(row[9]) if row[9] else None,
        })

    return minifigs


def get_minifig_price_history(
    conn: Any,
    minifig_id: str,
    limit: int = 10,
) -> list[dict]:
    """Get price history for a minifigure.

    Args:
        conn: Database connection
        minifig_id: Minifigure ID
        limit: Maximum number of records

    Returns:
        List of price history records as dicts
    """
    results = conn.execute(
        """
        SELECT id, minifig_id, six_month_new, six_month_used,
               current_new, current_used, scraped_at
        FROM minifig_price_history
        WHERE minifig_id = ?
        ORDER BY scraped_at DESC
        LIMIT ?
        """,
        [minifig_id, limit],
    ).fetchall()

    return [
        {
            "id": row[0],
            "minifig_id": row[1],
            "six_month_new": _json_to_pricing_box(row[2]),
            "six_month_used": _json_to_pricing_box(row[3]),
            "current_new": _json_to_pricing_box(row[4]),
            "current_used": _json_to_pricing_box(row[5]),
            "scraped_at": parse_timestamp(row[6]),
        }
        for row in results
    ]


def get_set_minifig_value_history(
    conn: Any,
    set_item_id: str,
) -> list[dict]:
    """Get aggregated minifigure value history for a set.

    Sums current_new and current_used avg_price across all minifigs
    in the set, grouped by scrape timestamp (rounded to hour).

    Args:
        conn: Database connection
        set_item_id: Set item ID (e.g., "75192-1")

    Returns:
        List of dicts with scraped_at, total_new_cents, total_used_cents
    """
    results = conn.execute(
        """
        SELECT
            date_trunc('hour', mph.scraped_at) AS snapshot_hour,
            SUM(
                COALESCE(
                    CAST(mph.current_new::jsonb -> 'avg_price' ->> 'amount' AS INTEGER)
                    * sm.quantity,
                    0
                )
            ) AS total_new_cents,
            SUM(
                COALESCE(
                    CAST(mph.current_used::jsonb -> 'avg_price' ->> 'amount' AS INTEGER)
                    * sm.quantity,
                    0
                )
            ) AS total_used_cents
        FROM set_minifigures sm
        JOIN minifig_price_history mph ON mph.minifig_id = sm.minifig_id
        WHERE sm.set_item_id = ?
        GROUP BY date_trunc('hour', mph.scraped_at)
        ORDER BY snapshot_hour ASC
        """,
        [set_item_id],
    ).fetchall()

    return [
        {
            "scraped_at": str(row[0]) if row[0] else None,
            "total_new_cents": int(row[1]) if row[1] else 0,
            "total_used_cents": int(row[2]) if row[2] else 0,
        }
        for row in results
    ]


def update_watch_status(
    conn: Any,
    item_id: str,
    status: WatchStatus,
) -> bool:
    """Update the watch status of an item.

    Args:
        conn: Database connection
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
