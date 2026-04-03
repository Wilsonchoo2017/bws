"""Target variable computation for ML pipeline.

Computes post-retirement returns: (transacted_price / rrp_usd) - 1
at 12, 24, and 36 month horizons.

Primary source: BrickLink monthly sales avg_price (USD).
Fallback: BrickEconomy value_chart_json time series or value_new_cents
from snapshots (since BrickLink only keeps 6 months of data).
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from config.ml import (
    OUTCOME_LOSER,
    OUTCOME_NEUTRAL,
    OUTCOME_PERFORMER,
    OUTCOME_STAGNANT,
    OUTCOME_STRONG_LOSER,
    InversionConfig,
    MLPipelineConfig,
    TARGET_SMOOTHING_WINDOW,
)
from services.ml.helpers import offset_months, set_number_to_item_id
from services.ml.queries import (
    load_be_snapshot_values,
    load_be_value_charts,
    load_bricklink_monthly_prices,
    load_retired_sets,
)

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

    # Load all data upfront (impure boundary)
    sets_df = _parse_retired_sets(load_retired_sets(conn))
    if sets_df.empty:
        logger.warning("No retired sets with RRP found")
        return pd.DataFrame()

    bricklink_prices = load_bricklink_monthly_prices(conn)
    be_value_charts = load_be_value_charts(conn)
    be_snapshots = load_be_snapshot_values(conn)

    # Pure computation over pre-loaded data
    return _compute_returns(
        sets_df, bricklink_prices, be_value_charts, be_snapshots, config
    )


def compute_outcome_labels(
    returns_df: pd.DataFrame,
    config: InversionConfig | None = None,
) -> pd.DataFrame:
    """Add outcome category labels and binary avoid flags to returns DataFrame.

    Takes the output of compute_retirement_returns() and adds columns:
        outcome_12m/24m/36m: categorical (strong_loser/loser/stagnant/neutral/performer)
        avoid_12m/24m/36m: boolean (True if return < avoid_threshold)

    Args:
        returns_df: DataFrame from compute_retirement_returns() with return_12m etc.
        config: Inversion thresholds. Uses defaults if None.

    Returns:
        New DataFrame with original columns plus outcome and avoid columns.
    """
    if config is None:
        config = InversionConfig()

    if returns_df.empty:
        return returns_df

    result = returns_df.copy()

    for horizon in (12, 24, 36):
        col = f"{horizon}m"
        return_col = f"return_{col}"

        if return_col not in result.columns:
            continue

        result[f"outcome_{col}"] = result[return_col].apply(
            lambda r: _classify_outcome(r, config)
        )
        result[f"avoid_{col}"] = result[return_col].apply(
            lambda r: r < config.avoid_threshold if pd.notna(r) else None
        )

    return result


# ---------------------------------------------------------------------------
# Pure computation functions
# ---------------------------------------------------------------------------


def _compute_returns(
    sets_df: pd.DataFrame,
    bricklink_prices: pd.DataFrame,
    be_value_charts: dict[str, list[tuple[int, int, int]]],
    be_snapshots: pd.DataFrame,
    config: MLPipelineConfig,
) -> pd.DataFrame:
    """Compute returns from pre-loaded data (pure function)."""
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

        item_id = set_number_to_item_id(set_number)

        for horizon in config.target_horizons:
            target_year, target_month = offset_months(
                retired_year, retired_month, horizon
            )

            avg_price, source = get_price_at_horizon(
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


def _parse_retired_sets(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Parse retired_date into year/month components."""
    if raw_df.empty:
        return raw_df

    df = raw_df.copy()
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
            df.at[idx, "retired_year"] = int(yr)
            df.at[idx, "retired_month"] = 12

    df = df.dropna(subset=["retired_year", "retired_month"])
    df["retired_year"] = df["retired_year"].astype(int)
    df["retired_month"] = df["retired_month"].astype(int)
    return df


def _classify_outcome(
    ret: float | None,
    config: InversionConfig,
) -> str | None:
    """Classify a return value into an outcome category."""
    if ret is None or pd.isna(ret):
        return None
    if ret < config.strong_loser_threshold:
        return OUTCOME_STRONG_LOSER
    if ret < config.loser_threshold:
        return OUTCOME_LOSER
    if ret < config.stagnant_threshold:
        return OUTCOME_STAGNANT
    if ret < config.neutral_threshold:
        return OUTCOME_NEUTRAL
    return OUTCOME_PERFORMER


# ---------------------------------------------------------------------------
# Price resolution (pure -- operates on pre-loaded data)
# ---------------------------------------------------------------------------


def get_price_at_horizon(
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
    price = bricklink_price_at(
        bricklink_prices, item_id, target_year, target_month, half_window
    )
    if price is not None:
        return price, "bricklink"

    price = be_chart_price_at(
        be_value_charts, set_number, target_year, target_month, half_window
    )
    if price is not None:
        return price, "brickeconomy_chart"

    price = be_snapshot_price_at(
        be_snapshots, set_number, target_year, target_month, half_window
    )
    if price is not None:
        return price, "brickeconomy_snapshot"

    return None, "none"


def bricklink_price_at(
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
        y, m = offset_months(target_year, target_month, offset)
        match = item_df[(item_df["year"] == y) & (item_df["month"] == m)]
        if not match.empty:
            p = match.iloc[0]["avg_price"]
            if p and p > 0:
                prices.append(int(p))

    if prices:
        return int(sum(prices) / len(prices))
    return None


def be_chart_price_at(
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

    prices: list[int] = []
    for offset in range(-half_window, half_window + 1):
        y, m = offset_months(target_year, target_month, offset)
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


def be_snapshot_price_at(
    df: pd.DataFrame,
    set_number: str,
    target_year: int,
    target_month: int,
    half_window: int,  # noqa: ARG001
) -> int | None:
    """Get value_new_cents from BrickEconomy snapshots near target date."""
    item_df = df[df["set_number"] == set_number]
    if item_df.empty:
        return None

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
        if dist_days < best_dist and dist_days <= 90:
            best_dist = dist_days
            best_price = int(row["value_new_cents"])

    return best_price
