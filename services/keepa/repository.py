"""Persistence for Keepa snapshots."""

import json
import logging

from services.keepa.types import KeepaProductData
from typing import Any


logger = logging.getLogger("bws.keepa.repository")


def _series_to_json(points: tuple) -> str:
    """Serialize a tuple of KeepaDataPoint to JSON array of [date, value]."""
    from db.serialization import datapoints_to_json

    return datapoints_to_json(points)


def save_keepa_snapshot(
    conn: Any, data: KeepaProductData
) -> int:
    """Insert a Keepa snapshot row and return the new row ID."""
    row_id = conn.execute(
        "SELECT nextval('keepa_snapshots_id_seq')"
    ).fetchone()[0]

    try:
        conn.execute(
            """
            INSERT INTO keepa_snapshots (
                id, set_number, asin, title, keepa_url, scraped_at,
                current_buy_box_cents, current_amazon_cents, current_new_cents,
                lowest_ever_cents, highest_ever_cents,
                amazon_price_json, new_price_json, new_3p_fba_json,
                new_3p_fbm_json, used_price_json, used_like_new_json,
                buy_box_json, list_price_json, warehouse_deals_json,
                collectible_json, sales_rank_json,
                rating, review_count, tracking_users, chart_screenshot_path
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?
            )
            """,
            [
                row_id,
                data.set_number,
                data.asin,
                data.title,
                data.keepa_url,
                data.scraped_at,
                data.current_buy_box_cents,
                data.current_amazon_cents,
                data.current_new_cents,
                data.lowest_ever_cents,
                data.highest_ever_cents,
                _series_to_json(data.amazon_price),
                _series_to_json(data.new_price),
                _series_to_json(data.new_3p_fba),
                _series_to_json(data.new_3p_fbm),
                _series_to_json(data.used_price),
                _series_to_json(data.used_like_new),
                _series_to_json(data.buy_box),
                _series_to_json(data.list_price),
                _series_to_json(data.warehouse_deals),
                _series_to_json(data.collectible),
                _series_to_json(data.sales_rank),
                data.rating,
                data.review_count,
                data.tracking_users,
                data.chart_screenshot_path,
            ],
        )
    except Exception:
        logger.error(
            "Failed to insert keepa_snapshot for %s (id=%d)",
            data.set_number,
            row_id,
            exc_info=True,
        )
        raise

    logger.info("Saved Keepa snapshot id=%d for %s", row_id, data.set_number)
    return row_id


def record_keepa_prices(
    conn: Any, data: KeepaProductData
) -> None:
    """Write current Keepa prices to the unified price_records table."""
    from services.items.repository import record_price

    if data.current_amazon_cents:
        record_price(
            conn,
            set_number=data.set_number,
            source="keepa_amazon",
            price_cents=data.current_amazon_cents,
            currency="USD",
            title=data.title,
            url=data.keepa_url,
        )

    if data.current_new_cents:
        record_price(
            conn,
            set_number=data.set_number,
            source="keepa_new",
            price_cents=data.current_new_cents,
            currency="USD",
            title=data.title,
            url=data.keepa_url,
        )

    if data.current_buy_box_cents:
        record_price(
            conn,
            set_number=data.set_number,
            source="keepa_buy_box",
            price_cents=data.current_buy_box_cents,
            currency="USD",
            title=data.title,
            url=data.keepa_url,
        )


def get_latest_keepa_snapshot(
    conn: Any, set_number: str
) -> dict | None:
    """Get the most recent Keepa snapshot for a set."""
    from db.queries import get_latest_row

    return get_latest_row(conn, "keepa_snapshots", key_value=set_number)
