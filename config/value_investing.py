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

    retiring_soon: float = 1.10  # Pre-retirement (leading indicator)
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


# =============================================================================
# THEME ANNUAL GROWTH RATES (%)
# =============================================================================
# Annualized price growth by theme from BrickLink market data.
# Positive = appreciating on average year-over-year.

THEME_ANNUAL_GROWTH: dict[str, float] = {
    "Indiana Jones": 17.4,
    "Scooby-Doo": 15.0,
    "The Hobbit": 13.1,
    "Wicked": 12.3,
    "Bionicle": 12.3,
    "FORMA": 11.6,
    "Minions": 11.1,
    "Animal Crossing": 11.0,
    "Ghostbusters": 10.9,
    "Avatar": 10.8,
    "Overwatch": 10.5,
    "BrickLink": 10.2,
    "Teenage Mutant Ninja Turtles": 10.0,
    "Vidiyo": 9.33,
    "Architecture": 8.82,
    "Mixels": 8.77,
    "HERO Factory": 8.24,
    "BrickHeadz": 8.12,
    "Ninjago": 7.82,
    "The LEGO Batman Movie": 7.61,
    "Super Mario": 7.26,
    "Jurassic World": 7.23,
    "The Angry Birds Movie": 6.91,
    "The LEGO Ninjago Movie": 6.84,
    "Speed Champions": 6.72,
    "Pirates": 6.69,
    "Duplo": 6.55,
    "DC Comics Super Heroes": 6.54,
    "Minifigure Series": 6.49,
    "Star Wars": 6.39,
    "Minecraft": 6.33,
    "Nexo Knights": 6.14,
    "LEGO Art": 6.02,
    "Marvel Super Heroes": 5.98,
    "Sonic the Hedgehog": 5.90,
    "Seasonal": 5.90,
    "Elves": 5.86,
    "Ideas": 5.84,
    "Monkie Kid": 5.73,
    "Xtra": 5.57,
    "Toy Story": 5.34,
    "Icons": 5.31,
    "Education": 5.11,
    "Ultra Agents": 5.10,
    "Dots": 4.91,
    "Technic": 4.91,
    "Exclusive": 4.81,
    "Legends of Chima": 4.77,
    "The Lego Movie 2 The Second Part": 4.77,
    "Disney": 4.77,
    "Creator": 4.75,
    "The LEGO Movie": 4.74,
    "DUPLO": 4.72,
    "City": 4.59,
    "Gabby's Dollhouse": 4.52,
    "Dimensions": 4.21,
    "Disney Princess": 4.19,
    "Promotional": 4.13,
    "Juniors": 3.71,
    "Unikitty!": 3.67,
    "Classic": 3.57,
    "DREAMZzz": 3.56,
    "Friends": 3.49,
    "Brick Sketches": 3.31,
    "Trolls World Tour": 3.23,
    "Hidden Side": 2.98,
    "Fusion": 2.85,
    "Books": 2.81,
    "Powered Up": 2.38,
    "Harry Potter": 2.31,
    "Racers": 2.13,
    "DC Super Hero Girls": 2.12,
}

# Default annual growth for themes not in the lookup
DEFAULT_THEME_ANNUAL_GROWTH = 5.0


# =============================================================================
# SUB-THEME ANNUAL GROWTH RATES (%)
# =============================================================================
# Granular growth by theme / sub-theme from BrickLink market data.
# Key format: "Theme / Sub-Theme"

SUBTHEME_ANNUAL_GROWTH: dict[str, float] = {
    "City / Jungle Exploration": 30.7,
    "BrickLink / Designer Program Series 5": 29.2,
    "BrickLink / Designer Program Series 4": 28.3,
    "BrickHeadz / Sonic the Hedgehog": 27.0,
    "BrickHeadz / The Lord of the Rings": 26.9,
    "Super Mario / Power-Up Pack": 26.0,
    "Minifigure Series / Series 26 Space": 25.4,
    "BrickLink / Designer Program Series 3": 24.5,
    "Minifigure Series / Series 27": 24.4,
    "Creator / Traffic": 24.1,
    "Ninjago / Arcade Pod": 24.0,
    "Technic / Monster Jam": 23.9,
    "Creator / Postcard": 23.2,
    "Star Wars / Helmet Collection": 21.7,
    "BrickHeadz / The LEGO Movie 2 The Second Part": 21.4,
    "Promotional / LEGO Brand Stores": 19.6,
    "Ninjago / Rising Dragon Strike": 18.9,
    "Speed Champions / Dodge": 18.0,
    "Minifigure Series / Marvel Studios": 17.8,
    "Super Mario / Miscellaneous": 17.8,
    "Minifigure Series / Series 25": 17.7,
    "Education / FIRST LEGO League Challenge": 17.7,
    "Star Wars / Episode II": 17.6,
    "Avatar / The Way of Water": 17.5,
    "Icons / Botanical Collection": 16.9,
    "Minifigure Series / Dungeons & Dragons": 16.9,
    "Vidiyo / Bandmates Series 2": 16.8,
    "Architecture / Skylines": 16.8,
    "Icons / Modular Buildings": 16.7,
    "Icons / Buildings": 16.5,
    "Promotional / Target": 16.4,
    "Minifigure Series / Marvel Studios Series 2": 16.2,
    "Ideas / NASA": 16.2,
    "Icons / Licensed": 16.2,
    "Minifigure Series / The Muppets": 16.0,
    "Speed Champions / Lamborghini": 15.9,
    "BrickHeadz / Disney": 15.9,
    "BrickLink / Designer Program Series 2": 15.8,
    "Star Wars / Mechs": 15.7,
    "Disney / Tangled": 15.7,
    "Speed Champions / Audi": 15.7,
    "Minifigure Series / Disney 100": 15.7,
    "Ninjago / Promotional": 15.6,
    "Ideas / Licensed": 15.6,
    "Star Wars / Episode III": 15.5,
    "Icons / Winter Village": 15.4,
    "BrickLink / Designer Program Series 1": 15.3,
    "Seasonal / Birthday": 15.0,
    "BrickLink / AFOL Designer Set": 14.7,
    "DC Comics Super Heroes / Batman 1989": 14.7,
    "DC Comics Super Heroes / Value Packs": 14.6,
    "Ninjago / The Hands of Time": 14.5,
    "Star Wars / Episode V": 14.4,
    "Bionicle / Unity": 14.3,
    "The Hobbit / The Battle of the Five Armies": 14.1,
    "Speed Champions / Porsche": 14.1,
    "Jurassic World / Jurassic Park": 14.1,
    "BrickHeadz / Minecraft": 14.0,
    "Promotional / LEGO House": 13.9,
    "Creator / Seasonal": 13.9,
    "Monkie Kid / Season 4": 13.9,
    "Minifigure Series / Series 24": 13.8,
    "Duplo / Trains": 13.8,
    "Ninjago / Secrets of the Forbidden Spinjitzu": 13.6,
    "Super Mario / Character Pack Series 6": 13.6,
    "Bionicle / Companions": 13.6,
    "BrickHeadz / Wizarding World": 13.5,
    "Star Wars / Rogue One": 13.4,
    "Ninjago / Core": 13.3,
    "Minecraft / BigFigs Series 1": 13.1,
    "Star Wars / Ultimate Collector Series": 13.1,
    "Bionicle / Toa": 13.0,
    "Bionicle / Reboot Villains": 13.0,
    "Architecture / Landmark Series": 13.0,
    "Marvel Super Heroes / Spider-Man": 12.9,
    "City / Town": 12.9,
    "Minions / The Rise of Gru": 12.9,
    "Ninjago / Airjitzu": 12.8,
    "Marvel Super Heroes / X-Men": 12.7,
    "Super Mario / Character Pack Series 4": 12.6,
    "Speed Champions / Ford": 12.5,
    "Ninjago / Spinjitzu": 12.3,
    "BrickHeadz / Miscellaneous": 12.3,
    "Star Wars / Legends": 12.3,
    "Marvel Super Heroes / Avengers": 12.3,
    "BrickLink / Designer Program": 12.2,
    "Ninjago / Spinjitzu Slam": 12.2,
    "Minifigure Series / DC Super Heroes": 12.2,
    "BrickHeadz / Pets": 12.0,
    "Harry Potter / Characters Sculptures": 11.9,
    "Ninjago / Legacy": 11.9,
    "Super Mario / Character Pack Series 5": 11.9,
    "DC Comics Super Heroes / Justice League": 11.9,
    "Harry Potter / Goblet of Fire": 11.8,
    "Sonic the Hedgehog / Classic Games": 11.8,
}


def get_subtheme_annual_growth(theme: str | None, subtheme: str | None) -> float | None:
    """Get annual growth rate for a theme/sub-theme combination.

    Args:
        theme: Theme name
        subtheme: Sub-theme name

    Returns:
        Annual growth percentage, or None if no sub-theme match found
    """
    if not theme or not subtheme:
        return None

    key = f"{theme} / {subtheme}"

    # Exact match
    if key in SUBTHEME_ANNUAL_GROWTH:
        return SUBTHEME_ANNUAL_GROWTH[key]

    # Partial match (case-insensitive)
    key_lower = key.lower()
    for k, v in SUBTHEME_ANNUAL_GROWTH.items():
        if k.lower() in key_lower or key_lower in k.lower():
            return v

    return None


def get_theme_annual_growth(theme: str | None) -> float:
    """Get annual growth rate for a theme with partial matching.

    Args:
        theme: Theme name or None

    Returns:
        Annual growth percentage (e.g. 6.39 for Star Wars)
    """
    if not theme:
        return DEFAULT_THEME_ANNUAL_GROWTH

    # Exact match first
    if theme in THEME_ANNUAL_GROWTH:
        return THEME_ANNUAL_GROWTH[theme]

    # Partial match (case-insensitive)
    theme_lower = theme.lower()
    for key, value in THEME_ANNUAL_GROWTH.items():
        if key.lower() in theme_lower or theme_lower in key.lower():
            return value

    return DEFAULT_THEME_ANNUAL_GROWTH


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
