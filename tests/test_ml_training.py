"""Tests for ML training pipeline."""

import numpy as np
import pandas as pd
import pytest


class TestFeatureSelection:
    def test_select_with_synthetic_data(self):
        from config.ml import MLPipelineConfig
        from services.ml.feature_selection import select_features

        rng = np.random.RandomState(42)
        n = 100

        # Create features: some informative, some noise
        informative = rng.randn(n)
        target = 2 * informative + rng.randn(n) * 0.5

        df = pd.DataFrame({
            "informative": informative,
            "correlated": informative + rng.randn(n) * 0.1,  # highly correlated
            "noise_1": rng.randn(n),
            "noise_2": rng.randn(n),
            "noise_3": rng.randn(n),
            "weak_signal": 0.3 * informative + rng.randn(n) * 2,
            "target": target,
        })

        config = MLPipelineConfig(max_features=5)
        features = ["informative", "correlated", "noise_1", "noise_2", "noise_3", "weak_signal"]
        result = select_features(df, "target", features, config)

        # informative should be selected
        assert "informative" in result.selected_features
        assert len(result.selected_features) >= 1
        assert len(result.selected_features) <= len(features)

    def test_too_few_samples(self):
        from services.ml.feature_selection import select_features

        df = pd.DataFrame({
            "feat": [1.0, 2.0],
            "target": [0.5, 1.0],
        })
        result = select_features(df, "target", ["feat"])
        assert "feat" in result.selected_features


class TestEvaluation:
    def test_regression_metrics(self):
        from services.ml.evaluation import evaluate_regression

        y_true = np.array([0.1, 0.5, -0.2, 0.8, 0.3, -0.1, 0.6, 0.2, -0.3, 0.4])
        y_pred = np.array([0.15, 0.45, -0.1, 0.75, 0.35, 0.0, 0.55, 0.25, -0.2, 0.35])

        metrics = evaluate_regression(y_true, y_pred, "TestModel", 12)
        assert metrics.r_squared > 0.8
        assert metrics.hit_rate > 0
        assert metrics.model_name == "TestModel"
        assert metrics.horizon_months == 12

    def test_sharpe_like(self):
        from services.ml.evaluation import _compute_sharpe_like

        y_true = np.array([0.1, 0.5, -0.2, 0.8, 0.3, -0.1, 0.6, 0.2, -0.3, 0.4])
        y_pred = np.array([0.15, 0.45, -0.1, 0.75, 0.35, 0.0, 0.55, 0.25, -0.2, 0.35])

        sharpe = _compute_sharpe_like(y_true, y_pred)
        assert sharpe > 0  # Top quintile should have positive returns

    def test_format_table(self):
        from services.ml.evaluation import format_metrics_table
        from services.ml.types import ModelMetrics

        metrics = [
            ModelMetrics(
                model_name="Ridge",
                horizon_months=12,
                task="regression",
                r_squared=0.25,
                hit_rate=0.8,
                quintile_spread=0.15,
                sharpe_like=1.2,
                n_train=100,
                n_test=25,
            )
        ]
        table = format_metrics_table(metrics)
        assert "Ridge" in table
        assert "regression" in table


class TestTrainingSplit:
    def test_chronological_sorting(self, tmp_path):
        """Verify training uses chronological split."""
        import duckdb

        from db.schema import init_schema

        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        init_schema(conn)

        # Insert sets with different retirement years
        for i, yr in enumerate([2018, 2019, 2020, 2021, 2022], start=1):
            conn.execute(
                "INSERT INTO lego_items (id, set_number, year_retired) VALUES (?, ?, ?)",
                [i, f"set_{yr}", yr],
            )

        from services.ml.training import _sort_chronologically

        df = pd.DataFrame({
            "set_number": ["set_2022", "set_2018", "set_2020", "set_2019", "set_2021"],
            "target_return": [0.1, 0.2, 0.3, 0.4, 0.5],
        })

        sorted_df = _sort_chronologically(conn, df)
        years = []
        for sn in sorted_df["set_number"]:
            years.append(int(sn.split("_")[1]))
        assert years == sorted(years)
        conn.close()
