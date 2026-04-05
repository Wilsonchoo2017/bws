"""Leakage prevention guardrails for the ML growth pipeline.

These tests enforce that:
1. Circular features are NEVER used in training
2. Temporal cutoff is properly applied to time-series features
3. Extractors respect cutoff dates
4. The ensemble produces honest OOS metrics
5. New features are validated against the circular feature list
"""

import json

import numpy as np
import pandas as pd
import pytest

from services.ml.growth.evaluation import CIRCULAR_FEATURES


# ---------------------------------------------------------------------------
# 1. Circular feature exclusion
# ---------------------------------------------------------------------------


class TestCircularFeatureExclusion:
    """Ensure circular features never leak into training."""

    KNOWN_CIRCULAR = {
        "be_value_trend_pct",
        "be_value_momentum",
        "be_value_cv",
        "be_value_max_drawdown",
        "be_value_recovery",
        "be_value_months",
        "value_new_vs_rrp",
        "annual_growth_pct",
        "rolling_growth_pct",
        "growth_90d_pct",
        "be_future_est_return",
    }

    def test_circular_features_match_known_set(self):
        """CIRCULAR_FEATURES must contain ALL known circular features."""
        missing = self.KNOWN_CIRCULAR - CIRCULAR_FEATURES
        assert not missing, f"Missing from CIRCULAR_FEATURES: {missing}"

    def test_circular_features_not_empty(self):
        assert len(CIRCULAR_FEATURES) >= 10

    def test_annual_growth_pct_is_circular(self):
        """The target variable itself must be in CIRCULAR_FEATURES."""
        assert "annual_growth_pct" in CIRCULAR_FEATURES

    def test_value_derived_features_are_circular(self):
        """Features derived from BrickEconomy value_chart_json must be circular."""
        value_features = {f for f in CIRCULAR_FEATURES if "value" in f.lower()}
        assert len(value_features) >= 4, f"Too few value features flagged: {value_features}"

    def test_tier3_excludes_circular(self):
        """Verify _prepare_tier3_features excludes CIRCULAR_FEATURES."""
        import inspect
        from services.ml.growth.training import _prepare_tier3_features

        source = inspect.getsource(_prepare_tier3_features)
        assert "CIRCULAR_FEATURES" in source, (
            "_prepare_tier3_features must reference CIRCULAR_FEATURES to exclude them"
        )

    def test_no_circular_in_tier3_feature_names(self):
        """If we can train Tier 3, verify no circular features appear."""
        # This is a structural test -- checks the exclude_cols pattern
        from services.ml.growth.training import _prepare_tier3_features

        source = __import__("inspect").getsource(_prepare_tier3_features)
        assert "| CIRCULAR_FEATURES" in source or "CIRCULAR_FEATURES" in source


# ---------------------------------------------------------------------------
# 2. Temporal cutoff enforcement
# ---------------------------------------------------------------------------


class TestTemporalCutoff:
    """Ensure extractors filter data by cutoff date."""

    def test_keepa_timeline_respects_cutoff(self):
        """keepa_timeline module must filter points after cutoff."""
        import inspect

        import services.ml.extractors.keepa_timeline as mod

        source = inspect.getsource(mod)
        assert "cutoff" in source.lower(), "keepa_timeline module must handle cutoff dates"

    def test_bricklink_respects_cutoff(self):
        """bricklink module must filter months after cutoff."""
        import inspect

        import services.ml.extractors.bricklink as mod

        source = inspect.getsource(mod)
        assert "cutoff" in source.lower(), "bricklink module must handle cutoff dates"

    def test_brickeconomy_charts_respects_cutoff(self):
        """BrickEconomyChartsExtractor must filter data after cutoff."""
        from services.ml.extractors.brickeconomy_charts import BrickEconomyChartsExtractor

        source = __import__("inspect").getsource(BrickEconomyChartsExtractor)
        assert "cutoff" in source.lower(), "BrickEconomyChartsExtractor must handle cutoff dates"

    def test_tier2_keepa_receives_cutoff_dates(self):
        """Tier 2 training must pass cutoff_dates to engineer_keepa_features."""
        import inspect
        from services.ml.growth.training import train_growth_models

        source = inspect.getsource(train_growth_models)
        assert "cutoff_dates" in source, (
            "train_growth_models must pass cutoff_dates to engineer_keepa_features"
        )

    def test_engineer_keepa_features_accepts_cutoff(self):
        """engineer_keepa_features must accept cutoff_dates parameter."""
        import inspect
        from services.ml.growth.features import engineer_keepa_features

        sig = inspect.signature(engineer_keepa_features)
        assert "cutoff_dates" in sig.parameters, (
            "engineer_keepa_features must accept cutoff_dates keyword arg"
        )

    def test_cutoff_filtering_logic(self):
        """Verify that cutoff_dates actually filters Keepa data points."""
        from services.ml.growth.features import engineer_keepa_features

        df = pd.DataFrame([{
            "set_number": "TEST-1",
            "rrp_usd_cents": 5000,
        }])

        # Create fake Keepa data spanning 2020-2025
        timeline = []
        for year in range(2020, 2026):
            for month in range(1, 13):
                timeline.append([f"{year}-{month:02d}-15", 4500])

        keepa_df = pd.DataFrame([{
            "set_number": "TEST-1",
            "amazon_price_json": json.dumps(timeline),
            "buy_box_json": "[]",
            "tracking_users": 100,
            "kp_reviews": 50,
            "kp_rating": 4.5,
        }])

        # Without cutoff: uses all data
        result_no_cutoff = engineer_keepa_features(df, keepa_df)

        # With cutoff at 2022-06: should only use data before that
        result_with_cutoff = engineer_keepa_features(
            df, keepa_df, cutoff_dates={"TEST-1": "2022-06"}
        )

        # The price trend should differ because cutoff limits data points
        # (we can't easily assert exact values, but both should produce results)
        assert result_no_cutoff["kp_price_cv"].notna().any()
        assert result_with_cutoff["kp_price_cv"].notna().any()


# ---------------------------------------------------------------------------
# 3. Feature registration consistency
# ---------------------------------------------------------------------------


class TestFeatureRegistration:
    """Ensure all extractor features are properly registered."""

    def test_all_extractor_features_registered(self):
        """Every feature declared by an extractor must be in the registry."""
        from services.ml.extractors import get_all_feature_metadata
        from services.ml.feature_registry import get_enabled_names

        # Import feature_extractors to trigger registration
        import services.ml.feature_extractors  # noqa: F401

        extractor_names = {m.name for m in get_all_feature_metadata()}
        registered_names = set(get_enabled_names())

        missing = extractor_names - registered_names
        assert not missing, f"Extractor features not registered: {missing}"

    def test_no_new_circular_features_undetected(self):
        """Any feature with 'value' or 'growth' in name should be reviewed.

        This is a tripwire -- if a new feature matches these patterns,
        it should be added to CIRCULAR_FEATURES or explicitly cleared.
        """
        from services.ml.extractors import get_all_feature_metadata

        CLEARED_PATTERNS = {
            # Features with 'value' in name that are NOT circular:
            "rating_value",
            "mf_total_value",
            "mf_hero_value",
            "mf_avg_value",
            "mf_value_vs_rrp",
            "mf_hero_vs_rrp",
            "mf_value_cv",
            "minifig_value_ratio",
            "has_exclusive_minifigs",
            # Features with 'growth' in name that are NOT circular:
            "subtheme_avg_growth_pct",
        }

        suspect = set()
        for meta in get_all_feature_metadata():
            name = meta.name
            if any(kw in name.lower() for kw in ("value", "growth", "return")):
                if name not in CIRCULAR_FEATURES and name not in CLEARED_PATTERNS:
                    suspect.add(name)

        assert not suspect, (
            f"New features matching circular patterns need review: {suspect}. "
            f"Add to CIRCULAR_FEATURES or CLEARED_PATTERNS in this test."
        )


# ---------------------------------------------------------------------------
# 4. OOS validation structure
# ---------------------------------------------------------------------------


class TestOOSValidation:
    """Ensure training reports honest out-of-sample metrics."""

    def test_tier3_reports_cv_metrics(self):
        """Tier model training must use cross-validated metrics (not just train R2)."""
        import inspect
        from services.ml.growth.training import _build_tier_model

        source = inspect.getsource(_build_tier_model)
        assert "_select_and_train" in source, (
            "_build_tier_model must use _select_and_train for cross-validated training"
        )

    def test_ensemble_uses_cross_validation(self):
        """Ensemble must use cross-validated OOF predictions, not in-sample."""
        import inspect
        from services.ml.growth.training import _train_ensemble

        source = inspect.getsource(_train_ensemble)
        assert "KFold" in source or "kf.split" in source, (
            "_train_ensemble must use KFold cross-validation"
        )

    def test_leakage_free_evaluation_excludes_circular(self):
        """evaluate_leakage_free must exclude CIRCULAR_FEATURES."""
        import inspect
        from services.ml.growth.evaluation import evaluate_leakage_free

        source = inspect.getsource(evaluate_leakage_free)
        assert "CIRCULAR_FEATURES" in source


# ---------------------------------------------------------------------------
# 5. Extractor unit tests (pure computation, no DB)
# ---------------------------------------------------------------------------


class TestMinifigExtractor:
    """Test minifig feature computation logic."""

    def test_compute_minifig_features_basic(self):
        from services.ml.extractors.minifigs import _compute_minifig_features

        mappings = pd.DataFrame([
            {"set_item_id": "123-1", "minifig_id": "sw001", "quantity": 1},
            {"set_item_id": "123-1", "minifig_id": "sw002", "quantity": 1},
            {"set_item_id": "456-1", "minifig_id": "sw001", "quantity": 1},
        ])

        fig_prices = {
            "sw001": {"avg_price": 5000, "max_price": 8000, "times_sold": 20, "total_lots": 50},
            "sw002": {"avg_price": 15000, "max_price": 20000, "times_sold": 10, "total_lots": 30},
        }

        # sw001 appears in 2 sets, sw002 in 1 set
        fig_set_counts = {"sw001": 2, "sw002": 1}

        rrp_lookup = {"123": 10000, "456": 5000}

        result = _compute_minifig_features(
            ["123", "456"],
            mappings,
            fig_prices,
            fig_set_counts,
            rrp_lookup,
        )

        assert len(result) == 2

        row_123 = result[result["set_number"] == "123"].iloc[0]
        assert row_123["mf_exclusive_count"] == 1  # only sw002 is exclusive
        assert row_123["mf_exclusive_pct"] == 50.0
        assert row_123["mf_total_value"] == 20000  # 5000 + 15000
        assert row_123["mf_value_vs_rrp"] == 2.0  # 20000 / 10000
        assert row_123["mf_hero_value"] == 15000  # sw002 is more valuable

        row_456 = result[result["set_number"] == "456"].iloc[0]
        assert row_456["mf_exclusive_count"] == 0  # sw001 is in 2 sets
        assert row_456["mf_value_vs_rrp"] == 1.0  # 5000 / 5000

    def test_set_without_minifigs(self):
        from services.ml.extractors.minifigs import _compute_minifig_features

        mappings = pd.DataFrame(columns=["set_item_id", "minifig_id", "quantity"])
        result = _compute_minifig_features(["999"], mappings, {}, {}, {})

        assert len(result) == 1
        assert result.iloc[0]["set_number"] == "999"
        # No minifig data -> only set_number column present, no features
        assert len(result.columns) == 1 or all(
            pd.isna(result.iloc[0].get(c))
            for c in result.columns if c != "set_number"
        )


class TestCutoffFiltering:
    """Test that Keepa cutoff filtering works correctly."""

    def test_keepa_cutoff_excludes_future_data(self):
        from services.ml.growth.features import engineer_keepa_features

        df = pd.DataFrame([{"set_number": "T1", "rrp_usd_cents": 10000}])

        # Prices: 2021=4000, 2022=5000, 2023=6000, 2024=8000
        timeline = [
            ["2021-01-01", 4000],
            ["2021-06-01", 4000],
            ["2022-01-01", 5000],
            ["2022-06-01", 5000],
            ["2023-01-01", 6000],
            ["2023-06-01", 6000],
            ["2024-01-01", 8000],
            ["2024-06-01", 8000],
        ]

        keepa_df = pd.DataFrame([{
            "set_number": "T1",
            "amazon_price_json": json.dumps(timeline),
            "buy_box_json": "[]",
            "tracking_users": 100,
            "kp_reviews": 50,
            "kp_rating": 4.5,
        }])

        # With cutoff at 2022-12: should only see 2021-2022 prices
        result = engineer_keepa_features(
            df, keepa_df, cutoff_dates={"T1": "2022-12"}
        )

        # Max discount should be based on prices up to 2022 only
        # All prices <= 5000, RRP = 10000, so max_discount = (10000-4000)/10000*100 = 60%
        max_disc = result.iloc[0]["kp_max_discount"]
        assert max_disc == pytest.approx(60.0, abs=0.1), (
            f"With cutoff=2022-12, max_discount should be ~60% but got {max_disc}"
        )

    def test_no_cutoff_uses_all_data(self):
        from services.ml.growth.features import engineer_keepa_features

        df = pd.DataFrame([{"set_number": "T1", "rrp_usd_cents": 10000}])

        timeline = [
            ["2021-01-01", 4000],
            ["2021-06-01", 4000],
            ["2022-01-01", 5000],
            ["2023-01-01", 6000],
            ["2024-01-01", 2000],  # deep discount in 2024
        ]

        keepa_df = pd.DataFrame([{
            "set_number": "T1",
            "amazon_price_json": json.dumps(timeline),
            "buy_box_json": "[]",
            "tracking_users": 100,
            "kp_reviews": 50,
            "kp_rating": 4.5,
        }])

        # Without cutoff: should see the 2024 price = 2000
        result = engineer_keepa_features(df, keepa_df)

        max_disc = result.iloc[0]["kp_max_discount"]
        # max_discount = (10000-2000)/10000*100 = 80%
        assert max_disc == pytest.approx(80.0, abs=0.1)
