"""Price type definitions for BWS.

All internal price storage uses Cents (integers) to avoid floating point issues.
"""

import re
from typing import NewType


# Type aliases for price handling
Cents = NewType("Cents", int)
Dollars = NewType("Dollars", float)


def dollars_to_cents(dollars: float) -> Cents:
    """Convert dollars to cents (integer).

    Args:
        dollars: Price in dollars (e.g., 12.34)

    Returns:
        Price in cents (e.g., 1234)
    """
    return Cents(round(dollars * 100))


def cents_to_dollars(cents: Cents) -> Dollars:
    """Convert cents to dollars.

    Args:
        cents: Price in cents (e.g., 1234)

    Returns:
        Price in dollars (e.g., 12.34)
    """
    return Dollars(cents / 100)


def format_cents(cents: Cents | None, currency: str = "USD") -> str:
    """Format cents as a currency string.

    Args:
        cents: Price in cents, or None
        currency: Currency code (default: USD)

    Returns:
        Formatted string (e.g., "USD 12.34" or "N/A")
    """
    if cents is None:
        return "N/A"
    dollars = cents_to_dollars(cents)
    return f"{currency} {dollars:.2f}"


def parse_price_string(price_str: str) -> tuple[str, Cents] | None:
    """Parse a price string like 'USD 12.34' into currency and cents.

    Args:
        price_str: Price string (e.g., "USD 12.34", "MYR 50.00")

    Returns:
        Tuple of (currency, cents) or None if parsing fails
    """

    match = re.match(r"([A-Z]{2,3})\s+([\d,\.]+)", price_str.strip())
    if not match:
        return None

    currency = match.group(1).upper()
    amount = float(match.group(2).replace(",", ""))
    return currency, dollars_to_cents(amount)
