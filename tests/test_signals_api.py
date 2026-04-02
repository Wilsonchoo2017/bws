"""GWT tests for signals score in items listing and filtering."""

import duckdb
import pandas as pd
import pytest

from db.schema import init_schema
from services.items.repository import get_all_items, get_or_create_item
from services.backtesting.screener import compute_all_signals


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema initialized."""
    connection = duckdb.connect(":memory:")
    init_schema(connection)
    yield connection
    connection.close()


def _seed_item(conn, set_number: str, title: str = "Test Set", theme: str = "City") -> None:
    """Insert a lego_items row."""
    get_or_create_item(
        conn, set_number, title=title, theme=theme,
        year_released=2023, year_retired=None,
    )


def _seed_bricklink_item(conn, set_number: str) -> None:
    """Insert matching bricklink_items row."""
    item_id = f"{set_number}-1"
    conn.execute(
        """
        INSERT INTO bricklink_items (id, item_id, item_type, title, year_released)
        VALUES (nextval('bricklink_items_id_seq'), ?, 'S', 'Test', 2023)
        ON CONFLICT DO NOTHING
        """,
        [item_id],
    )


def _seed_monthly_sales(
    conn,
    set_number: str,
    months: list[tuple[int, int]],
    avg_prices: list[int],
) -> None:
    """Insert bricklink_monthly_sales rows to generate signals."""
    item_id = f"{set_number}-1"
    _seed_bricklink_item(conn, set_number)
    for (year, month), avg in zip(months, avg_prices):
        conn.execute(
            """
            INSERT INTO bricklink_monthly_sales
            (id, item_id, year, month, condition, times_sold, total_quantity,
             min_price, max_price, avg_price, currency)
            VALUES (nextval('bricklink_monthly_sales_id_seq'), ?, ?, ?, 'new', 10, 10, ?, ?, ?, 'USD')
            """,
            [item_id, year, month, int(avg * 0.8), int(avg * 1.2), avg],
        )


# ---------------------------------------------------------------------------
# Tests: compute_all_signals returns composite_score
# ---------------------------------------------------------------------------


class TestSignalsComputation:
    """Given items with sufficient sales data, composite_score is computed."""

    def test_given_item_with_sales_when_compute_signals_then_score_is_number(self, conn):
        """Given an item with 6 months of sales data,
        When we compute all signals,
        Then the result includes a numeric composite_score.
        """
        _seed_item(conn, "75192")
        months = [(2024, m) for m in range(1, 7)]
        prices = [15000, 15500, 16000, 16500, 17000, 17500]
        _seed_monthly_sales(conn, "75192", months, prices)

        signals = compute_all_signals(conn, condition="new")

        assert len(signals) >= 1
        item_signal = next(s for s in signals if s["set_number"] == "75192")
        assert item_signal["composite_score"] is not None
        assert isinstance(item_signal["composite_score"], (int, float))
        assert 0 <= item_signal["composite_score"] <= 100

    def test_given_item_with_insufficient_data_when_compute_signals_then_excluded(self, conn):
        """Given an item with fewer than 3 months of sales,
        When we compute all signals,
        Then the item is excluded from results.
        """
        _seed_item(conn, "10300")
        _seed_monthly_sales(conn, "10300", [(2024, 1), (2024, 2)], [5000, 5200])

        signals = compute_all_signals(conn, condition="new")

        matching = [s for s in signals if s["set_number"] == "10300"]
        assert len(matching) == 0

    def test_given_multiple_items_when_compute_signals_then_sorted_by_score(self, conn):
        """Given multiple items with different price trajectories,
        When we compute all signals,
        Then results are sorted by composite_score descending.
        """
        for sn in ["10001", "10002", "10003"]:
            _seed_item(conn, sn)
            months = [(2024, m) for m in range(1, 7)]
            prices = [5000 + i * 100 for i in range(6)]
            _seed_monthly_sales(conn, sn, months, prices)

        signals = compute_all_signals(conn, condition="new")

        scores = [s["composite_score"] for s in signals if s["composite_score"] is not None]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Tests: composite_score is not NaN
# ---------------------------------------------------------------------------


class TestSignalsNoNaN:
    """Given any valid signal computation, composite_score must never be NaN."""

    def test_given_flat_prices_when_compute_signals_then_score_not_nan(self, conn):
        """Given an item with completely flat prices,
        When we compute signals,
        Then composite_score is a valid number (not NaN).
        """
        _seed_item(conn, "40001")
        months = [(2024, m) for m in range(1, 7)]
        prices = [5000] * 6
        _seed_monthly_sales(conn, "40001", months, prices)

        signals = compute_all_signals(conn, condition="new")

        matching = [s for s in signals if s["set_number"] == "40001"]
        if matching:
            score = matching[0]["composite_score"]
            if score is not None:
                import math
                assert not math.isnan(score), f"composite_score is NaN for flat prices"

    def test_given_volatile_prices_when_compute_signals_then_score_not_nan(self, conn):
        """Given an item with wildly varying prices,
        When we compute signals,
        Then composite_score is a valid number (not NaN).
        """
        _seed_item(conn, "40002")
        months = [(2024, m) for m in range(1, 7)]
        prices = [1000, 50000, 1000, 50000, 1000, 50000]
        _seed_monthly_sales(conn, "40002", months, prices)

        signals = compute_all_signals(conn, condition="new")

        matching = [s for s in signals if s["set_number"] == "40002"]
        if matching:
            score = matching[0]["composite_score"]
            if score is not None:
                import math
                assert not math.isnan(score), f"composite_score is NaN for volatile prices"


# ---------------------------------------------------------------------------
# Tests: signals response shape matches frontend expectations
# ---------------------------------------------------------------------------


class TestSignalsResponseShape:
    """Given a signals result, the dict shape matches what the frontend expects."""

    def test_given_signal_result_when_check_keys_then_has_set_number_and_score(self, conn):
        """Given an item with sufficient data,
        When we compute signals,
        Then the result has set_number and composite_score fields.
        """
        _seed_item(conn, "75300")
        months = [(2024, m) for m in range(1, 7)]
        prices = [10000, 10500, 11000, 11500, 12000, 12500]
        _seed_monthly_sales(conn, "75300", months, prices)

        signals = compute_all_signals(conn, condition="new")
        item_signal = next(s for s in signals if s["set_number"] == "75300")

        assert "set_number" in item_signal
        assert "composite_score" in item_signal
        assert "item_id" in item_signal
        assert item_signal["set_number"] == "75300"

    def test_given_signal_result_when_json_serialize_then_no_nan_in_output(self, conn):
        """Given a signals result,
        When we serialize to JSON,
        Then the output contains no NaN values (which are invalid JSON).
        """
        import json

        _seed_item(conn, "75301")
        months = [(2024, m) for m in range(1, 7)]
        prices = [10000, 10500, 11000, 11500, 12000, 12500]
        _seed_monthly_sales(conn, "75301", months, prices)

        signals = compute_all_signals(conn, condition="new")
        item_signal = next(s for s in signals if s["set_number"] == "75301")

        # json.dumps will raise ValueError if NaN is present (without allow_nan)
        serialized = json.dumps(item_signal, allow_nan=False)
        assert "NaN" not in serialized


# ---------------------------------------------------------------------------
# Tests: score merge logic (simulating frontend merge by set_number)
# ---------------------------------------------------------------------------


class TestScoreMerge:
    """Given items and signals, merging by set_number produces correct results."""

    def test_given_items_and_signals_when_merge_then_scores_attached(self):
        """Given a list of items and a list of signals,
        When we merge by set_number,
        Then matching items get their composite_score.
        """
        items = [
            {"set_number": "75192", "title": "Falcon"},
            {"set_number": "10300", "title": "DeLorean"},
        ]
        signals = [
            {"set_number": "75192", "item_id": "75192-1", "composite_score": 72.5},
        ]

        score_map = {s["set_number"]: s["composite_score"] for s in signals}
        merged = [{**item, "composite_score": score_map.get(item["set_number"])} for item in items]

        assert merged[0]["composite_score"] == 72.5
        assert merged[1]["composite_score"] is None

    def test_given_signal_with_item_id_suffix_when_merge_by_set_number_then_matches(self):
        """Given a signal where set_number is derived from item_id (stripping -1),
        When we merge by set_number,
        Then the score is correctly attached.
        """
        items = [{"set_number": "75192", "title": "Falcon"}]
        signals = [
            {"set_number": "75192", "item_id": "75192-1", "composite_score": 65.0},
        ]

        score_map = {}
        for sig in signals:
            set_num = sig.get("set_number") or sig["item_id"].removesuffix("-1")
            if sig["composite_score"] is not None:
                score_map[set_num] = sig["composite_score"]

        merged = [{**item, "composite_score": score_map.get(item["set_number"])} for item in items]
        assert merged[0]["composite_score"] == 65.0

    def test_given_signal_with_nan_score_when_merge_then_treated_as_none(self):
        """Given a signal where composite_score is NaN (Python float),
        When we merge by set_number,
        Then the item gets None instead of NaN.
        """
        import math

        items = [{"set_number": "75192", "title": "Falcon"}]
        signals = [
            {"set_number": "75192", "item_id": "75192-1", "composite_score": float("nan")},
        ]

        score_map = {}
        for sig in signals:
            set_num = sig.get("set_number") or sig["item_id"].removesuffix("-1")
            score = sig["composite_score"]
            if score is not None and not (isinstance(score, float) and math.isnan(score)):
                score_map[set_num] = score

        merged = [{**item, "composite_score": score_map.get(item["set_number"])} for item in items]
        assert merged[0]["composite_score"] is None


# ---------------------------------------------------------------------------
# Tests: score filtering logic (simulating frontend filter)
# ---------------------------------------------------------------------------


class TestSanitizeNaN:
    """Given signal dicts with NaN values, _sanitize_nan replaces them with None."""

    def test_given_nan_composite_score_when_sanitize_then_becomes_none(self):
        """Given a signal dict where composite_score is NaN,
        When we sanitize,
        Then composite_score becomes None.
        """
        from api.serialization import sanitize_nan as _sanitize_nan

        data = [{"set_number": "75192", "composite_score": float("nan"), "demand_pressure": 55.0}]
        result = _sanitize_nan(data)

        assert result[0]["composite_score"] is None
        assert result[0]["demand_pressure"] == 55.0
        assert result[0]["set_number"] == "75192"

    def test_given_all_valid_values_when_sanitize_then_unchanged(self):
        """Given a signal dict with no NaN values,
        When we sanitize,
        Then all values remain unchanged.
        """
        from api.serialization import sanitize_nan as _sanitize_nan

        data = [{"set_number": "75192", "composite_score": 72.5, "title": None}]
        result = _sanitize_nan(data)

        assert result[0]["composite_score"] == 72.5
        assert result[0]["title"] is None

    def test_given_multiple_nan_fields_when_sanitize_then_all_replaced(self):
        """Given a signal dict with multiple NaN fields,
        When we sanitize,
        Then all NaN values become None.
        """
        from api.serialization import sanitize_nan as _sanitize_nan

        data = [{"composite_score": float("nan"), "demand_pressure": float("nan"), "price_trend": 60.0}]
        result = _sanitize_nan(data)

        assert result[0]["composite_score"] is None
        assert result[0]["demand_pressure"] is None
        assert result[0]["price_trend"] == 60.0


class TestScoreFilter:
    """Given items with scores, filtering by score threshold works correctly."""

    @pytest.fixture
    def scored_items(self):
        return [
            {"set_number": "A", "composite_score": 80.0},
            {"set_number": "B", "composite_score": 65.0},
            {"set_number": "C", "composite_score": 52.0},
            {"set_number": "D", "composite_score": 40.0},
            {"set_number": "E", "composite_score": 20.0},
            {"set_number": "F", "composite_score": None},
        ]

    def _apply_filter(self, items, score_filter):
        if score_filter == "65+":
            return [i for i in items if i["composite_score"] is not None and i["composite_score"] >= 65]
        elif score_filter == "50+":
            return [i for i in items if i["composite_score"] is not None and i["composite_score"] >= 50]
        elif score_filter == "35+":
            return [i for i in items if i["composite_score"] is not None and i["composite_score"] >= 35]
        elif score_filter == "<35":
            return [i for i in items if i["composite_score"] is not None and i["composite_score"] < 35]
        elif score_filter == "no_score":
            return [i for i in items if i["composite_score"] is None]
        return items

    def test_given_items_when_filter_65_plus_then_only_high_scores(self, scored_items):
        """Given items with various scores,
        When filtering for 65+,
        Then only items with score >= 65 are returned.
        """
        result = self._apply_filter(scored_items, "65+")
        assert [i["set_number"] for i in result] == ["A", "B"]

    def test_given_items_when_filter_50_plus_then_moderate_and_above(self, scored_items):
        """Given items with various scores,
        When filtering for 50+,
        Then items with score >= 50 are returned.
        """
        result = self._apply_filter(scored_items, "50+")
        assert [i["set_number"] for i in result] == ["A", "B", "C"]

    def test_given_items_when_filter_35_plus_then_includes_weak(self, scored_items):
        """Given items with various scores,
        When filtering for 35+,
        Then items with score >= 35 are returned.
        """
        result = self._apply_filter(scored_items, "35+")
        assert [i["set_number"] for i in result] == ["A", "B", "C", "D"]

    def test_given_items_when_filter_below_35_then_only_poor(self, scored_items):
        """Given items with various scores,
        When filtering for <35,
        Then only items with score < 35 are returned.
        """
        result = self._apply_filter(scored_items, "<35")
        assert [i["set_number"] for i in result] == ["E"]

    def test_given_items_when_filter_no_score_then_only_null(self, scored_items):
        """Given items with various scores,
        When filtering for no_score,
        Then only items with null score are returned.
        """
        result = self._apply_filter(scored_items, "no_score")
        assert [i["set_number"] for i in result] == ["F"]

    def test_given_items_when_filter_all_then_everything_returned(self, scored_items):
        """Given items with various scores,
        When filtering for all,
        Then all items are returned.
        """
        result = self._apply_filter(scored_items, "all")
        assert len(result) == 6
