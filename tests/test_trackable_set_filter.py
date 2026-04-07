"""GWT tests for non-trackable item filtering across ingestion, scrape queue, and catalog."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from db.connection import get_connection
from db.schema import init_schema
from services.items.repository import (
    NON_RETAIL_THEMES,
    get_or_create_item,
    is_trackable_set,
    item_exists,
    purge_non_trackable_items,
)
from services.scrape_queue.models import TaskType
from services.scrape_queue.repository import create_task, create_tasks_for_set


@pytest.fixture
def conn():
    """Test DB connection with schema initialized."""
    c = get_connection()
    init_schema(c)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# is_trackable_set -- pure logic
# ---------------------------------------------------------------------------


class TestIsTrackableSet:
    """Given various set numbers and themes, verify trackability classification."""

    @pytest.mark.parametrize(
        "set_number,expected",
        [
            ("75192", True),
            ("10300", True),
            ("42151", True),
            ("21282", True),
            ("60400", True),
        ],
    )
    def test_given_numeric_set_number_when_checking_then_trackable(
        self, set_number: str, expected: bool
    ):
        """Given a numeric set number, when checking trackability, then returns True."""
        assert is_trackable_set(set_number) is expected

    @pytest.mark.parametrize(
        "set_number",
        ["col24", "col20", "colsh", "collt", "coltm", "FNIK", "BILLY", "WILL",
         "BMU01", "BMU02", "SCHUR", "YURT", "UNITY", "ST", "lwp13", "lwp14"],
    )
    def test_given_non_numeric_set_number_when_checking_then_not_trackable(
        self, set_number: str
    ):
        """Given a non-numeric set number, when checking trackability, then returns False."""
        assert is_trackable_set(set_number) is False

    def test_given_polybag_set_number_when_checking_then_not_trackable(self):
        """Given a 6+ digit set number (polybag), when checking, then returns False."""
        assert is_trackable_set("892291") is False

    def test_given_set_with_variant_suffix_when_checking_then_trackable(self):
        """Given a set number with dash-variant suffix, when checking, then returns True."""
        assert is_trackable_set("75192-1") is True

    @pytest.mark.parametrize("theme", sorted(NON_RETAIL_THEMES))
    def test_given_non_retail_theme_when_checking_then_not_trackable(
        self, theme: str
    ):
        """Given a numeric set number with a non-retail theme, when checking,
        then returns False."""
        assert is_trackable_set("99999", theme) is False

    def test_given_retail_theme_when_checking_then_trackable(self):
        """Given a numeric set number with a retail theme, when checking,
        then returns True."""
        assert is_trackable_set("75192", "Star Wars") is True

    def test_given_sculptures_theme_when_checking_then_trackable(self):
        """Given a Sculptures theme set (e.g. 10276 Colosseum), when checking,
        then returns True -- Sculptures contains retail Icons/Creator Expert sets."""
        assert is_trackable_set("10276", "Sculptures") is True

    def test_given_none_theme_when_checking_then_trackable(self):
        """Given no theme information, when checking a numeric set, then returns True."""
        assert is_trackable_set("75192", None) is True


# ---------------------------------------------------------------------------
# get_or_create_item -- ingestion gate
# ---------------------------------------------------------------------------


class TestIngestionFiltering:
    """Given non-trackable items, verify get_or_create_item rejects them."""

    def test_given_non_numeric_set_when_creating_then_not_inserted(self, conn):
        """Given a non-numeric set number like 'col24', when calling get_or_create_item,
        then the item is not inserted into lego_items."""
        get_or_create_item(conn, "col24", title="Football Referee, Series 24")

        assert item_exists(conn, "col24") is False

    def test_given_promotional_theme_when_creating_then_not_inserted(self, conn):
        """Given a set with Promotional theme, when calling get_or_create_item,
        then the item is not inserted."""
        get_or_create_item(conn, "40599", title="Houses of the World 4", theme="Promotional")

        assert item_exists(conn, "40599") is False

    def test_given_collectible_minifigures_theme_when_creating_then_not_inserted(self, conn):
        """Given a set with Collectible Minifigures theme, when calling get_or_create_item,
        then the item is not inserted."""
        get_or_create_item(conn, "71039", title="Marvel CMF Series 2", theme="Collectible Minifigures")

        assert item_exists(conn, "71039") is False

    def test_given_retail_set_when_creating_then_inserted(self, conn):
        """Given a normal retail set, when calling get_or_create_item,
        then the item is inserted."""
        get_or_create_item(conn, "75192", title="Millennium Falcon", theme="Star Wars")

        assert item_exists(conn, "75192") is True

    def test_given_polybag_when_creating_then_not_inserted(self, conn):
        """Given a polybag set number (6+ digits), when calling get_or_create_item,
        then the item is not inserted."""
        get_or_create_item(conn, "892291", title="Some Foil Pack")

        assert item_exists(conn, "892291") is False


# ---------------------------------------------------------------------------
# create_task / create_tasks_for_set -- scrape queue gate
# ---------------------------------------------------------------------------


class TestScrapeQueueFiltering:
    """Given non-trackable items, verify scrape tasks are not created."""

    def test_given_non_numeric_set_when_creating_task_then_returns_none(self, conn):
        """Given a non-numeric set number, when calling create_task,
        then returns None without creating a task."""
        task = create_task(conn, "FNIK", TaskType.KEEPA)

        assert task is None

    def test_given_non_numeric_set_when_creating_tasks_for_set_then_empty(self, conn):
        """Given a non-numeric set number, when calling create_tasks_for_set,
        then returns empty list."""
        tasks = create_tasks_for_set(conn, "col24")

        assert tasks == []

    def test_given_polybag_when_creating_tasks_for_set_then_empty(self, conn):
        """Given a polybag set number, when calling create_tasks_for_set,
        then returns empty list."""
        tasks = create_tasks_for_set(conn, "892291")

        assert tasks == []

    def test_given_retail_set_when_creating_task_then_task_created(self, conn):
        """Given a valid retail set number, when calling create_task,
        then task is created successfully."""
        task = create_task(conn, "75192", TaskType.KEEPA)

        assert task is not None
        assert task.set_number == "75192"
        assert task.task_type == TaskType.KEEPA


# ---------------------------------------------------------------------------
# extract_set_numbers_from_catalog -- catalog import gate
# ---------------------------------------------------------------------------


class TestCatalogExtraction:
    """Given BrickLink catalog items, verify non-trackable items are filtered out."""

    def _make_catalog_item(
        self, item_id: str, item_type: str = "S"
    ) -> Any:
        """Create a mock BrickLink catalog item."""
        item = MagicMock()
        item.item_id = item_id
        item.item_type = item_type
        return item

    def test_given_mixed_catalog_when_extracting_then_only_trackable_returned(self):
        """Given catalog items including non-numeric IDs and polybags,
        when extracting set numbers, then only trackable sets are returned."""
        from api.workers.transforms import extract_set_numbers_from_catalog

        items = [
            self._make_catalog_item("75192-1"),      # valid retail set
            self._make_catalog_item("col24-12"),      # CMF -- non-numeric
            self._make_catalog_item("FNIK-1"),        # promo -- non-numeric
            self._make_catalog_item("42151-1"),       # valid retail set
            self._make_catalog_item("892291-1"),      # polybag
        ]

        result = extract_set_numbers_from_catalog(items)

        assert sorted(result) == ["42151", "75192"]

    def test_given_only_valid_sets_when_extracting_then_all_returned(self):
        """Given only valid retail catalog items, when extracting, then all returned."""
        from api.workers.transforms import extract_set_numbers_from_catalog

        items = [
            self._make_catalog_item("75192-1"),
            self._make_catalog_item("10300-1"),
            self._make_catalog_item("42151-1"),
        ]

        result = extract_set_numbers_from_catalog(items)

        assert sorted(result) == ["10300", "42151", "75192"]

    def test_given_non_set_type_when_extracting_then_filtered(self):
        """Given catalog items of type 'M' (minifigures), when extracting,
        then they are excluded."""
        from api.workers.transforms import extract_set_numbers_from_catalog

        items = [
            self._make_catalog_item("75192-1", item_type="S"),
            self._make_catalog_item("sw0001-1", item_type="M"),
        ]

        result = extract_set_numbers_from_catalog(items)

        assert result == ["75192"]


# ---------------------------------------------------------------------------
# purge_non_trackable_items
# ---------------------------------------------------------------------------


class TestPurgeNonTrackable:
    """Given existing non-trackable items, verify purge removes them."""

    def test_given_non_numeric_item_when_purging_then_deleted(self, conn):
        """Given a non-numeric set number item was previously inserted,
        when purging, then it is removed."""
        # Bypass the filter by inserting directly
        conn.execute(
            """
            INSERT INTO lego_items (id, set_number, title)
            VALUES (nextval('lego_items_id_seq'), ?, ?)
            """,
            ["TESTX", "Test Non-Numeric"],
        )
        assert item_exists(conn, "TESTX") is True

        deleted = purge_non_trackable_items(conn)

        assert "TESTX" in deleted
        assert item_exists(conn, "TESTX") is False

    def test_given_non_retail_theme_item_when_purging_then_deleted(self, conn):
        """Given an item with a non-retail theme was previously inserted,
        when purging, then it is removed."""
        conn.execute(
            """
            INSERT INTO lego_items (id, set_number, title, theme)
            VALUES (nextval('lego_items_id_seq'), ?, ?, ?)
            """,
            ["99998", "Test Promo", "Promotional"],
        )
        assert item_exists(conn, "99998") is True

        deleted = purge_non_trackable_items(conn)

        assert "99998" in deleted
        assert item_exists(conn, "99998") is False

    def test_given_only_retail_items_when_purging_then_none_deleted(self, conn):
        """Given only retail items exist, when purging, then nothing is deleted."""
        get_or_create_item(conn, "75192", title="Millennium Falcon", theme="Star Wars")

        deleted = purge_non_trackable_items(conn)

        assert "75192" not in deleted
        assert item_exists(conn, "75192") is True
