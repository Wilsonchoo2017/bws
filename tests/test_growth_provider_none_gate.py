"""Verify the growth provider gates buy_category to NONE when the set is
missing Keepa or BrickLink data.

The keepa_bl model was trained on Keepa price history AND BrickLink sold
prices. A prediction that fires from zero-sentinel features alone is
blind to the model's strongest signals, so _build_entry must demote it
to category NONE rather than surface GREAT/GOOD/SKIP/WORST.
"""

from __future__ import annotations

from services.ml.growth.types import GrowthPrediction
from services.scoring.growth_provider import _build_entry


def _make_prediction(
    set_number: str,
    buy_category: str,
    great_buy_probability: float = 0.85,
) -> GrowthPrediction:
    return GrowthPrediction(
        set_number=set_number,
        title="LEGO Test Set",
        theme="Test",
        predicted_growth_pct=25.0,
        confidence="high",
        tier=1,
        avoid_probability=0.10,
        great_buy_probability=great_buy_probability,
        good_buy_probability=0.05,
        buy_category=buy_category,
        raw_growth_pct=25.0,
    )


class TestBuildEntryGate:
    def test_both_present_preserves_original_category(self):
        """Given a set with both Keepa and BL data,
        when _build_entry runs,
        then buy_category stays GREAT and is_buy=True."""
        p = _make_prediction("12345", "GREAT")
        entry = _build_entry(
            p,
            model_version="test",
            market_prices={"12345": (3500.0, 3000.0)},
            keepa_set_numbers={"12345"},
        )
        assert entry["buy_category"] == "GREAT"
        assert entry["buy_signal"] is True
        assert entry["avoid"] is False
        assert entry["confidence"] == "high"
        assert entry["has_keepa_data"] is True
        assert entry["has_bl_data"] is True

    def test_missing_keepa_demotes_to_none(self):
        """Given a GREAT prediction for a set with no Keepa row,
        when _build_entry runs,
        then buy_category becomes NONE and buy_signal is False."""
        p = _make_prediction("71808", "GREAT")
        entry = _build_entry(
            p,
            model_version="test",
            market_prices={"71808": (3500.0, 3000.0)},
            keepa_set_numbers=set(),  # empty: 71808 not in the covered set
        )
        assert entry["buy_category"] == "NONE"
        assert entry["buy_signal"] is False
        assert entry["avoid"] is False
        assert entry["confidence"] == "none"
        assert entry["has_keepa_data"] is False
        assert entry["has_bl_data"] is True

    def test_missing_bl_demotes_to_none(self):
        """Given a GREAT prediction for a set with no BL market row,
        when _build_entry runs,
        then buy_category becomes NONE."""
        p = _make_prediction("55555", "GREAT")
        entry = _build_entry(
            p,
            model_version="test",
            market_prices={},  # empty: no BL coverage
            keepa_set_numbers={"55555"},
        )
        assert entry["buy_category"] == "NONE"
        assert entry["buy_signal"] is False
        assert entry["has_keepa_data"] is True
        assert entry["has_bl_data"] is False

    def test_missing_both_demotes_to_none(self):
        """Given a GREAT prediction with no coverage at all,
        when _build_entry runs,
        then buy_category becomes NONE."""
        p = _make_prediction("77777", "GREAT")
        entry = _build_entry(
            p,
            model_version="test",
            market_prices={},
            keepa_set_numbers=set(),
        )
        assert entry["buy_category"] == "NONE"
        assert entry["has_keepa_data"] is False
        assert entry["has_bl_data"] is False

    def test_worst_also_demoted_when_uncovered(self):
        """Given a WORST prediction on an uncovered set,
        when _build_entry runs,
        then category is NONE (not WORST) — without evidence we can't
        confidently claim it's a loser either."""
        p = _make_prediction("88888", "WORST", great_buy_probability=0.05)
        entry = _build_entry(
            p,
            model_version="test",
            market_prices={},
            keepa_set_numbers=set(),
        )
        assert entry["buy_category"] == "NONE"
        assert entry["avoid"] is False  # not coerced to WORST-style avoid

    def test_entry_price_filter_skipped_for_none(self):
        """Given market prices for an uncovered set,
        when _build_entry runs,
        then entry-price filter returns recommended_action=NONE
        rather than BUY/WAIT/HOLD."""
        p = _make_prediction("99999", "GREAT")
        entry = _build_entry(
            p,
            model_version="test",
            market_prices={"99999": (3200.0, 3000.0)},
            keepa_set_numbers=set(),  # no Keepa → gated to NONE
        )
        assert entry["buy_category"] == "NONE"
        assert entry.get("recommended_action") == "NONE"
        assert entry.get("entry_price_ok") is None


class TestBuildEntryLegacyCallers:
    """Callers that don't pass keepa_set_numbers keep the old behavior.

    Backwards compatibility: the gate only activates when the caller
    opts in by passing keepa_set_numbers. Legacy callers that pass only
    market_prices see the original category untouched.
    """

    def test_no_keepa_set_numbers_passes_through(self):
        p = _make_prediction("12345", "GREAT")
        entry = _build_entry(
            p,
            model_version="test",
            market_prices={"12345": (3500.0, 3000.0)},
            # keepa_set_numbers not passed → None → gate bypassed
        )
        assert entry["buy_category"] == "GREAT"
        assert entry["buy_signal"] is True
