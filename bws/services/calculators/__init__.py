"""Multiplier calculators for value investing.

Pure functions that calculate value multipliers based on various factors.
Each calculator returns a MultiplierResult with the multiplier value,
explanation, and metadata about the calculation.
"""

from bws.services.calculators.liquidity import calculate_liquidity_multiplier
from bws.services.calculators.ppd import calculate_ppd_multiplier
from bws.services.calculators.retirement import calculate_retirement_multiplier
from bws.services.calculators.saturation import calculate_saturation_multiplier
from bws.services.calculators.scarcity import calculate_scarcity_multiplier
from bws.services.calculators.theme import calculate_theme_multiplier
from bws.services.calculators.volatility import calculate_volatility_penalty


__all__ = [
    "calculate_liquidity_multiplier",
    "calculate_ppd_multiplier",
    "calculate_retirement_multiplier",
    "calculate_saturation_multiplier",
    "calculate_scarcity_multiplier",
    "calculate_theme_multiplier",
    "calculate_volatility_penalty",
]
