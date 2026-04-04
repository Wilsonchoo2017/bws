"""ML pipeline configuration constants."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InversionConfig:
    """Thresholds for Munger inversion outcome classification.

    Classifies post-retirement returns into 5 buckets and provides
    a binary "avoid" threshold for the classifier target.
    """

    strong_loser_threshold: float = -0.15  # < -15% return
    loser_threshold: float = -0.05  # -15% to -5%
    stagnant_threshold: float = 0.05  # -5% to +5%
    neutral_threshold: float = 0.20  # +5% to +20%
    # >= +20% = performer

    # Binary: return < avoid_threshold = "avoid"
    avoid_threshold: float = 0.05


# Outcome label constants
OUTCOME_STRONG_LOSER = "strong_loser"
OUTCOME_LOSER = "loser"
OUTCOME_STAGNANT = "stagnant"
OUTCOME_NEUTRAL = "neutral"
OUTCOME_PERFORMER = "performer"

OUTCOME_LABELS = (
    OUTCOME_STRONG_LOSER,
    OUTCOME_LOSER,
    OUTCOME_STAGNANT,
    OUTCOME_NEUTRAL,
    OUTCOME_PERFORMER,
)


@dataclass(frozen=True)
class MLPipelineConfig:
    """Configuration for the full ML pipeline."""

    target_horizons: tuple[int, ...] = (12, 24, 36)
    binary_threshold: float = 0.0  # return > 0 = profitable
    min_training_samples: int = 80
    n_cv_splits: int = 5
    test_fraction: float = 0.2
    random_state: int = 42
    feature_store_table: str = "ml_feature_store"
    model_artifact_dir: str = "models"
    max_features: int = 30
    correlation_threshold: float = 0.90
    # Cross-validation
    n_cv_repeats: int = 3
    # Hyperparameter tuning (Optuna)
    tuning_trials: int = 75
    model_candidates: tuple[str, ...] = ("lightgbm", "gbm")
    # Only prefer LightGBM if it beats GBM by this margin
    min_improvement_for_complex: float = 0.01
    # Loss function: "huber" (robust to outliers) or "squared_error"
    gbm_loss: str = "huber"
    gbm_huber_alpha: float = 0.9  # Huber transition percentile
    # Target transformation: "none" or "yeo-johnson"
    target_transform: str = "yeo-johnson"
    # SHAP explanations
    compute_shap: bool = True
    shap_top_k: int = 5


# Features are restricted to data available this many months before retirement.
# We typically buy when a set is retiring soon (~12 months out).
FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT: int = 12

# Averaging window (months) around target horizon to smooth noisy prices.
# E.g., for 12m horizon we average months 11-13 of post-retirement sales.
TARGET_SMOOTHING_WINDOW: int = 3

# Licensed LEGO themes (tend to appreciate differently)
LICENSED_THEMES: frozenset[str] = frozenset({
    "Star Wars",
    "Harry Potter",
    "Marvel Super Heroes",
    "DC Comics Super Heroes",
    "Disney",
    "Jurassic World",
    "Indiana Jones",
    "Lord of the Rings",
    "The Hobbit",
    "Speed Champions",
    "Overwatch",
    "Minecraft",
    "Super Mario",
    "Sonic the Hedgehog",
    "Avatar",
    "Transformers",
})
