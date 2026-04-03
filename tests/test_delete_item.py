"""GWT tests for delete_item -- cascading deletion across all tables."""

import duckdb
import pytest

from db.schema import init_schema
from services.items.repository import (
    delete_item,
    get_item_detail,
    get_or_create_item,
    item_exists,
    record_price,
)


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema initialized."""
    connection = duckdb.connect(":memory:")
    init_schema(connection)
    yield connection
    connection.close()


def _insert_brickeconomy_snapshot(conn, set_number: str) -> None:
    """Insert a minimal brickeconomy_snapshots row for testing."""
    conn.execute(
        """
        INSERT INTO brickeconomy_snapshots (id, set_number, scraped_at)
        VALUES (nextval('brickeconomy_snapshots_id_seq'), ?, now())
        """,
        [set_number],
    )


def _insert_keepa_snapshot(conn, set_number: str) -> None:
    """Insert a minimal keepa_snapshots row for testing."""
    conn.execute(
        """
        INSERT INTO keepa_snapshots (id, set_number, scraped_at)
        VALUES (nextval('keepa_snapshots_id_seq'), ?, now())
        """,
        [set_number],
    )


def _insert_scrape_task(conn, set_number: str) -> None:
    """Insert a minimal scrape_tasks row for testing."""
    conn.execute(
        """
        INSERT INTO scrape_tasks (id, task_id, set_number, task_type, status)
        VALUES (nextval('scrape_tasks_id_seq'), ?, ?, 'keepa', 'pending')
        """,
        [f"test-{set_number}", set_number],
    )


def _count_rows(conn, table: str, set_number: str) -> int:
    """Count rows for a given set_number in a table."""
    return conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE set_number = ?",  # noqa: S608
        [set_number],
    ).fetchone()[0]


class TestDeleteItemBasic:
    """Given an item exists, verify delete_item removes it."""

    def test_given_existing_item_when_deleted_then_returns_true(self, conn):
        """Given an item in lego_items,
        when delete_item is called,
        then it returns True."""
        get_or_create_item(conn, "12222")
        assert delete_item(conn, "12222") is True

    def test_given_existing_item_when_deleted_then_item_gone(self, conn):
        """Given an item in lego_items,
        when delete_item is called,
        then item_exists returns False."""
        get_or_create_item(conn, "12222")
        delete_item(conn, "12222")
        assert item_exists(conn, "12222") is False

    def test_given_nonexistent_item_when_deleted_then_returns_false(self, conn):
        """Given no item with this set number,
        when delete_item is called,
        then it returns False."""
        assert delete_item(conn, "99999") is False


class TestDeleteItemCascade:
    """Given an item with related records, verify all are cleaned up."""

    def test_given_item_with_prices_when_deleted_then_prices_removed(self, conn):
        """Given an item with price_records,
        when delete_item is called,
        then price_records are also deleted."""
        get_or_create_item(conn, "12222")
        record_price(conn, "12222", "shopee", 9900)
        record_price(conn, "12222", "toysrus", 12900)

        delete_item(conn, "12222")
        assert _count_rows(conn, "price_records", "12222") == 0

    def test_given_item_with_be_snapshot_when_deleted_then_snapshot_removed(self, conn):
        """Given an item with a brickeconomy_snapshots row,
        when delete_item is called,
        then the snapshot is also deleted."""
        get_or_create_item(conn, "12222")
        _insert_brickeconomy_snapshot(conn, "12222")

        delete_item(conn, "12222")
        assert _count_rows(conn, "brickeconomy_snapshots", "12222") == 0

    def test_given_item_with_keepa_snapshot_when_deleted_then_snapshot_removed(self, conn):
        """Given an item with a keepa_snapshots row,
        when delete_item is called,
        then the snapshot is also deleted."""
        get_or_create_item(conn, "12222")
        _insert_keepa_snapshot(conn, "12222")

        delete_item(conn, "12222")
        assert _count_rows(conn, "keepa_snapshots", "12222") == 0

    def test_given_item_with_scrape_task_when_deleted_then_task_removed(self, conn):
        """Given an item with a scrape_tasks row,
        when delete_item is called,
        then the task is also deleted."""
        get_or_create_item(conn, "12222")
        _insert_scrape_task(conn, "12222")

        delete_item(conn, "12222")
        assert _count_rows(conn, "scrape_tasks", "12222") == 0

    def test_given_item_with_image_asset_when_deleted_then_asset_removed(self, conn):
        """Given an item with an image_assets row,
        when delete_item is called,
        then the image asset is also deleted."""
        get_or_create_item(conn, "12222")
        conn.execute(
            """
            INSERT INTO image_assets (id, asset_type, item_id, source_url, local_path, status)
            VALUES (nextval('image_assets_id_seq'), 'set', '12222',
                    'https://example.com/img.png', '/tmp/img.png', 'downloaded')
            """,
        )

        delete_item(conn, "12222")
        count = conn.execute(
            "SELECT COUNT(*) FROM image_assets WHERE item_id = '12222'"
        ).fetchone()[0]
        assert count == 0


class TestDeleteItemIsolation:
    """Given multiple items, verify delete only affects the target."""

    def test_given_two_items_when_one_deleted_then_other_survives(self, conn):
        """Given two items in lego_items,
        when delete_item is called for one,
        then the other item and its prices remain."""
        get_or_create_item(conn, "12222")
        get_or_create_item(conn, "60305")
        record_price(conn, "12222", "shopee", 9900)
        record_price(conn, "60305", "shopee", 19900)

        delete_item(conn, "12222")

        assert item_exists(conn, "60305") is True
        assert _count_rows(conn, "price_records", "60305") == 1
        assert item_exists(conn, "12222") is False
        assert _count_rows(conn, "price_records", "12222") == 0
