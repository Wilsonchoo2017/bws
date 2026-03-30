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

# Return horizons grouped by strategy
FLIP_HORIZONS: tuple[str, ...] = ("return_flip_1m", "return_flip_2m")
HOLD_HORIZONS: tuple[str, ...] = (
    "return_hold_12m",
    "return_hold_24m",
    "return_hold_36m",
)
