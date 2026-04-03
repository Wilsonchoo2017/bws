"""Shared pure utility functions for the ML pipeline.

All functions in this module are pure -- no side effects, no I/O.
"""

from __future__ import annotations

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
    retired_date: str | None,
    year_retired: int | None,
) -> tuple[int | None, int | None]:
    """Parse retirement timing into (year, month).

    Tries retired_date ("YYYY-MM" string) first, falls back to
    year_retired with month=12.

    Args:
        retired_date: ISO date string like "2022-06", or None.
        year_retired: Retirement year integer, or None.

    Returns:
        (year, month) or (None, None) if unparseable.
    """
    if retired_date and isinstance(retired_date, str) and "-" in retired_date:
        parts = retired_date.split("-")
        try:
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
    if year_retired:
        return int(year_retired), 12
    return None, None


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
