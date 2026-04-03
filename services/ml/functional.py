"""Functional programming utilities for the ML pipeline.

Higher-order functions and composition helpers that eliminate
repeated patterns across the module.
"""

from __future__ import annotations

from functools import reduce
from typing import Callable, TypeVar

import pandas as pd

T = TypeVar("T")


def try_sources(
    sources: tuple[tuple[Callable[..., T | None], str], ...],
    *args: object,
    **kwargs: object,
) -> tuple[T | None, str]:
    """Generic chain of responsibility.

    Tries each (callable, name) pair in order. Returns the first
    non-None result paired with its source name.

    Args:
        sources: Tuple of (resolver_fn, source_name) pairs.
        *args: Positional arguments passed to each resolver.
        **kwargs: Keyword arguments passed to each resolver.

    Returns:
        (result, source_name) or (None, "none").
    """
    for resolver, name in sources:
        result = resolver(*args, **kwargs)
        if result is not None:
            return result, name
    return None, "none"


def merge_feature_frames(
    frames: list[pd.DataFrame],
    on: str = "set_number",
    how: str = "left",
) -> pd.DataFrame:
    """Left-merge a sequence of DataFrames on a common key.

    Filters out empty frames before merging.

    Args:
        frames: List of DataFrames to merge.
        on: Column to merge on.
        how: Merge type (default 'left').

    Returns:
        Merged DataFrame, or empty DataFrame if no non-empty frames.
    """
    non_empty = [f for f in frames if not f.empty]
    if not non_empty:
        return pd.DataFrame()
    return reduce(lambda a, b: a.merge(b, on=on, how=how), non_empty)


def pipe_transforms(
    df: pd.DataFrame,
    *transforms: Callable[[pd.DataFrame], pd.DataFrame],
) -> pd.DataFrame:
    """Apply a sequence of pure DataFrame transforms via composition.

    Each transform takes a DataFrame and returns a new DataFrame.
    This replaces the pattern of `result = df.copy()` followed by
    many lines of `result[col] = ...`.

    Args:
        df: Input DataFrame.
        *transforms: Functions that take and return DataFrames.

    Returns:
        DataFrame after all transforms applied.
    """
    result = df
    for transform in transforms:
        result = transform(result)
    return result
