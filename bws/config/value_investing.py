"""Value investing configuration constants.

All configuration values for the value investing engine as frozen dataclasses
and module constants. Based on Mohnish Pabrai's value investing principles.
"""

from dataclasses import dataclass


# =============================================================================
# INTRINSIC VALUE BASE WEIGHTS
# =============================================================================

# When calculating base value from Bricklink prices
BASE_PRICE_AVG_WEIGHT = 0.7
BASE_PRICE_MAX_WEIGHT = 0.3

# Discount when only max price is available (no avg)
MAX_ONLY_DISCOUNT = 0.6


# =============================================================================
# RETIREMENT MULTIPLIERS (J-CURVE)
# =============================================================================


@dataclass(frozen=True)
class RetirementMultipliers:
    """J-curve retirement premium multipliers by years post-retirement."""

    year_0_1: float = 0.95  # Initial discount (market oversupply)
    year_1_2: float = 1.00  # Baseline
    year_2_5: float = 1.15  # Growth phase
    year_5_10: float = 1.40  # Maturity
    year_10_plus: float = 2.00  # Collector premium


RETIREMENT_MULTIPLIERS = RetirementMultipliers()


def get_retirement_multiplier(years_post_retirement: int | None) -> float:
    """Get retirement multiplier based on years since retirement.

    Args:
        years_post_retirement: Years since set retired, or None if still active

    Returns:
        Multiplier value (0.95 - 2.00)
    """
    if years_post_retirement is None:
        return 1.0  # Active set, no premium

    if years_post_retirement < 1:
        return RETIREMENT_MULTIPLIERS.year_0_1
    if years_post_retirement < 2:
        return RETIREMENT_MULTIPLIERS.year_1_2
    if years_post_retirement < 5:
        return RETIREMENT_MULTIPLIERS.year_2_5
    if years_post_retirement < 10:
        return RETIREMENT_MULTIPLIERS.year_5_10
    return RETIREMENT_MULTIPLIERS.year_10_plus


# =============================================================================
# THEME MULTIPLIERS
# =============================================================================

THEME_MULTIPLIERS: dict[str, float] = {
    # Premium themes (collector appeal)
    "Star Wars": 1.30,
    "Architecture": 1.40,
    "Creator Expert": 1.25,
    "Ideas": 1.20,
    "Modular Buildings": 1.35,
    "Icons": 1.25,
    "Art": 1.15,
    "Ultimate Collector Series": 1.45,
    "UCS": 1.45,
    # Standard themes
    "Technic": 1.10,
    "Creator": 1.05,
    "Speed Champions": 1.05,
    "Harry Potter": 1.15,
    "Marvel": 1.10,
    "DC": 1.05,
    "Ninjago": 1.00,
    "Minecraft": 1.00,
    "Super Mario": 1.00,
    # Lower demand themes
    "City": 0.80,
    "Friends": 0.75,
    "Duplo": 0.70,
    "Classic": 0.75,
    "Dots": 0.65,
    "Vidiyo": 0.50,
}

# Default multiplier for unknown themes
DEFAULT_THEME_MULTIPLIER = 1.0


def get_theme_multiplier(theme: str | None) -> float:
    """Get theme multiplier with partial matching.

    Args:
        theme: Theme name or None

    Returns:
        Multiplier value
    """
    if not theme:
        return DEFAULT_THEME_MULTIPLIER

    # Exact match first
    if theme in THEME_MULTIPLIERS:
        return THEME_MULTIPLIERS[theme]

    # Partial match (case-insensitive)
    theme_lower = theme.lower()
    for key, value in THEME_MULTIPLIERS.items():
        if key.lower() in theme_lower or theme_lower in key.lower():
            return value

    return DEFAULT_THEME_MULTIPLIER


# =============================================================================
# LIQUIDITY THRESHOLDS
# =============================================================================

# Sales velocity thresholds (sales per day)
LIQUIDITY_VELOCITY_HIGH = 0.5  # 15+ sales/month
LIQUIDITY_VELOCITY_MEDIUM = 0.1  # 3+ sales/month
LIQUIDITY_VELOCITY_LOW = 0.033  # 1 sale/month
LIQUIDITY_VELOCITY_DEAD = 0.01  # Less than 1 sale every 3 months

# Multiplier range for liquidity
LIQUIDITY_MULTIPLIER_MIN = 0.60
LIQUIDITY_MULTIPLIER_MAX = 1.10


# =============================================================================
# VOLATILITY DISCOUNT
# =============================================================================

# Maximum discount for high volatility
VOLATILITY_MAX_DISCOUNT = 0.12

# Risk aversion factor (how much we penalize volatility)
VOLATILITY_RISK_AVERSION = 0.20


# =============================================================================
# SATURATION THRESHOLDS
# =============================================================================

# Months of inventory thresholds
SATURATION_MONTHS_PREMIUM = 3  # Less than 3 months = premium
SATURATION_MONTHS_NEUTRAL = 12  # 3-12 months = neutral
SATURATION_MONTHS_DISCOUNT = 24  # 12-24 months = interpolate to discount

# Multiplier range for saturation
SATURATION_MULTIPLIER_MIN = 0.50
SATURATION_MULTIPLIER_MAX = 1.05


# =============================================================================
# PARTS PER DOLLAR (PPD) THRESHOLDS
# =============================================================================

# PPD quality thresholds
PPD_EXCELLENT = 10.0  # 10+ parts per dollar
PPD_GOOD = 8.0  # 8-10 PPD
PPD_FAIR = 6.0  # 6-8 PPD
# Below 6 PPD is considered poor

# PPD multipliers
PPD_MULTIPLIER_EXCELLENT = 1.10
PPD_MULTIPLIER_GOOD = 1.05
PPD_MULTIPLIER_FAIR = 1.00
PPD_MULTIPLIER_POOR = 0.95


# =============================================================================
# SANITY BOUNDS
# =============================================================================

# Minimum and maximum total multiplier (prevents extreme valuations)
MULTIPLIER_MIN_BOUND = 0.30
MULTIPLIER_MAX_BOUND = 3.50


# =============================================================================
# MARGIN OF SAFETY
# =============================================================================

# Default margin of safety (Pabrai style)
MARGIN_DEFAULT = 0.25

# Margin based on confidence level
MARGIN_HIGH_CONFIDENCE = 0.20
MARGIN_LOW_CONFIDENCE = 0.40


# =============================================================================
# HARD GATE THRESHOLDS (TOO HARD PILE)
# =============================================================================

# Minimum scores required (0-100)
GATE_MIN_QUALITY_SCORE = 40
GATE_MIN_DEMAND_SCORE = 40

# Dead velocity threshold (reject items with less activity)
GATE_DEAD_VELOCITY = 0.033  # Less than 1 sale per month

# Maximum inventory months (reject oversaturated items)
GATE_MAX_INVENTORY_MONTHS = 24


@dataclass(frozen=True)
class HardGates:
    """Hard gate thresholds for rejecting items."""

    min_quality_score: int = GATE_MIN_QUALITY_SCORE
    min_demand_score: int = GATE_MIN_DEMAND_SCORE
    dead_velocity: float = GATE_DEAD_VELOCITY
    max_inventory_months: int = GATE_MAX_INVENTORY_MONTHS


HARD_GATES = HardGates()


# =============================================================================
# SCORE COMPONENT WEIGHTS
# =============================================================================


@dataclass(frozen=True)
class DemandScoreWeights:
    """Weights for demand score components."""

    velocity: float = 0.30
    momentum: float = 0.25
    market_depth: float = 0.20
    supply_demand_ratio: float = 0.15
    consistency: float = 0.10


@dataclass(frozen=True)
class QualityScoreWeights:
    """Weights for quality score components."""

    ppd: float = 0.40
    complexity: float = 0.30
    theme: float = 0.20
    scarcity: float = 0.10


DEMAND_SCORE_WEIGHTS = DemandScoreWeights()
QUALITY_SCORE_WEIGHTS = QualityScoreWeights()


# =============================================================================
# SCARCITY THRESHOLDS
# =============================================================================

# Months of inventory for scarcity scoring
SCARCITY_ULTRA_RARE_MONTHS = 1  # Less than 1 month supply
SCARCITY_RARE_MONTHS = 3  # 1-3 months supply
SCARCITY_LIMITED_MONTHS = 6  # 3-6 months supply
# Greater than 6 months = common

# Scarcity multipliers
SCARCITY_MULTIPLIER_ULTRA_RARE = 1.10
SCARCITY_MULTIPLIER_RARE = 1.05
SCARCITY_MULTIPLIER_LIMITED = 1.00
SCARCITY_MULTIPLIER_COMMON = 0.95
