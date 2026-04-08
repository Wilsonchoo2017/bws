"""Feature store: materialize and cache features in database.

Combines target computation + feature extraction into a single table
for efficient training and evaluation. Features are stored as a JSON
blob so adding/removing features doesn't require schema migrations.
"""

import json
import logging

import pandas as pd

from config.ml import FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT, MLPipelineConfig
from services.ml.extractors import extract_all as _extract_all_plugin
from services.ml.feature_registry import get_enabled_names
from services.ml.helpers import offset_months
from services.ml.queries import load_base_metadata
from services.ml.target import compute_retirement_returns
from typing import Any


logger = logging.getLogger(__name__)


def materialize_features(
    conn: Any,
    config: MLPipelineConfig | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Build or refresh the feature store.

    1. Compute targets via target.py (retirement returns)
    2. Extract features via feature_extractors.py
    3. Join targets + features
    4. Write to ml_feature_store table
    5. Return the combined DataFrame

    Returns DataFrame with columns:
        set_number, horizon_months, target_return, target_profitable,
        + one column per enabled feature
    """
    if config is None:
        config = MLPipelineConfig()

    if force_refresh:
        conn.execute("DELETE FROM ml_feature_store")
        logger.info("Cleared existing feature store")

    # 1. Compute targets
    targets_df = compute_retirement_returns(conn, config)
    if targets_df.empty:
        logger.warning("No retirement returns computed, feature store will be empty")
        return pd.DataFrame()

    set_numbers = targets_df["set_number"].tolist()
    logger.info("Computed targets for %d retired sets", len(set_numbers))

    # 2. Extract features via plugin-based extractors
    features_df = _extract_features_with_cutoff(conn, set_numbers)
    if features_df.empty:
        logger.warning("No features extracted")
        return pd.DataFrame()

    logger.info(
        "Extracted %d features for %d sets",
        len(features_df.columns) - 1,  # minus set_number
        len(features_df),
    )

    # 3. Join targets + features
    merged = targets_df.merge(features_df, on="set_number", how="inner")
    logger.info("Merged dataset: %d sets", len(merged))

    # 4. Write to database (one row per set per horizon)
    feature_cols = get_enabled_names()
    available_feature_cols = [c for c in feature_cols if c in merged.columns]
    _write_to_store(conn, merged, available_feature_cols, config)

    # 5. Return the combined DataFrame
    return merged


def load_feature_store(
    conn: Any,
    horizon_months: int = 12,
) -> pd.DataFrame:
    """Load materialized features from database.

    Returns DataFrame ready for training: one row per set,
    columns = feature columns + target_return + target_profitable.
    """
    query = """
        SELECT
            set_number,
            horizon_months,
            target_return,
            target_profitable,
            features_json
        FROM ml_feature_store
        WHERE horizon_months = ?
        ORDER BY set_number
    """
    df = conn.execute(query, [horizon_months]).df()
    if df.empty:
        return df

    # Expand features_json into columns
    feature_rows: list[dict] = []
    for _, row in df.iterrows():
        features_raw = row["features_json"]
        if isinstance(features_raw, str):
            features = json.loads(features_raw)
        else:
            features = features_raw if features_raw else {}

        entry = {
            "set_number": row["set_number"],
            "target_return": row["target_return"],
            "target_profitable": row["target_profitable"],
        }
        entry.update(features)
        feature_rows.append(entry)

    return pd.DataFrame(feature_rows)


def get_store_stats(conn: Any) -> dict[str, int]:
    """Get summary statistics of the feature store."""
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM ml_feature_store"
        ).fetchone()
        by_horizon = conn.execute(
            "SELECT horizon_months, COUNT(*) AS cnt "
            "FROM ml_feature_store GROUP BY horizon_months ORDER BY horizon_months"
        ).fetchall()

        return {
            "total_rows": total[0] if total else 0,
            **{f"horizon_{h}m": c for h, c in by_horizon},
        }
    except Exception:
        return {"total_rows": 0}


def _extract_features_with_cutoff(
    conn: Any,
    set_numbers: list[str],
) -> pd.DataFrame:
    """Build base metadata with cutoff dates and run all extractors."""
    base = load_base_metadata(conn, set_numbers)
    if base.empty:
        return pd.DataFrame()

    base["cutoff_year"] = None
    base["cutoff_month"] = None
    for idx, row in base.iterrows():
        rd = row.get("retired_date")
        yr = row.get("year_retired")
        if pd.notna(rd) and isinstance(rd, str) and "-" in rd:
            parts = rd.split("-")
            ret_year, ret_month = int(parts[0]), int(parts[1])
            cy, cm = offset_months(
                ret_year, ret_month, -FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
            )
            base.at[idx, "cutoff_year"] = cy
            base.at[idx, "cutoff_month"] = cm
        elif pd.notna(rd) and hasattr(rd, "year"):  # datetime.date from DB
            cy, cm = offset_months(
                rd.year, rd.month, -FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
            )
            base.at[idx, "cutoff_year"] = cy
            base.at[idx, "cutoff_month"] = cm
        elif pd.notna(yr):
            cy, cm = offset_months(
                int(yr), 1, -FEATURE_CUTOFF_MONTHS_BEFORE_RETIREMENT
            )
            base.at[idx, "cutoff_year"] = cy
            base.at[idx, "cutoff_month"] = cm

    return _extract_all_plugin(conn, base)


def _write_to_store(
    conn: Any,
    merged: pd.DataFrame,
    feature_cols: list[str],
    config: MLPipelineConfig,
) -> None:
    """Write merged features + targets to the ml_feature_store table."""
    conn.execute("DELETE FROM ml_feature_store")

    rows_written = 0
    for _, row in merged.iterrows():
        sn = row["set_number"]

        # Build features JSON
        features = {}
        for col in feature_cols:
            val = row.get(col)
            if val is not None and pd.notna(val):
                features[col] = float(val)
            else:
                features[col] = None

        features_json = json.dumps(features)

        for horizon in config.target_horizons:
            col_suffix = f"{horizon}m"
            target_return = row.get(f"return_{col_suffix}")
            target_profitable = row.get(f"profitable_{col_suffix}")

            if target_return is None or pd.isna(target_return):
                continue

            conn.execute(
                """
                INSERT INTO ml_feature_store
                    (id, set_number, horizon_months, target_return,
                     target_profitable, features_json)
                VALUES (
                    nextval('ml_feature_store_id_seq'),
                    ?, ?, ?, ?, ?::JSON
                )
                """,
                [sn, horizon, float(target_return), bool(target_profitable), features_json],
            )
            rows_written += 1

    logger.info("Wrote %d rows to ml_feature_store", rows_written)
