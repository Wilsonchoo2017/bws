"""APR (Annualized Percentage Return) calculations for backtesting.

Converts raw percentage returns at various horizons into annualized
rates for fair cross-horizon comparison. A 50% gain in 12 months
(50% APR) is better than 80% in 36 months (~21% APR).
"""

import re

import numpy as np
import pandas as pd

# Maximum APR for short-horizon returns to avoid extreme annualization.
# A 5% gain in 1 month annualizes to ~80% — beyond this cap, the number
# is noise rather than signal.
MAX_FLIP_APR: float = 2.0  # 200%


def compute_apr(raw_return: float, months: int) -> float:
    """Convert a raw return over N months to an annualized percentage rate.

    APR = (1 + raw_return)^(12/months) - 1

    Args:
        raw_return: Fractional return (e.g. 0.50 for 50% gain).
        months: Holding period in months (must be > 0).

    Returns:
        Annualized return as a fraction (e.g. 0.50 for 50% APR).

    Raises:
        ValueError: If months <= 0.
    """
    if months <= 0:
        raise ValueError(f"months must be positive, got {months}")

    # Guard against total loss producing complex numbers:
    # (1 + raw_return) must be >= 0 for real-valued exponentiation.
    base = 1.0 + raw_return
    if base <= 0:
        return -1.0  # Total loss or worse = -100% APR

    return float(base ** (12.0 / months) - 1.0)


def _parse_horizon_months(col_name: str) -> int | None:
    """Extract month count from a return column name.

    Examples:
        'return_hold_12m' -> 12
        'return_flip_2m'  -> 2
        'return_hold_36m' -> 36
    """
    match = re.search(r"(\d+)m$", col_name)
    if match is None:
        return None
    return int(match.group(1))


def add_apr_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add APR columns for each return horizon present in the DataFrame.

    For each column matching 'return_*_Nm', adds an 'apr_*_Nm' column
    with the annualized return.

    Returns a new DataFrame — the input is not mutated.
    """
    result = df.copy()
    return_cols = [c for c in df.columns if c.startswith("return_")]

    for col in return_cols:
        months = _parse_horizon_months(col)
        if months is None:
            continue

        apr_col = col.replace("return_", "apr_")
        is_flip = "flip" in col

        def _to_apr(val: float | None, m: int = months, flip: bool = is_flip) -> float | None:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return None
            apr = compute_apr(val, m)
            if flip:
                return min(apr, MAX_FLIP_APR)
            return apr

        result[apr_col] = result[col].map(_to_apr)

    return result


def compute_best_apr(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'best_hold_apr' column: the best APR across all hold horizons.

    This serves as the primary target variable for ML training — it
    represents the best achievable annualized return if the investor
    chose the optimal exit point.

    Returns a new DataFrame — the input is not mutated.
    """
    result = df.copy()
    hold_apr_cols = [c for c in result.columns if c.startswith("apr_hold_")]

    if not hold_apr_cols:
        result["best_hold_apr"] = np.nan
        return result

    result["best_hold_apr"] = result[hold_apr_cols].max(axis=1)
    return result
