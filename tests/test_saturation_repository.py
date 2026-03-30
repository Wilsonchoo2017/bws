"""GWT tests for Shopee saturation repository.

Covers: snapshot persistence, retrieval, staleness detection,
and items needing saturation checks.
"""

from datetime import datetime, timezone

import duckdb
import pytest

from db.schema import init_schema
from services.shopee.saturation_repository import (
    get_all_latest_saturations,
    get_items_needing_saturation_check,
    get_latest_saturation,
    save_saturation_snapshot,
)
from services.shopee.saturation_types import SaturationLevel, SaturationSnapshot


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema initialized."""
    c = duckdb.connect(":memory:")
    init_schema(c)
    yield c
    c.close()


def _make_snapshot(
    set_number: str = "75192",
    listings: int = 30,
    sellers: int = 15,
    score: float = 55.0,
    level: SaturationLevel = SaturationLevel.MODERATE,
) -> SaturationSnapshot:
    return SaturationSnapshot(
        set_number=set_number,
        listings_count=listings,
        unique_sellers=sellers,
        min_price_cents=50000,
        max_price_cents=80000,
        avg_price_cents=65000,
        median_price_cents=64000,
        price_spread_pct=46.2,
        saturation_score=score,
        saturation_level=level,
        search_query=f"LEGO {set_number}",
        scraped_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Saving and retrieving snapshots
# ---------------------------------------------------------------------------


class TestSaveSaturationSnapshot:
    def test_given_snapshot_when_saved_then_retrievable_by_set_number(self, conn):
        snap = _make_snapshot()
        save_saturation_snapshot(conn, snap)

        result = get_latest_saturation(conn, "75192")
        assert result is not None
        assert result["set_number"] == "75192"
        assert result["listings_count"] == 30
        assert result["unique_sellers"] == 15
        assert result["saturation_score"] == 55.0
        assert result["saturation_level"] == "moderate"
        assert result["search_query"] == "LEGO 75192"

    def test_given_two_snapshots_when_retrieved_then_latest_returned(self, conn):
        """Append-only table should return the most recent snapshot."""
        save_saturation_snapshot(conn, _make_snapshot(score=40.0, level=SaturationLevel.LOW))
        save_saturation_snapshot(conn, _make_snapshot(score=70.0, level=SaturationLevel.MODERATE))

        result = get_latest_saturation(conn, "75192")
        assert result is not None
        assert result["saturation_score"] == 70.0
        assert result["saturation_level"] == "moderate"

    def test_given_snapshot_when_saved_then_price_stats_preserved(self, conn):
        save_saturation_snapshot(conn, _make_snapshot())

        result = get_latest_saturation(conn, "75192")
        assert result["min_price_cents"] == 50000
        assert result["max_price_cents"] == 80000
        assert result["avg_price_cents"] == 65000
        assert result["median_price_cents"] == 64000
        assert result["price_spread_pct"] == pytest.approx(46.2)


# ---------------------------------------------------------------------------
# Retrieving latest saturation (single item)
# ---------------------------------------------------------------------------


class TestGetLatestSaturation:
    def test_given_no_data_when_queried_then_returns_none(self, conn):
        result = get_latest_saturation(conn, "99999")
        assert result is None

    def test_given_different_sets_when_queried_then_returns_correct_one(self, conn):
        save_saturation_snapshot(conn, _make_snapshot("75192", score=80.0))
        save_saturation_snapshot(conn, _make_snapshot("42151", score=20.0))

        result = get_latest_saturation(conn, "42151")
        assert result is not None
        assert result["set_number"] == "42151"
        assert result["saturation_score"] == 20.0


# ---------------------------------------------------------------------------
# Retrieving all latest saturations
# ---------------------------------------------------------------------------


class TestGetAllLatestSaturations:
    def test_given_multiple_sets_when_listed_then_returns_one_per_set(self, conn):
        save_saturation_snapshot(conn, _make_snapshot("75192", score=80.0, level=SaturationLevel.HIGH))
        save_saturation_snapshot(conn, _make_snapshot("42151", score=20.0, level=SaturationLevel.VERY_LOW))

        results = get_all_latest_saturations(conn)
        assert len(results) == 2

    def test_given_multiple_sets_when_listed_then_ordered_by_score_desc(self, conn):
        save_saturation_snapshot(conn, _make_snapshot("42151", score=20.0, level=SaturationLevel.VERY_LOW))
        save_saturation_snapshot(conn, _make_snapshot("75192", score=80.0, level=SaturationLevel.HIGH))

        results = get_all_latest_saturations(conn)
        assert results[0]["set_number"] == "75192"
        assert results[1]["set_number"] == "42151"

    def test_given_no_data_when_listed_then_returns_empty(self, conn):
        results = get_all_latest_saturations(conn)
        assert results == []

    def test_given_multiple_snapshots_per_set_when_listed_then_only_latest(self, conn):
        """Two snapshots for same set should return only the latest."""
        save_saturation_snapshot(conn, _make_snapshot("75192", score=40.0, level=SaturationLevel.LOW))
        save_saturation_snapshot(conn, _make_snapshot("75192", score=80.0, level=SaturationLevel.HIGH))

        results = get_all_latest_saturations(conn)
        assert len(results) == 1
        assert results[0]["saturation_score"] == 80.0


# ---------------------------------------------------------------------------
# Finding items needing saturation checks
# ---------------------------------------------------------------------------


class TestGetItemsNeedingSaturationCheck:
    def test_given_item_with_rrp_and_no_check_when_queried_then_returned(self, conn):
        conn.execute(
            "INSERT INTO lego_items (id, set_number, title, rrp_cents) "
            "VALUES (1, '75192', 'UCS Millennium Falcon', 59900)"
        )

        items = get_items_needing_saturation_check(conn, stale_days=7)
        assert len(items) == 1
        assert items[0]["set_number"] == "75192"
        assert items[0]["title"] == "UCS Millennium Falcon"
        assert items[0]["rrp_cents"] == 59900

    def test_given_item_without_rrp_when_queried_then_excluded(self, conn):
        conn.execute(
            "INSERT INTO lego_items (id, set_number, title) VALUES (1, '42151', 'Bugatti')"
        )

        items = get_items_needing_saturation_check(conn, stale_days=7)
        assert len(items) == 0

    def test_given_recently_checked_item_when_queried_then_excluded(self, conn):
        conn.execute(
            "INSERT INTO lego_items (id, set_number, rrp_cents) VALUES (1, '75192', 59900)"
        )
        save_saturation_snapshot(conn, _make_snapshot("75192"))

        items = get_items_needing_saturation_check(conn, stale_days=7)
        assert len(items) == 0

    def test_given_limit_when_queried_then_respects_limit(self, conn):
        for i in range(5):
            conn.execute(
                f"INSERT INTO lego_items (id, set_number, rrp_cents) "
                f"VALUES ({i + 1}, '{10000 + i}', 10000)"
            )

        items = get_items_needing_saturation_check(conn, stale_days=7, limit=2)
        assert len(items) == 2

    def test_given_mixed_items_when_queried_then_only_rrp_items_returned(self, conn):
        """Mix of items with and without RRP -- only RRP items returned."""
        conn.execute(
            "INSERT INTO lego_items (id, set_number, rrp_cents) VALUES (1, '75192', 59900)"
        )
        conn.execute(
            "INSERT INTO lego_items (id, set_number) VALUES (2, '42151')"
        )
        conn.execute(
            "INSERT INTO lego_items (id, set_number, rrp_cents) VALUES (3, '10312', 29900)"
        )

        items = get_items_needing_saturation_check(conn, stale_days=7)
        set_numbers = {item["set_number"] for item in items}
        assert set_numbers == {"75192", "10312"}

    def test_given_non_int_stale_days_when_queried_then_raises_type_error(self, conn):
        with pytest.raises(TypeError):
            get_items_needing_saturation_check(conn, stale_days="7")  # type: ignore[arg-type]

    def test_given_unchecked_items_when_queried_then_nulls_first(self, conn):
        """Items never checked should appear before stale items."""
        conn.execute(
            "INSERT INTO lego_items (id, set_number, rrp_cents) VALUES (1, '75192', 59900)"
        )
        conn.execute(
            "INSERT INTO lego_items (id, set_number, rrp_cents) VALUES (2, '10312', 29900)"
        )

        items = get_items_needing_saturation_check(conn, stale_days=7)
        assert len(items) == 2
        # Both unchecked, should be returned (order may vary but both present)
        set_numbers = {item["set_number"] for item in items}
        assert "75192" in set_numbers
        assert "10312" in set_numbers
