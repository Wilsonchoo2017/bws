"""Shared pure utility functions for the ML pipeline.

All functions in this module are pure -- no side effects, no I/O.
"""

from __future__ import annotations

import datetime

import numpy as np


def safe_float(val: object) -> float | None:
    """Convert a value to float, returning None for NaN/Inf/invalid."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def ordinal_bucket(
    value: int | float | None,
    tiers: tuple[tuple[str, int, int], ...],
) -> int | None:
    """Map a value to its ordinal bucket index (0-based).

    Args:
        value: The numeric value to bucket.
        tiers: Tuple of (label, low_inclusive, high_exclusive) tier definitions.

    Returns:
        The 0-based index of the matching tier, or None if no match.
    """
    if value is None:
        return None
    for i, (_, low, high) in enumerate(tiers):
        if low <= value < high:
            return i
    return None


def offset_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Add or subtract months from a year/month pair.

    Args:
        year: Starting year.
        month: Starting month (1-12).
        delta: Months to add (positive) or subtract (negative).

    Returns:
        (year, month) tuple after applying the offset.
    """
    total = (year * 12 + month - 1) + delta
    return total // 12, (total % 12) + 1


def set_number_to_item_id(set_number: str) -> str:
    """Convert set_number (e.g. '75192') to BrickLink item_id ('75192-1')."""
    if "-" in set_number:
        return set_number
    return f"{set_number}-1"


def parse_retirement_date(
    retired_date: str | datetime.date | None,
    year_retired: int | None,
) -> tuple[int | None, int | None]:
    """Parse retirement timing into (year, month).

    Handles DATE objects (from DB), ISO strings ("YYYY-MM-DD" or "YYYY-MM"),
    and falls back to year_retired with month=12.

    Args:
        retired_date: Date object, ISO string, or None.
        year_retired: Retirement year integer, or None.

    Returns:
        (year, month) or (None, None) if unparseable.
    """
    if isinstance(retired_date, datetime.date):
        return retired_date.year, retired_date.month
    if retired_date and isinstance(retired_date, str) and "-" in retired_date:
        parts = retired_date.split("-")
        try:
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
    if year_retired:
        return int(year_retired), 12
    return None, None


def compute_cutoff_dates(
    df: "pd.DataFrame",
    cutoff_months: int,
) -> "pd.DataFrame":
    """Compute feature cutoff dates for each set in a DataFrame.

    For retired sets, the cutoff is `cutoff_months` before retirement.
    For active sets, cutoff is None (use latest data).

    Adds cutoff_year and cutoff_month columns to the DataFrame.

    Args:
        df: DataFrame with retired_date and year_retired columns.
        cutoff_months: Months before retirement to cut off features.

    Returns:
        DataFrame with cutoff_year and cutoff_month columns added.
    """
    import pandas as pd

    result = df.copy()
    result["cutoff_year"] = None
    result["cutoff_month"] = None

    for idx, row in result.iterrows():
        rd = row.get("retired_date")
        yr = row.get("year_retired")
        if pd.notna(rd) and (isinstance(rd, (str, datetime.date))):
            ret_year, ret_month = parse_retirement_date(rd, None)
            if ret_year is not None:
                cy, cm = offset_months(ret_year, ret_month, -cutoff_months)
                result.at[idx, "cutoff_year"] = cy
                result.at[idx, "cutoff_month"] = cm
        elif pd.notna(yr):
            cy, cm = offset_months(int(yr), 1, -cutoff_months)
            result.at[idx, "cutoff_year"] = cy
            result.at[idx, "cutoff_month"] = cm

    return result


def parse_rating_string(rating_str: object) -> float | None:
    """Parse a rating string like '4.5/5' or '4.5' into a float.

    Args:
        rating_str: Rating value (may be string with '/5' suffix, float, or None).

    Returns:
        Numeric rating value, or None if unparseable.
    """
    import pandas as pd

    if rating_str is None or (hasattr(pd, "isna") and pd.isna(rating_str)):
        return None
    if not rating_str:
        return None
    try:
        return float(str(rating_str).split("/")[0].strip())
    except (ValueError, IndexError):
        return None
