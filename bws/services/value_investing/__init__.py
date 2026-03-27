"""Value investing engine.

Core value calculation and data aggregation for LEGO investment analysis.
Based on Mohnish Pabrai's value investing principles.
"""

from bws.services.value_investing.types import ValueBreakdown, ValueInputs
from bws.services.value_investing.value_calc import (
    apply_sanity_bounds,
    calculate_base_value,
    calculate_intrinsic_value,
    check_hard_gates,
)


__all__ = [
    "ValueBreakdown",
    "ValueInputs",
    "apply_sanity_bounds",
    "calculate_base_value",
    "calculate_intrinsic_value",
    "check_hard_gates",
]
