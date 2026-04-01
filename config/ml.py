"""ML pipeline configuration constants."""

from dataclasses import dataclass


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
