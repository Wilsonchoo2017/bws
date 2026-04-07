"""Tests for classifier hyperparameter tuning with Optuna."""

import numpy as np
import pytest
from sklearn.datasets import make_classification


@pytest.fixture
def binary_data():
    """Synthetic binary classification data mimicking avoid/keep split."""
    X, y = make_classification(
        n_samples=200, n_features=10, n_informative=5,
        weights=[0.66, 0.34],  # 34% avoid, like real data
        random_state=42,
    )
    return X, y


@pytest.fixture
def growth_data():
    """Synthetic growth data with ~34% below 5% threshold."""
    rng = np.random.RandomState(42)
    X = rng.randn(200, 10)
    y = rng.normal(loc=12.0, scale=10.0, size=200)  # ~34% below 5%
    return X, y


class TestBuildClassifier:
    def test_default_params(self):
        from services.ml.growth.classifier import _build_classifier

        clf = _build_classifier()
        assert hasattr(clf, "fit")
        assert hasattr(clf, "predict_proba")
        assert clf.max_depth == 4
        assert clf.learning_rate == 0.05

    def test_custom_params_override(self):
        from services.ml.growth.classifier import _build_classifier

        clf = _build_classifier({"max_depth": 6, "n_estimators": 300})
        assert clf.max_depth == 6
        assert clf.n_estimators == 300
        # defaults still applied
        assert clf.learning_rate == 0.05


class TestClassifierSearchSpace:
    def test_search_space_keys(self):
        from unittest.mock import MagicMock

        from services.ml.growth.classifier import _get_classifier_search_space

        trial = MagicMock()
        trial.suggest_int.side_effect = lambda name, *a, **kw: 10
        trial.suggest_float.side_effect = lambda name, *a, **kw: 0.5

        params = _get_classifier_search_space(trial)

        expected_keys = {
            "n_estimators", "max_depth", "num_leaves", "min_child_samples",
            "learning_rate", "reg_alpha", "reg_lambda",
            "feature_fraction", "subsample",
        }
        assert set(params.keys()) == expected_keys


class TestTuneClassifier:
    def test_returns_dict(self, binary_data):
        from services.ml.growth.classifier import tune_classifier

        X, y = binary_data
        params = tune_classifier(X, y, n_trials=3, n_splits=2, n_repeats=1)

        assert isinstance(params, dict)
        assert "n_estimators" in params
        assert "max_depth" in params
        assert "learning_rate" in params

    def test_params_in_search_bounds(self, binary_data):
        from services.ml.growth.classifier import tune_classifier

        X, y = binary_data
        params = tune_classifier(X, y, n_trials=5, n_splits=2, n_repeats=1)

        assert 100 <= params["n_estimators"] <= 400
        assert 3 <= params["max_depth"] <= 6
        assert 7 <= params["num_leaves"] <= 31
        assert 5 <= params["min_child_samples"] <= 30
        assert 0.01 <= params["learning_rate"] <= 0.1
        assert 1e-3 <= params["reg_alpha"] <= 1.0
        assert 1e-3 <= params["reg_lambda"] <= 1.0
        assert 0.5 <= params["feature_fraction"] <= 1.0
        assert 0.7 <= params["subsample"] <= 1.0


class TestMakeAvoidLabels:
    def test_threshold_splits(self):
        from services.ml.growth.classifier import make_avoid_labels

        y = np.array([1.0, 4.9, 5.0, 5.1, 20.0])
        labels = make_avoid_labels(y, threshold=5.0)

        np.testing.assert_array_equal(labels, [1, 1, 0, 0, 0])

    def test_custom_threshold(self):
        from services.ml.growth.classifier import make_avoid_labels

        y = np.array([7.0, 8.0, 9.0])
        labels = make_avoid_labels(y, threshold=8.0)

        np.testing.assert_array_equal(labels, [1, 0, 0])


class TestTrainClassifier:
    def test_returns_trained_classifier(self, growth_data):
        from services.ml.growth.classifier import TrainedClassifier, train_classifier

        X, y = growth_data
        features = [f"f{i}" for i in range(10)]
        fills = tuple((f, 0.0) for f in features)

        result = train_classifier(
            X, y, features, fills,
            threshold=5.0, tuning_trials=3,
        )

        assert isinstance(result, TrainedClassifier)
        assert result.cv_auc > 0.0
        assert result.n_avoid > 0
        assert result.n_train == 200

    def test_skip_tuning_when_zero_trials(self, growth_data):
        from services.ml.growth.classifier import TrainedClassifier, train_classifier

        X, y = growth_data
        features = [f"f{i}" for i in range(10)]
        fills = tuple((f, 0.0) for f in features)

        result = train_classifier(
            X, y, features, fills,
            threshold=5.0, tuning_trials=0,
        )

        assert isinstance(result, TrainedClassifier)
        # Still trains with default params
        assert result.cv_auc > 0.0

    def test_returns_none_when_too_few_avoid(self):
        from services.ml.growth.classifier import train_classifier

        rng = np.random.RandomState(42)
        X = rng.randn(100, 5)
        y = rng.normal(loc=50.0, scale=2.0, size=100)  # all well above threshold
        features = [f"f{i}" for i in range(5)]
        fills = tuple((f, 0.0) for f in features)

        result = train_classifier(X, y, features, fills, threshold=5.0)
        assert result is None


class TestPredictAvoidProba:
    def test_probabilities_bounded(self, growth_data):
        from services.ml.growth.classifier import predict_avoid_proba, train_classifier

        X, y = growth_data
        features = [f"f{i}" for i in range(10)]
        fills = tuple((f, 0.0) for f in features)

        clf = train_classifier(X, y, features, fills, tuning_trials=0)
        probs = predict_avoid_proba(X, clf)

        assert probs.shape == (200,)
        assert np.all(probs >= 0.0)
        assert np.all(probs <= 1.0)


class TestHurdleCombine:
    def test_combination_formula(self):
        from services.ml.growth.classifier import hurdle_combine

        reg = np.array([20.0, 30.0])
        avoid_p = np.array([0.0, 1.0])
        median_loser = -5.0

        result = hurdle_combine(reg, avoid_p, median_loser)

        # P(avoid)=0 -> pure regressor
        assert result[0] == pytest.approx(20.0)
        # P(avoid)=1 -> pure median loser
        assert result[1] == pytest.approx(-5.0)

    def test_mixed_probabilities(self):
        from services.ml.growth.classifier import hurdle_combine

        reg = np.array([20.0])
        avoid_p = np.array([0.3])
        median_loser = -10.0

        result = hurdle_combine(reg, avoid_p, median_loser)
        expected = 0.7 * 20.0 + 0.3 * (-10.0)
        assert result[0] == pytest.approx(expected)


class TestCrossValidateWithParams:
    def test_tuned_params_used(self, binary_data):
        from services.ml.growth.classifier import _cross_validate

        X, y = binary_data
        params = {"max_depth": 3, "n_estimators": 50}

        metrics = _cross_validate(X, y, n_splits=2, n_repeats=1, params=params)

        assert metrics.auc_mean > 0.0
        assert metrics.n_total == 200
