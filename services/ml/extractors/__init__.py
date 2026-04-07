"""Feature extractor plugin registry.

Each extractor lives in its own module and implements the FeatureExtractor
protocol. New data sources are added by creating a new module here and
adding its extractor to _ALL_EXTRACTORS.
"""

from __future__ import annotations

from functools import reduce

import pandas as pd

from services.ml.extractors.brickeconomy import BrickEconomyExtractor
from services.ml.extractors.brickeconomy_charts import BrickEconomyChartsExtractor
from services.ml.extractors.bricklink import BrickLinkExtractor
from services.ml.extractors.gtrends import GoogleTrendsExtractor
from services.ml.extractors.gtrends_theme import GoogleTrendsThemeExtractor
from services.ml.extractors.intrinsics import IntrinsicsExtractor
from services.ml.extractors.keepa import KeepaExtractor
from services.ml.extractors.keepa_timeline import KeepaTimelineExtractor
from services.ml.extractors.minifigs import MinifigExtractor
from services.ml.extractors.shopee import ShopeeExtractor
from typing import Any


    from services.ml.protocols import FeatureExtractor
    from services.ml.types import FeatureMeta

_ALL_EXTRACTORS: tuple[FeatureExtractor, ...] = (
    IntrinsicsExtractor(),
    BrickEconomyExtractor(),
    BrickEconomyChartsExtractor(),
    KeepaExtractor(),
    KeepaTimelineExtractor(),
    BrickLinkExtractor(),
    MinifigExtractor(),
    GoogleTrendsExtractor(),
    GoogleTrendsThemeExtractor(),
    ShopeeExtractor(),
)


def get_all_extractors() -> tuple[FeatureExtractor, ...]:
    """Return all registered feature extractors."""
    return _ALL_EXTRACTORS


def get_all_feature_metadata() -> list[FeatureMeta]:
    """Collect feature metadata from all extractors."""
    result: list[FeatureMeta] = []
    for ext in _ALL_EXTRACTORS:
        result.extend(ext.features)
    return result


def extract_all(
    conn: Any,
    base: pd.DataFrame,
) -> pd.DataFrame:
    """Run all extractors and merge results.

    This is the composition function -- it delegates to each extractor
    and left-merges the results on set_number.

    Args:
        conn: Database connection.
        base: Base metadata DataFrame with set_number, cutoff info, etc.

    Returns:
        DataFrame with set_number + all extracted feature columns.
    """
    if base.empty:
        return pd.DataFrame()

    frames = [ext.extract(conn, base) for ext in _ALL_EXTRACTORS]
    non_empty = [f for f in frames if not f.empty]

    if not non_empty:
        return pd.DataFrame()

    return reduce(
        lambda a, b: a.merge(b, on="set_number", how="left"),
        non_empty,
    )
