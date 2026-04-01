"""Target variable computation for ML pipeline.

Computes post-retirement returns: (transacted_price / rrp_usd) - 1
at 12, 24, and 36 month horizons.

Primary source: BrickLink monthly sales avg_price (USD).
Fallback: BrickEconomy value_chart_json time series or value_new_cents
from snapshots (since BrickLink only keeps 6 months of data).
"""

import json
import logging
from typing import TYPE_CHECKING

import pandas as pd

from config.ml import MLPipelineConfig, TARGET_SMOOTHING_WINDOW

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger(__name__)


def compute_retirement_returns(
    conn: "DuckDBPyConnection",
    config: MLPipelineConfig | None = None,
) -> pd.DataFrame:
    """Compute post-retirement returns for all retired sets.

    For each set with a known retired_date and rrp_usd_cents:
    1. Try BrickLink monthly avg_price at retirement + horizon months
    2. Fall back to BrickEconomy value_chart_json time series
    3. Fall back to BrickEconomy value_new_cents from nearest snapshot

    Returns DataFrame with columns:
        set_number, year_retired, retired_date, rrp_usd_cents,
        avg_price_12m, avg_price_24m, avg_price_36m,
        return_12m, return_24m, return_36m,
        profitable_12m, profitable_24m, profitable_36m,
        price_source_12m, price_source_24m, price_source_36m
    """
    if config is None:
        config = MLPipelineConfig()

    # Load retired sets with RRP
    sets_df = _load_retired_sets(conn)
    if sets_df.empty:
        logger.warning("No retired sets with RRP found")
        return pd.DataFrame()

    # Load BrickLink monthly sales
    bricklink_prices = _load_bricklink_monthly_prices(conn)

    # Load BrickEconomy value chart time series
    be_value_charts = _load_brickeconomy_value_charts(conn)

    # Load BrickEconomy snapshot values (last resort)
    be_snapshots = _load_brickeconomy_snapshot_values(conn)

    rows: list[dict] = []
    half_window = TARGET_SMOOTHING_WINDOW // 2

    for _, item in sets_df.iterrows():
        set_number = item["set_number"]
        rrp_usd = item["rrp_usd_cents"]
        retired_year = item["retired_year"]
        retired_month = item["retired_month"]

        if rrp_usd is None or rrp_usd <= 0:
            continue

        row: dict = {
            "set_number": set_number,
            "year_retired": item["year_retired"],
            "retired_date": item["retired_date"],
            "rrp_usd_cents": rrp_usd,
        }

        item_id = _set_number_to_item_id(set_number)

        for horizon in config.target_horizons:
            target_year, target_month = _add_months(
                retired_year, retired_month, horizon
            )

            avg_price, source = _get_price_at_horizon(
                set_number=set_number,
                item_id=item_id,
                target_year=target_year,
                target_month=target_month,
                half_window=half_window,
                bricklink_prices=bricklink_prices,
                be_value_charts=be_value_charts,
                be_snapshots=be_snapshots,
            )

            col = f"{horizon}m"
            row[f"avg_price_{col}"] = avg_price
            row[f"price_source_{col}"] = source

            if avg_price is not None and avg_price > 0:
                ret = (avg_price / rrp_usd) - 1.0
                row[f"return_{col}"] = ret
                row[f"profitable_{col}"] = ret > config.binary_threshold
            else:
                row[f"return_{col}"] = None
                row[f"profitable_{col}"] = None

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def _load_retired_sets(conn: "DuckDBPyConnection") -> pd.DataFrame:
    """Load retired sets with RRP in USD."""
    query = """
        SELECT
            li.set_number,
            li.year_retired,
            li.retired_date,
            be.rrp_usd_cents
        FROM lego_items li
        JOIN (
            SELECT
                set_number,
                rrp_usd_cents,
                ROW_NUMBER() OVER (
                    PARTITION BY set_number ORDER BY scraped_at DESC
                ) AS rn
            FROM brickeconomy_snapshots
            WHERE rrp_usd_cents IS NOT NULL AND rrp_usd_cents > 0
        ) be ON be.set_number = li.set_number AND be.rn = 1
        WHERE li.year_retired IS NOT NULL
        ORDER BY li.set_number
    """
    df = conn.execute(query).df()
    if df.empty:
        return df

    # Parse retired_date (ISO "YYYY-MM") into year/month components
    df["retired_year"] = None
    df["retired_month"] = None

    for idx, row in df.iterrows():
        rd = row["retired_date"]
        yr = row["year_retired"]
        if rd and isinstance(rd, str) and "-" in rd:
            parts = rd.split("-")
            df.at[idx, "retired_year"] = int(parts[0])
            df.at[idx, "retired_month"] = int(parts[1])
        elif yr:
            # Fall back to year_retired with month=12 (end of year)
            df.at[idx, "retired_year"] = int(yr)
            df.at[idx, "retired_month"] = 12

    # Drop rows where we couldn't determine retirement timing
    df = df.dropna(subset=["retired_year", "retired_month"])
    df["retired_year"] = df["retired_year"].astype(int)
    df["retired_month"] = df["retired_month"].astype(int)
    return df


def _load_bricklink_monthly_prices(conn: "DuckDBPyConnection") -> pd.DataFrame:
    """Load BrickLink monthly sales with avg_price in USD cents."""
    query = """
        SELECT
            item_id,
            year,
            month,
            avg_price
        FROM bricklink_monthly_sales
        WHERE condition = 'N'
            AND avg_price IS NOT NULL
            AND avg_price > 0
        ORDER BY item_id, year, month
    """
    return conn.execute(query).df()


def _load_brickeconomy_value_charts(
    conn: "DuckDBPyConnection",
) -> dict[str, list[tuple[int, int, int]]]:
    """Load BrickEconomy value_chart_json parsed into (year, month, cents).

    Returns dict mapping set_number -> sorted list of (year, month, price_cents).
    """
    query = """
        SELECT set_number, value_chart_json
        FROM (
            SELECT
                set_number,
                value_chart_json,
                ROW_NUMBER() OVER (
                    PARTITION BY set_number ORDER BY scraped_at DESC
                ) AS rn
            FROM brickeconomy_snapshots
            WHERE value_chart_json IS NOT NULL
        )
        WHERE rn = 1
    """
    df = conn.execute(query).df()
    result: dict[str, list[tuple[int, int, int]]] = {}

    for _, row in df.iterrows():
        chart_raw = row["value_chart_json"]
        if not chart_raw:
            continue

        try:
            if isinstance(chart_raw, str):
                chart = json.loads(chart_raw)
            else:
                chart = chart_raw

            points: list[tuple[int, int, int]] = []
            for entry in chart:
                # Format: ["YYYY-MM-DD", price_cents] or [date_str, price]
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                date_str = str(entry[0])
                price = int(entry[1])
                if "-" in date_str:
                    parts = date_str.split("-")
                    points.append((int(parts[0]), int(parts[1]), price))

            if points:
                points.sort()
                result[row["set_number"]] = points
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    return result


def _load_brickeconomy_snapshot_values(
    conn: "DuckDBPyConnection",
) -> pd.DataFrame:
    """Load BrickEconomy snapshot value_new_cents over time."""
    query = """
        SELECT
            set_number,
            scraped_at,
            value_new_cents
        FROM brickeconomy_snapshots
        WHERE value_new_cents IS NOT NULL AND value_new_cents > 0
        ORDER BY set_number, scraped_at
    """
    return conn.execute(query).df()


def _get_price_at_horizon(
    *,
    set_number: str,
    item_id: str,
    target_year: int,
    target_month: int,
    half_window: int,
    bricklink_prices: pd.DataFrame,
    be_value_charts: dict[str, list[tuple[int, int, int]]],
    be_snapshots: pd.DataFrame,
) -> tuple[int | None, str]:
    """Get the average transacted price at a target year/month.

    Tries sources in order:
    1. BrickLink monthly avg_price (3-month window average)
    2. BrickEconomy value_chart_json time series
    3. BrickEconomy value_new_cents from snapshots

    Returns (price_cents, source_name) or (None, "none").
    """
    # 1. Try BrickLink
    price = _bricklink_price_at(
        bricklink_prices, item_id, target_year, target_month, half_window
    )
    if price is not None:
        return price, "bricklink"

    # 2. Try BrickEconomy value chart
    price = _be_chart_price_at(
        be_value_charts, set_number, target_year, target_month, half_window
    )
    if price is not None:
        return price, "brickeconomy_chart"

    # 3. Try BrickEconomy snapshots
    price = _be_snapshot_price_at(
        be_snapshots, set_number, target_year, target_month, half_window
    )
    if price is not None:
        return price, "brickeconomy_snapshot"

    return None, "none"


def _bricklink_price_at(
    df: pd.DataFrame,
    item_id: str,
    target_year: int,
    target_month: int,
    half_window: int,
) -> int | None:
    """Get avg BrickLink price in a window around target month."""
    item_df = df[df["item_id"] == item_id]
    if item_df.empty:
        return None

    prices: list[int] = []
    for offset in range(-half_window, half_window + 1):
        y, m = _add_months(target_year, target_month, offset)
        match = item_df[(item_df["year"] == y) & (item_df["month"] == m)]
        if not match.empty:
            p = match.iloc[0]["avg_price"]
            if p and p > 0:
                prices.append(int(p))

    if prices:
        return int(sum(prices) / len(prices))
    return None


def _be_chart_price_at(
    charts: dict[str, list[tuple[int, int, int]]],
    set_number: str,
    target_year: int,
    target_month: int,
    half_window: int,
) -> int | None:
    """Get price from BrickEconomy value chart near target month."""
    points = charts.get(set_number)
    if not points:
        return None

    # Collect prices within the window
    prices: list[int] = []
    for offset in range(-half_window, half_window + 1):
        y, m = _add_months(target_year, target_month, offset)
        for py, pm, price in points:
            if py == y and pm == m:
                prices.append(price)
                break

    if prices:
        return int(sum(prices) / len(prices))

    # If exact months not found, find nearest point within 3 months
    target_abs = target_year * 12 + target_month
    nearest_price = None
    nearest_dist = 999
    for py, pm, price in points:
        dist = abs((py * 12 + pm) - target_abs)
        if dist < nearest_dist and dist <= 3:
            nearest_dist = dist
            nearest_price = price

    return nearest_price


def _be_snapshot_price_at(
    df: pd.DataFrame,
    set_number: str,
    target_year: int,
    target_month: int,
    half_window: int,
) -> int | None:
    """Get value_new_cents from BrickEconomy snapshots near target date."""
    item_df = df[df["set_number"] == set_number]
    if item_df.empty:
        return None

    from datetime import datetime

    target_date = datetime(target_year, target_month, 15)
    best_price = None
    best_dist = float("inf")

    for _, row in item_df.iterrows():
        scraped = row["scraped_at"]
        if scraped is None:
            continue
        if isinstance(scraped, str):
            try:
                scraped = datetime.fromisoformat(scraped)
            except ValueError:
                continue

        dist_days = abs((scraped - target_date).days)
        # Allow up to 90 days of slack
        if dist_days < best_dist and dist_days <= 90:
            best_dist = dist_days
            best_price = int(row["value_new_cents"])

    return best_price


def _add_months(year: int, month: int, months: int) -> tuple[int, int]:
    """Add months to a year/month pair."""
    total = (year * 12 + month - 1) + months
    return total // 12, (total % 12) + 1


def _set_number_to_item_id(set_number: str) -> str:
    """Convert set_number (e.g. '75192') to BrickLink item_id ('75192-1')."""
    if "-" in set_number:
        return set_number
    return f"{set_number}-1"
