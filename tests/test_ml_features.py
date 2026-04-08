"""Tests for ML feature extraction and registry."""

import pytest


class TestFeatureRegistry:
    def setup_method(self):
        from services.ml.feature_registry import clear

        clear()

    def test_register_and_get(self):
        from services.ml.feature_registry import get, get_all, register

        register("test_feat", "test_table", "A test feature")
        assert len(get_all()) == 1
        feat = get("test_feat")
        assert feat is not None
        assert feat.name == "test_feat"
        assert feat.is_enabled is True

    def test_disable_and_enable(self):
        from services.ml.feature_registry import (
            disable,
            enable,
            get,
            get_enabled,
            register,
        )

        register("feat_a", "table", "Feature A")
        register("feat_b", "table", "Feature B")

        disable("feat_a")
        enabled = get_enabled()
        assert len(enabled) == 1
        assert enabled[0].name == "feat_b"

        enable("feat_a")
        enabled = get_enabled()
        assert len(enabled) == 2

    def test_get_enabled_names(self):
        from services.ml.feature_registry import get_enabled_names, register

        register("x", "t", "X")
        register("y", "t", "Y")
        names = get_enabled_names()
        assert "x" in names
        assert "y" in names


class TestFeatureExtractors:
    def test_imports_register_features(self):
        """Importing feature_extractors should register features."""
        from services.ml.feature_registry import clear, get_all

        clear()
        import importlib

        import services.ml.feature_extractors

        importlib.reload(services.ml.feature_extractors)
        features = get_all()
        assert len(features) > 20  # We register ~30 features

    def test_extract_intrinsics_empty_db(self, tmp_path):
        """Should handle empty database gracefully."""
        from db.connection import get_connection
        from db.schema import init_schema
        from services.ml.feature_extractors import extract_all_features

        conn = get_connection()
        init_schema(conn)

        result = extract_all_features(conn)
        assert result.empty
        conn.close()

    def test_extract_with_data(self, tmp_path):
        """Should extract features for a set with data."""
        from db.connection import get_connection
        from db.schema import init_schema
        from services.ml.feature_extractors import extract_all_features

        conn = get_connection()
        init_schema(conn)

        # Insert a set
        conn.execute("""
            INSERT INTO lego_items
                (id, set_number, title, theme, year_released, year_retired,
                 parts_count, minifig_count, retired_date)
            VALUES
                (1, '75192', 'Millennium Falcon', 'Star Wars', 2017, 2022,
                 7541, 8, '2022-06-01')
        """)

        # Insert BrickEconomy snapshot
        conn.execute("""
            INSERT INTO brickeconomy_snapshots
                (id, set_number, rrp_usd_cents, annual_growth_pct,
                 value_new_cents, review_count, rating_value, scraped_at)
            VALUES
                (1, '75192', 80000, 15.5, 120000, 250, '4.5/5', '2021-01-01')
        """)

        result = extract_all_features(conn, ["75192"])
        assert not result.empty
        assert "75192" in result["set_number"].values

        row = result[result["set_number"] == "75192"].iloc[0]
        assert row["parts_count"] == 7541.0
        assert row["is_licensed"] == 1.0
        assert row["shelf_life_years"] == 5.0

        # BrickEconomy features
        assert row.get("rrp_usd_cents") == 80000.0
        assert row.get("annual_growth_pct") == pytest.approx(15.5)
        assert row.get("value_new_vs_rrp") == pytest.approx(1.5)

        conn.close()


class TestCurrencyConversion:
    def test_usd_passthrough(self):
        from services.ml.currency import to_usd_cents

        assert to_usd_cents(10000, "USD") == 10000

    def test_myr_conversion(self):
        from services.ml.currency import to_usd_cents

        # 10000 MYR cents at ~4.40 rate = ~2273 USD cents
        result = to_usd_cents(10000, "MYR", 2026)
        assert result is not None
        assert 2200 <= result <= 2400

    def test_none_input(self):
        from services.ml.currency import to_usd_cents

        assert to_usd_cents(None, "USD") is None

    def test_unknown_currency(self):
        from services.ml.currency import to_usd_cents

        assert to_usd_cents(10000, "XYZ") is None
