"""Currency conversion utilities for the ML pipeline.

All ML features and targets must be normalized to USD for consistent
comparison. This module provides conversion rates and helpers.

Rates are approximate mid-market rates and should be updated periodically.
For historical accuracy, rates are bucketed by year.
"""

import logging

logger = logging.getLogger(__name__)

# Historical approximate USD exchange rates (1 USD = X foreign currency).
# Used for converting non-USD prices to USD cents.
# Source: approximate annual averages.
_USD_RATES: dict[int, dict[str, float]] = {
    2018: {"MYR": 4.03, "GBP": 0.75, "EUR": 0.85, "CAD": 1.30, "AUD": 1.34},
    2019: {"MYR": 4.14, "GBP": 0.78, "EUR": 0.89, "CAD": 1.33, "AUD": 1.44},
    2020: {"MYR": 4.20, "GBP": 0.78, "EUR": 0.88, "CAD": 1.34, "AUD": 1.45},
    2021: {"MYR": 4.14, "GBP": 0.73, "EUR": 0.84, "CAD": 1.25, "AUD": 1.33},
    2022: {"MYR": 4.40, "GBP": 0.81, "EUR": 0.95, "CAD": 1.30, "AUD": 1.44},
    2023: {"MYR": 4.56, "GBP": 0.80, "EUR": 0.92, "CAD": 1.35, "AUD": 1.51},
    2024: {"MYR": 4.68, "GBP": 0.79, "EUR": 0.92, "CAD": 1.37, "AUD": 1.53},
    2025: {"MYR": 4.45, "GBP": 0.78, "EUR": 0.91, "CAD": 1.36, "AUD": 1.55},
    2026: {"MYR": 4.40, "GBP": 0.78, "EUR": 0.90, "CAD": 1.35, "AUD": 1.53},
}

# Default rates (latest year fallback)
_DEFAULT_RATES: dict[str, float] = _USD_RATES[2026]


def to_usd_cents(
    amount_cents: int | float | None,
    currency: str,
    year: int | None = None,
) -> int | None:
    """Convert an amount in cents of a given currency to USD cents.

    Args:
        amount_cents: Amount in the source currency's cents.
        currency: ISO currency code (e.g. 'MYR', 'GBP', 'EUR').
        year: Optional year for historical rate lookup.

    Returns:
        Amount in USD cents, or None if conversion not possible.
    """
    if amount_cents is None:
        return None

    currency = currency.upper().strip()
    if currency == "USD":
        return int(amount_cents)

    rates = _USD_RATES.get(year, _DEFAULT_RATES) if year else _DEFAULT_RATES
    rate = rates.get(currency)
    if rate is None:
        logger.warning("No exchange rate for %s (year=%s)", currency, year)
        return None

    return int(float(amount_cents) / rate)


def get_rate(currency: str, year: int | None = None) -> float | None:
    """Get the USD exchange rate for a currency (1 USD = X currency).

    Returns None if currency is unknown.
    """
    currency = currency.upper().strip()
    if currency == "USD":
        return 1.0

    rates = _USD_RATES.get(year, _DEFAULT_RATES) if year else _DEFAULT_RATES
    return rates.get(currency)
