"""Shared utility functions for the backtesting framework."""

import pandas as pd


def safe_get(df: pd.DataFrame, col: str) -> str | None:
    """Safely get a string value from a metadata DataFrame."""
    if df.empty or col not in df.columns:
        return None
    val = df.iloc[0][col]
    if pd.isna(val):
        return None
    return str(val)


def safe_get_int(df: pd.DataFrame, col: str) -> int | None:
    """Safely get an int value from a metadata DataFrame."""
    if df.empty or col not in df.columns:
        return None
    val = df.iloc[0][col]
    if pd.isna(val):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def safe_get_bool(df: pd.DataFrame, col: str) -> bool:
    """Safely get a bool value from a metadata DataFrame."""
    if df.empty or col not in df.columns:
        return False
    val = df.iloc[0][col]
    if pd.isna(val):
        return False
    return bool(val)
