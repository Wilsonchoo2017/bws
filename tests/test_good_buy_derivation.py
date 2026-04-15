"""Sanity tests for P(good_buy) derivation and tier classification.

`good_buy_probability` is not trained directly — it's derived at prediction
time from the two trained classifiers:
    P(good_buy) = max(0, min(1, (1 - P(avoid)) - P(great_buy)))

where P(avoid) at threshold=10.0 represents P(APR < 10%) and
P(great_buy) represents P(APR >= 20%).
"""

from __future__ import annotations

import pytest


def _derive(avoid_p: float, great_p: float) -> float:
    return max(0.0, min(1.0, (1.0 - avoid_p) - great_p))


class TestGoodBuyDerivation:
    def test_strong_great_buy_leaves_no_good_room(self):
        # Classifier strongly believes APR >= 20%. Good-buy slice should shrink.
        assert _derive(avoid_p=0.05, great_p=0.90) == pytest.approx(0.05, abs=0.01)

    def test_clean_good_buy_band(self):
        # Model says not-skip (low P(avoid)) but unlikely to hit 20% (low P(great))
        # → the middle tier swells.
        assert _derive(avoid_p=0.10, great_p=0.10) == pytest.approx(0.80, abs=0.01)

    def test_definite_skip(self):
        # High P(avoid) → very little probability mass in the good band.
        assert _derive(avoid_p=0.95, great_p=0.01) == pytest.approx(0.04, abs=0.01)

    def test_clamps_negative_when_classifiers_disagree(self):
        # Poorly calibrated subtraction can produce negative values — clamp to 0.
        # E.g. P(avoid)=0.3, P(great_buy)=0.85 → (0.7 - 0.85) = -0.15 → 0.
        assert _derive(avoid_p=0.30, great_p=0.85) == 0.0

    def test_clamps_above_one(self):
        # Cannot exceed 1.0 even with degenerate classifier outputs.
        assert _derive(avoid_p=0.0, great_p=0.0) == 1.0


class TestTierThresholds:
    """Phase 2 tier shift: avoid threshold 8% -> 10%, good_buy emerges from
    the derived probability, great_buy unchanged at APR >= 20%."""

    def test_hurdle_constants_are_ten_percent(self):
        from services.ml.buy_signal import HURDLE_RATE_12M
        from services.ml.growth.backtest import HURDLE_RATE
        from services.ml.growth.prediction import BUY_HURDLE_PCT

        assert HURDLE_RATE_12M == 10.0
        assert HURDLE_RATE == 10.0
        assert BUY_HURDLE_PCT == 10.0

    def test_good_buy_probability_field_exists(self):
        from services.ml.growth.types import GrowthPrediction

        assert "good_buy_probability" in GrowthPrediction.__dataclass_fields__

    def test_good_buy_threshold_above_zero(self):
        from services.ml.growth.prediction import GOOD_BUY_THRESHOLD

        # Must be a non-trivial threshold to avoid flagging every weak set.
        assert 0.1 <= GOOD_BUY_THRESHOLD <= 0.5
