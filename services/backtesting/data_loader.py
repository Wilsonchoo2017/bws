"""Load historical data from DuckDB into pandas DataFrames for backtesting."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MinifigSetData:
    """Minifigure analysis data for a single set."""

    total_value_cents: int
    exclusive_count: int
    total_count: int
    exclusive_value_cents: int
    cheapest_alternative_item_id: str | None
    cheapest_alternative_price_cents: int | None


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
            COALESCE(li.retiring_soon, FALSE) AS retiring_soon,
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


def load_minifig_data(conn: "DuckDBPyConnection") -> dict[str, MinifigSetData]:
    """Load minifigure analysis data per set.

    For each set computes:
    - total_value_cents: sum of all minifig values in the set
    - exclusive_count: minifigs that appear in only this set
    - total_count: total distinct minifigs in the set
    - exclusive_value_cents: value of exclusive minifigs only
    - cheapest_alternative: if shared minifigs exist, the cheapest other
      set that contains any of the same minifigs (arbitrage signal)

    Returns dict mapping set_item_id to MinifigSetData.
    """
    try:
        # Count how many sets each minifig appears in
        appearance_query = """
            SELECT minifig_id, COUNT(DISTINCT set_item_id) AS set_count
            FROM set_minifigures
            GROUP BY minifig_id
        """
        appearances = conn.execute(appearance_query).df()
        if appearances.empty:
            return {}

        exclusivity = dict(
            zip(appearances["minifig_id"], appearances["set_count"])
        )

        # Get latest price per minifig
        price_query = """
            SELECT DISTINCT ON (minifig_id)
                minifig_id,
                JSON_EXTRACT(current_new, '$.avg_price.amount')::INTEGER
                    AS avg_price_cents
            FROM minifig_price_history
            ORDER BY minifig_id, scraped_at DESC
        """
        prices_df = conn.execute(price_query).df()
        minifig_prices: dict[str, int] = dict(
            zip(prices_df["minifig_id"], prices_df["avg_price_cents"])
        ) if not prices_df.empty else {}

        # Get all set-minifig links
        links_query = """
            SELECT set_item_id, minifig_id, quantity
            FROM set_minifigures
        """
        links = conn.execute(links_query).df()
        if links.empty:
            return {}

        # Get latest entry prices for sets (for cheapest alternative calc)
        set_prices_query = """
            SELECT item_id,
                   JSON_EXTRACT(current_new, '$.avg_price.amount')::INTEGER
                       AS price_cents
            FROM (
                SELECT DISTINCT ON (item_id) item_id, current_new
                FROM bricklink_price_history
                ORDER BY item_id, scraped_at DESC
            )
            WHERE price_cents > 0
        """
        try:
            sp_df = conn.execute(set_prices_query).df()
            set_entry_prices: dict[str, int] = dict(
                zip(sp_df["item_id"], sp_df["price_cents"])
            ) if not sp_df.empty else {}
        except Exception:
            set_entry_prices = {}

        # Build per-set data
        result: dict[str, MinifigSetData] = {}
        grouped = links.groupby("set_item_id")

        for set_id, group in grouped:
            total_value = 0
            exclusive_value = 0
            exclusive_count = 0
            total_count = 0
            shared_minifig_ids: list[str] = []

            for _, row in group.iterrows():
                mfig_id = row["minifig_id"]
                qty = int(row["quantity"])
                price = minifig_prices.get(mfig_id, 0)
                is_exclusive = exclusivity.get(mfig_id, 1) == 1

                total_count += 1
                total_value += qty * price

                if is_exclusive:
                    exclusive_count += 1
                    exclusive_value += qty * price
                else:
                    shared_minifig_ids.append(mfig_id)

            if total_value <= 0:
                continue

            # Find cheapest alternative set for shared minifigs
            cheapest_alt_id = None
            cheapest_alt_price = None
            if shared_minifig_ids:
                alt_sets = links[
                    (links["minifig_id"].isin(shared_minifig_ids))
                    & (links["set_item_id"] != set_id)
                ]["set_item_id"].unique()
                for alt_id in alt_sets:
                    alt_price = set_entry_prices.get(str(alt_id))
                    if alt_price and (
                        cheapest_alt_price is None
                        or alt_price < cheapest_alt_price
                    ):
                        cheapest_alt_id = str(alt_id)
                        cheapest_alt_price = alt_price

            result[str(set_id)] = MinifigSetData(
                total_value_cents=total_value,
                exclusive_count=exclusive_count,
                total_count=total_count,
                exclusive_value_cents=exclusive_value,
                cheapest_alternative_item_id=cheapest_alt_id,
                cheapest_alternative_price_cents=cheapest_alt_price,
            )

        return result

    except Exception:
        logger.warning("Minifig data unavailable", exc_info=True)
        return {}


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
