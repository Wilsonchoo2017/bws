"""Load historical data from DuckDB into pandas DataFrames for backtesting."""

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def load_monthly_sales(conn: "DuckDBPyConnection") -> pd.DataFrame:
    """Load all monthly sales data.

    Returns DataFrame with columns:
        item_id, year, month, condition, times_sold, total_quantity,
        min_price, avg_price, max_price, currency
    """
    query = """
        SELECT
            item_id,
            year,
            month,
            condition,
            times_sold,
            total_quantity,
            min_price,
            avg_price,
            max_price,
            currency
        FROM bricklink_monthly_sales
        ORDER BY item_id, year, month
    """
    return conn.execute(query).df()


def load_item_metadata(conn: "DuckDBPyConnection") -> pd.DataFrame:
    """Load item metadata from lego_items joined with bricklink_items.

    Returns DataFrame with columns:
        item_id, set_number, title, theme, year_released, year_retired,
        parts_count, rrp_cents, rrp_currency
    """
    query = """
        SELECT
            bi.item_id,
            li.set_number,
            COALESCE(li.title, bi.title) AS title,
            li.theme,
            COALESCE(li.year_released, bi.year_released) AS year_released,
            li.year_retired,
            li.parts_count,
            li.rrp_cents,
            li.rrp_currency
        FROM bricklink_items bi
        LEFT JOIN lego_items li
            ON REPLACE(bi.item_id, '-1', '') = li.set_number
            OR bi.item_id = li.set_number || '-1'
        ORDER BY bi.item_id
    """
    return conn.execute(query).df()


def load_price_snapshots(conn: "DuckDBPyConnection") -> pd.DataFrame:
    """Load BrickLink price history snapshots.

    Returns DataFrame with parsed pricing box fields.
    """
    query = """
        SELECT
            item_id,
            scraped_at,
            six_month_new,
            six_month_used,
            current_new,
            current_used
        FROM bricklink_price_history
        ORDER BY item_id, scraped_at
    """
    return conn.execute(query).df()
