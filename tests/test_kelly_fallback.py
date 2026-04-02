"""Tests for Kelly Criterion neighbor-bin fallback logic."""

import pytest

from config.kelly import NEIGHBOR_FALLBACK_DISCOUNT, SCORE_BIN_LABELS, SCORE_BINS
from services.backtesting.kelly import KellyParams
from services.backtesting.position_sizing import (
    PositionSizing,
    discount_kelly_params,
    find_neighbor_bin,
    size_position,
)


def _make_kelly_params(
    score_bin: str = "Good (65-79)",
    horizon: str = "hold_12m",
    half_kelly: float = 0.10,
    sample_count: int = 60,
) -> KellyParams:
    return KellyParams(
        score_bin=score_bin,
        horizon=horizon,
        win_rate=0.65,
        avg_win=0.30,
        avg_loss=0.10,
        mean_return=0.15,
        return_variance=0.05,
        sample_count=sample_count,
        kelly_fraction=0.20,
        half_kelly=half_kelly,
    )


def _make_table(
    bins: dict[str, float],
) -> dict[str, dict[str, KellyParams]]:
    """Build a minimal Kelly table with one hold horizon per bin."""
    table: dict[str, dict[str, KellyParams]] = {}
    for label, hk in bins.items():
        params = _make_kelly_params(score_bin=label, half_kelly=hk)
        table[label] = {"return_hold_12m": params}
    return table


class TestFindNeighborBin:
    def test_finds_nearest_above(self) -> None:
        table = _make_table({"Neutral (50-64)": 0.08})
        result = find_neighbor_bin("Weak (35-49)", table)
        assert result is not None
        label, horizons = result
        assert label == "Neutral (50-64)"
        assert "return_hold_12m" in horizons

    def test_finds_nearest_below(self) -> None:
        table = _make_table({"Neutral (50-64)": 0.08})
        result = find_neighbor_bin("Good (65-79)", table)
        assert result is not None
        assert result[0] == "Neutral (50-64)"

    def test_prefers_closer_neighbor(self) -> None:
        table = _make_table({
            "Poor (0-34)": 0.05,
            "Good (65-79)": 0.12,
        })
        # Weak is distance 1 from Poor and distance 2 from Good
        result = find_neighbor_bin("Weak (35-49)", table)
        assert result is not None
        assert result[0] == "Poor (0-34)"

    def test_returns_none_when_table_empty(self) -> None:
        result = find_neighbor_bin("Weak (35-49)", {})
        assert result is None

    def test_returns_none_for_unknown_bin(self) -> None:
        table = _make_table({"Good (65-79)": 0.10})
        result = find_neighbor_bin("Unknown Bin", table)
        assert result is None

    def test_edge_bin_poor_searches_upward(self) -> None:
        table = _make_table({"Neutral (50-64)": 0.08})
        result = find_neighbor_bin("Poor (0-34)", table)
        assert result is not None
        assert result[0] == "Neutral (50-64)"

    def test_edge_bin_strong_searches_downward(self) -> None:
        table = _make_table({"Good (65-79)": 0.12})
        result = find_neighbor_bin("Strong (80+)", table)
        assert result is not None
        assert result[0] == "Good (65-79)"


class TestDiscountKellyParams:
    def test_scales_half_kelly(self) -> None:
        params = _make_kelly_params(half_kelly=0.10)
        discounted = discount_kelly_params(params, 0.6)
        assert discounted.half_kelly == 0.06

    def test_preserves_other_fields(self) -> None:
        params = _make_kelly_params(half_kelly=0.10, sample_count=50)
        discounted = discount_kelly_params(params, 0.6)
        assert discounted.win_rate == params.win_rate
        assert discounted.avg_win == params.avg_win
        assert discounted.avg_loss == params.avg_loss
        assert discounted.mean_return == params.mean_return
        assert discounted.kelly_fraction == params.kelly_fraction
        assert discounted.sample_count == params.sample_count

    def test_returns_new_instance(self) -> None:
        params = _make_kelly_params(half_kelly=0.10)
        discounted = discount_kelly_params(params, 0.6)
        assert discounted is not params
        assert params.half_kelly == 0.10  # original unchanged


class TestSizePositionFallback:
    def _item_signals(self, score: float) -> dict:
        return {
            "set_number": "75192-1",
            "composite_score": score,
            "entry_price_cents": 50000,
        }

    def test_fallback_produces_nonzero_allocation(self) -> None:
        table = _make_table({"Neutral (50-64)": 0.10})
        result = size_position(self._item_signals(40.0), table)
        assert result.recommended_pct > 0.0

    def test_fallback_caps_confidence_at_low(self) -> None:
        table = _make_table({"Neutral (50-64)": 0.10})
        result = size_position(self._item_signals(40.0), table)
        assert result.confidence in ("low", "insufficient")

    def test_fallback_adds_extrapolation_warning(self) -> None:
        table = _make_table({"Neutral (50-64)": 0.10})
        result = size_position(self._item_signals(40.0), table)
        assert any("Extrapolated from" in w for w in result.warnings)
        assert any("discounted" in w.lower() for w in result.warnings)

    def test_fallback_discounts_half_kelly(self) -> None:
        table = _make_table({"Neutral (50-64)": 0.10})
        result = size_position(self._item_signals(40.0), table)
        # The hold half_kelly should be 0.10 * 0.6 = 0.06
        assert result.hold is not None
        assert result.hold.half_kelly == pytest.approx(
            0.10 * NEIGHBOR_FALLBACK_DISCOUNT, abs=0.001
        )

    def test_normal_path_unaffected(self) -> None:
        table = _make_table({
            "Weak (35-49)": 0.08,
            "Neutral (50-64)": 0.10,
        })
        result = size_position(self._item_signals(40.0), table)
        # Should use Weak's own data, no fallback warnings
        assert not any("Extrapolated" in w for w in result.warnings)
        assert result.hold is not None
        assert result.hold.half_kelly == 0.08

    def test_truly_empty_table_returns_insufficient(self) -> None:
        result = size_position(self._item_signals(40.0), {})
        assert result.confidence == "insufficient"
        assert result.recommended_pct == 0.0
        assert result.flip is None
        assert result.hold is None

    def test_fallback_with_budget(self) -> None:
        table = _make_table({"Neutral (50-64)": 0.10})
        result = size_position(
            self._item_signals(40.0), table, budget_cents=500000
        )
        assert result.recommended_amount_cents is not None
        assert result.recommended_amount_cents > 0
