"""Feature engineering for ML-based signal optimization.

Creates derived features from the 14 raw signals and 3 modifiers,
including domain-driven interaction pairs and data quality proxies.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from services.backtesting.types import MODIFIER_NAMES, SIGNAL_NAMES

# Domain-driven interaction pairs: each tuple is (signal_a, signal_b, output_name).
# These capture investment-relevant combinations that raw signals alone miss.
DEFAULT_INTERACTION_PAIRS: tuple[tuple[str, str, str], ...] = (
    # Recently retired AND in demand = J-curve sweet spot
    ("lifecycle_position", "demand_pressure", "lifecycle_demand"),
    # Undervalued AND scarce supply = buy signal
    ("value_opportunity", "listing_ratio", "value_scarcity"),
    # Low stock AND supply decreasing = scarcity accelerating
    ("stock_level", "supply_velocity", "scarcity_momentum"),
    # Price trend AND theme tailwind = compounding momentum
    ("price_trend", "theme_growth", "trend_tailwind"),
    # Collector premium AND tight new/used spread = strong market
    ("collector_premium", "new_used_spread", "market_health"),
)


@dataclass(frozen=True)
class FeatureConfig:
    """Controls which derived features to generate."""

    include_interactions: bool = True
    include_log_price: bool = True
    include_signal_count: bool = True
    interaction_pairs: tuple[tuple[str, str, str], ...] = DEFAULT_INTERACTION_PAIRS


def engineer_features(
    df: pd.DataFrame,
    config: FeatureConfig | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Add derived feature columns to the analysis DataFrame.

    Returns:
        A tuple of (augmented_df, feature_names) where feature_names
        lists all columns suitable for ML input. The input DataFrame
        is not mutated.
    """
    if config is None:
        config = FeatureConfig()

    result = df.copy()
    feature_names: list[str] = []

    # 1. Raw signals
    for signal in SIGNAL_NAMES:
        if signal in result.columns:
            feature_names.append(signal)

    # 2. Modifiers
    for mod in MODIFIER_NAMES:
        if mod in result.columns:
            feature_names.append(mod)

    # 3. Interaction features
    if config.include_interactions:
        for sig_a, sig_b, output_name in config.interaction_pairs:
            if sig_a in result.columns and sig_b in result.columns:
                result[output_name] = _compute_interaction(
                    result[sig_a], result[sig_b]
                )
                feature_names.append(output_name)

    # 4. Log entry price (reduces skew from wide price range)
    if config.include_log_price and "entry_price_cents" in result.columns:
        result["log_entry_price"] = result["entry_price_cents"].apply(
            lambda x: np.log1p(x) if pd.notna(x) and x > 0 else np.nan
        )
        feature_names.append("log_entry_price")

    # 5. Signal count (data quality proxy)
    if config.include_signal_count:
        signal_cols_present = [s for s in SIGNAL_NAMES if s in result.columns]
        if signal_cols_present:
            result["signal_count"] = result[signal_cols_present].notna().sum(axis=1)
            feature_names.append("signal_count")

    return result, feature_names


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return all signal, modifier, and derived feature column names in df.

    Useful when loading a previously-engineered DataFrame where you need
    to recover the feature list without re-running engineer_features.
    """
    known_derived = {pair[2] for pair in DEFAULT_INTERACTION_PAIRS}
    known_derived.update({"log_entry_price", "signal_count"})

    columns: list[str] = []
    for col in df.columns:
        if col in SIGNAL_NAMES or col in MODIFIER_NAMES or col in known_derived:
            columns.append(col)
    return columns


def _compute_interaction(
    series_a: pd.Series,
    series_b: pd.Series,
) -> pd.Series:
    """Compute normalized interaction between two 0-100 signals.

    Result is (a * b) / 100, keeping the 0-100 scale.
    If either input is NaN, the output is NaN.
    """
    return (series_a * series_b) / 100.0
