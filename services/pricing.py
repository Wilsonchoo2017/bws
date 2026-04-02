"""Shared pricing utilities for Malaysian retailer scrapers."""

import re


def parse_myr_cents(price_myr: str) -> int | None:
    """Parse a MYR price string to cents. e.g. '123.45' -> 12345."""
    match = re.search(r"([\d,]+\.?\d*)", price_myr)
    if not match:
        return None
    try:
        return int(float(match.group(1).replace(",", "")) * 100)
    except ValueError:
        return None
