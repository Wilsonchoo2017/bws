"""Kelly Criterion position sizing configuration."""

# Score bins matching frontend color thresholds (scoreColor in signals-table.tsx)
# Each tuple is (lower_inclusive, upper_exclusive)
SCORE_BINS: list[tuple[int, int]] = [
    (0, 35),
    (35, 50),
    (50, 65),
    (65, 80),
    (80, 101),
]

SCORE_BIN_LABELS: dict[tuple[int, int], str] = {
    (0, 35): "Poor (0-34)",
    (35, 50): "Weak (35-49)",
    (50, 65): "Neutral (50-64)",
    (65, 80): "Good (65-79)",
    (80, 101): "Strong (80+)",
}

# Half-Kelly multiplier (safety margin for estimation error)
KELLY_FRACTION: float = 0.5

# Maximum allocation to any single set (25%)
MAX_POSITION_PCT: float = 0.25

# Minimum sample count per bin to produce a recommendation
MIN_SAMPLE_COUNT: int = 10

# Confidence thresholds based on sample count
CONFIDENCE_HIGH_SAMPLES: int = 50
CONFIDENCE_MODERATE_SAMPLES: int = 30

# Discount factor applied to half-Kelly when using neighbor-bin fallback.
# 0.6 means the neighbor's recommendation is reduced by 40%.
NEIGHBOR_FALLBACK_DISCOUNT: float = 0.6

# ---------------------------------------------------------------------------
# Signal weights for weighted composite scoring
# ---------------------------------------------------------------------------
# Weights > 1.0 amplify the signal; < 1.0 dampen it.
# Momentum/trend signals are down-weighted (anti-value for buy-and-hold).
# Fundamental signals (theme, lifecycle, value opportunity) are up-weighted.
SIGNAL_WEIGHTS: dict[str, float] = {
    "demand_pressure": 1.0,
    "supply_velocity": 1.0,
    "price_trend": 0.3,
    "price_vs_rrp": 1.0,
    "lifecycle_position": 1.5,
    "stock_level": 1.0,
    "collector_premium": 1.0,
    "theme_growth": 1.2,
    "value_opportunity": 1.8,
    "price_wall": 1.0,
    "listing_ratio": 1.2,
    "new_used_spread": 1.2,
}

# Default weight for signals not listed in SIGNAL_WEIGHTS
DEFAULT_SIGNAL_WEIGHT: float = 1.0

# Whether to apply modifiers (shelf_life, subtheme, niche) as multipliers
# to the composite score
APPLY_MODIFIERS: bool = True

# Return horizons grouped by strategy
FLIP_HORIZONS: tuple[str, ...] = ("return_flip_1m", "return_flip_2m")
HOLD_HORIZONS: tuple[str, ...] = (
    "return_hold_12m",
    "return_hold_24m",
    "return_hold_36m",
)

# ---------------------------------------------------------------------------
# ML-optimized weights (updated by running: python -m services.backtesting.runner --optimize)
# ---------------------------------------------------------------------------
# Initially identical to hand-tuned weights. After optimization, replace with
# learned values and update ML_WEIGHTS_SOURCE to the model name.
ML_SIGNAL_WEIGHTS: dict[str, float] = dict(SIGNAL_WEIGHTS)
ML_WEIGHTS_SOURCE: str = "handtuned"

# ---------------------------------------------------------------------------
# Assumption-based capital allocation (simplified Kelly)
# ---------------------------------------------------------------------------
# Win probabilities from FINDINGS.md Phase 3 Category Breakdown (BL ground truth)
# Loss scenario: -20% half the time, -100% half the time → avg -60%
CATEGORY_PARAMS: dict[str, dict[str, float]] = {
    "GREAT": {"annual_roi": 0.20, "win_prob": 0.973, "hold_years": 3.0},
    "GOOD": {"annual_roi": 0.10, "win_prob": 0.952, "hold_years": 3.0},
}

LOSS_SCENARIOS: list[tuple[float, float]] = [(-0.20, 0.5), (-1.00, 0.5)]
AVG_LOSS_PCT: float = 0.60  # weighted average of loss scenarios

HALF_KELLY_MULTIPLIER: float = 0.5
TARGET_APR: float = 0.20
DISCOUNT_STEPS: list[float] = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
