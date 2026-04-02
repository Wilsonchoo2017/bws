"""Shared JSON serialization helpers for API responses."""

import math
from typing import overload


@overload
def sanitize_nan(obj: dict) -> dict: ...
@overload
def sanitize_nan(obj: list) -> list: ...
@overload
def sanitize_nan(obj: object) -> object: ...


def sanitize_nan(obj: object) -> object:
    """Replace NaN/Inf float values with None for JSON-safe serialization.

    Works recursively on dicts, lists, and bare floats.
    """
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_nan(v) for v in obj]
    return obj
