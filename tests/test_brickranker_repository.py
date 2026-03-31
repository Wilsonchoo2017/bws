"""GWT tests for BrickRanker repository — covers upsert, batch, and PK edge cases.

Focuses on the duplicate-key crash that occurs when DuckDB sequences
fall out of sync with existing data.
"""

import duckdb
import pytest

from db.schema import init_schema
from services.brickranker.parser import RetirementItem
from services.brickranker.repository import (
    batch_upsert_items,
    count_items,
    get_item,
    get_retiring_soon_items,
    list_items,
    upsert_item,
)


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema initialized."""
    connection = duckdb.connect(":memory:")
    init_schema(connection)
    yield connection
    connection.close()


def _make_retirement_item(
    set_number: str = "75192",
    set_name: str = "Millennium Falcon",
    **overrides,
) -> RetirementItem:
    defaults = {
        "set_number": set_number,
        "set_name": set_name,
        "year_released": 2017,
        "retiring_soon": False,
        "expected_retirement_date": None,
        "theme": "Star Wars",
        "image_url": "https://example.com/75192.jpg",
    }
    return RetirementItem(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Basic upsert
# ---------------------------------------------------------------------------


class TestUpsertItem:
    """Given a RetirementItem, when upserting, then the row is persisted."""

    def test_given_new_item_when_upsert_then_inserted(self, conn):
        item = _make_retirement_item()
        item_id = upsert_item(conn, item)

        assert item_id > 0
        row = get_item(conn, "75192")
        assert row is not None
        assert row["set_name"] == "Millennium Falcon"
        assert row["theme"] == "Star Wars"

    def test_given_existing_item_when_upsert_then_updated(self, conn):
        item_v1 = _make_retirement_item(retiring_soon=False)
        upsert_item(conn, item_v1)

        item_v2 = _make_retirement_item(retiring_soon=True)
        item_id = upsert_item(conn, item_v2)

        row = get_item(conn, "75192")
        assert row is not None
        assert row["retiring_soon"] is True
        assert row["id"] == item_id

    def test_given_upsert_when_checking_id_then_stable_across_updates(self, conn):
        item = _make_retirement_item()
        id_first = upsert_item(conn, item)
        id_second = upsert_item(conn, item)

        assert id_first == id_second


# ---------------------------------------------------------------------------
# Batch upsert
# ---------------------------------------------------------------------------


class TestBatchUpsertItems:
    """Given a list of items, when batch upserting, then stats are correct."""

    def test_given_empty_table_when_batch_then_all_created(self, conn):
        items = [
            _make_retirement_item("10001", "Set A"),
            _make_retirement_item("10002", "Set B"),
            _make_retirement_item("10003", "Set C"),
        ]

        stats = batch_upsert_items(conn, items)

        assert stats["created"] == 3
        assert stats["updated"] == 0
        assert stats["total"] == 3

    def test_given_existing_items_when_batch_then_updated_count(self, conn):
        upsert_item(conn, _make_retirement_item("10001", "Set A"))
        upsert_item(conn, _make_retirement_item("10002", "Set B"))

        items = [
            _make_retirement_item("10001", "Set A Updated"),
            _make_retirement_item("10002", "Set B Updated"),
            _make_retirement_item("10003", "Set C New"),
        ]

        stats = batch_upsert_items(conn, items)

        assert stats["created"] == 1
        assert stats["updated"] == 2

    def test_given_items_not_in_batch_when_batch_then_marked_inactive(self, conn):
        upsert_item(conn, _make_retirement_item("10001", "Set A"))
        upsert_item(conn, _make_retirement_item("10002", "Set B"))

        # Batch only contains 10001 -- 10002 should be marked inactive
        batch_upsert_items(conn, [_make_retirement_item("10001", "Set A")])

        row = get_item(conn, "10002")
        assert row is not None
        assert row["is_active"] is False


# ---------------------------------------------------------------------------
# Primary key collision edge cases (the crash root cause)
# ---------------------------------------------------------------------------


class TestNoDuplicateKeyOnInsert:
    """Given pre-existing data, when inserting new items, then no PK collision.

    This class tests the exact scenario that caused the fatal DuckDB crash:
    sequences falling out of sync with existing data.
    """

    def test_given_preseeded_rows_when_insert_new_then_no_pk_collision(self, conn):
        """Simulate data that exists before init_schema syncs sequences."""
        # Manually insert rows with explicit IDs (simulating pre-existing data)
        conn.execute(
            "INSERT INTO brickranker_items (id, set_number, set_name) "
            "VALUES (1, '10001', 'Set A')"
        )
        conn.execute(
            "INSERT INTO brickranker_items (id, set_number, set_name) "
            "VALUES (2, '10002', 'Set B')"
        )

        # Re-sync sequences (as init_schema would on restart)
        init_schema(conn)

        # Now insert a new item -- should NOT collide with id 1 or 2
        item = _make_retirement_item("99999", "New Set")
        item_id = upsert_item(conn, item)

        assert item_id > 2
        assert get_item(conn, "99999") is not None

    def test_given_gap_in_ids_when_insert_then_no_collision(self, conn):
        """IDs with gaps (e.g., 1, 3, 5) should not cause collisions."""
        conn.execute(
            "INSERT INTO brickranker_items (id, set_number, set_name) "
            "VALUES (1, '10001', 'A')"
        )
        conn.execute(
            "INSERT INTO brickranker_items (id, set_number, set_name) "
            "VALUES (5, '10005', 'E')"
        )

        init_schema(conn)

        item = _make_retirement_item("99999", "New")
        item_id = upsert_item(conn, item)

        assert item_id > 5

    def test_given_many_preseeded_when_batch_insert_then_unique_ids(self, conn):
        """Batch insert of many new items after pre-seeding must produce unique IDs."""
        for i in range(1, 11):
            conn.execute(
                "INSERT INTO brickranker_items (id, set_number, set_name) "
                f"VALUES ({i}, '{10000 + i}', 'Set {i}')"
            )

        init_schema(conn)

        new_items = [
            _make_retirement_item(f"{20000 + i}", f"New Set {i}")
            for i in range(1, 21)
        ]
        batch_upsert_items(conn, new_items)

        # Verify all IDs are unique
        rows = conn.execute("SELECT id FROM brickranker_items").fetchall()
        ids = [r[0] for r in rows]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {ids}"
        assert len(ids) == 30  # 10 pre-seeded + 20 new

    def test_given_second_connection_preseeded_when_new_conn_inserts_then_safe(self):
        """Two connections to the same DB must not generate duplicate IDs.

        This reproduces the production scenario: the API server has one
        connection, the worker creates another.
        """
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.duckdb")

            # Connection 1: seed data
            conn1 = duckdb.connect(db_path)
            init_schema(conn1)
            for i in range(1, 6):
                upsert_item(conn1, _make_retirement_item(f"{10000 + i}", f"Set {i}"))
            conn1.close()

            # Connection 2: insert new items (simulates worker)
            conn2 = duckdb.connect(db_path)
            init_schema(conn2)
            item = _make_retirement_item("99999", "Worker Set")
            item_id = upsert_item(conn2, item)
            assert item_id > 5

            # Verify no duplicate IDs
            rows = conn2.execute("SELECT id FROM brickranker_items").fetchall()
            ids = [r[0] for r in rows]
            assert len(ids) == len(set(ids))
            conn2.close()

    def test_given_concurrent_connections_when_both_insert_then_no_collision(self):
        """Two connections open simultaneously must not collide on IDs."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.duckdb")

            # Setup
            conn_setup = duckdb.connect(db_path)
            init_schema(conn_setup)
            upsert_item(conn_setup, _make_retirement_item("10001", "Existing"))
            conn_setup.close()

            # Two connections open at the same time
            conn_a = duckdb.connect(db_path)
            conn_b = duckdb.connect(db_path)
            init_schema(conn_a)
            init_schema(conn_b)

            # Connection A inserts
            upsert_item(conn_a, _make_retirement_item("20001", "From A"))

            # Connection B inserts (must not collide with A's insert)
            upsert_item(conn_b, _make_retirement_item("20002", "From B"))

            conn_a.close()

            rows = conn_b.execute("SELECT id FROM brickranker_items").fetchall()
            ids = [r[0] for r in rows]
            assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"
            conn_b.close()


# ---------------------------------------------------------------------------
# Sequence sync after init_schema
# ---------------------------------------------------------------------------


class TestSequenceSyncOnInit:
    """Given stale sequences, when init_schema runs, then sequences are synced."""

    def test_given_manual_inserts_when_init_then_sequence_past_max(self, conn):
        """init_schema must advance the sequence past existing MAX(id)."""
        conn.execute(
            "INSERT INTO brickranker_items (id, set_number, set_name) "
            "VALUES (100, '10100', 'High ID Set')"
        )

        init_schema(conn)

        # The next auto-generated id must be > 100
        item = _make_retirement_item("99999", "After Sync")
        item_id = upsert_item(conn, item)
        assert item_id > 100

    def test_given_empty_table_when_init_then_sequence_starts_at_1(self, conn):
        item = _make_retirement_item()
        item_id = upsert_item(conn, item)
        assert item_id >= 1


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------


class TestListAndFilter:
    """Given persisted items, when querying, then correct results returned."""

    def test_given_active_and_inactive_when_list_active_only(self, conn):
        upsert_item(conn, _make_retirement_item("10001", "Active"))
        upsert_item(conn, _make_retirement_item("10002", "Will Deactivate"))

        conn.execute(
            "UPDATE brickranker_items SET is_active = FALSE WHERE set_number = '10002'"
        )

        active = list_items(conn, active_only=True)
        assert len(active) == 1
        assert active[0]["set_number"] == "10001"

    def test_given_retiring_items_when_get_retiring_soon(self, conn):
        upsert_item(conn, _make_retirement_item("10001", "Retiring", retiring_soon=True))
        upsert_item(conn, _make_retirement_item("10002", "Not Retiring", retiring_soon=False))

        retiring = get_retiring_soon_items(conn)
        assert len(retiring) == 1
        assert retiring[0]["set_number"] == "10001"

    def test_given_retiring_item_when_upsert_then_lego_items_retiring_soon_set(self, conn):
        """Given a retiring item, when upserting, then lego_items.retiring_soon is True."""
        upsert_item(conn, _make_retirement_item("10001", "Retiring Set", retiring_soon=True))

        row = conn.execute(
            "SELECT retiring_soon FROM lego_items WHERE set_number = '10001'"
        ).fetchone()
        assert row is not None
        assert row[0] is True

    def test_given_existing_item_when_update_retiring_soon_then_lego_items_updated(self, conn):
        """Given an existing item, when updating retiring_soon via upsert,
        then lego_items reflects the change."""
        upsert_item(conn, _make_retirement_item("10001", "Set A", retiring_soon=False))

        row = conn.execute(
            "SELECT retiring_soon FROM lego_items WHERE set_number = '10001'"
        ).fetchone()
        assert row[0] is False

        upsert_item(conn, _make_retirement_item("10001", "Set A", retiring_soon=True))

        row = conn.execute(
            "SELECT retiring_soon FROM lego_items WHERE set_number = '10001'"
        ).fetchone()
        assert row[0] is True

    def test_given_items_when_count_then_correct_stats(self, conn):
        upsert_item(conn, _make_retirement_item("10001", "A", retiring_soon=True))
        upsert_item(conn, _make_retirement_item("10002", "B", retiring_soon=False))

        stats = count_items(conn)
        assert stats["total"] == 2
        assert stats["active"] == 2
        assert stats["retiring_soon"] == 1


# ---------------------------------------------------------------------------
# PK index repair (DuckDB corruption recovery)
# ---------------------------------------------------------------------------


class TestWalRecoveryRebuild:
    """Given WAL-detected corruption, when tables are rebuilt, then data is preserved."""

    def test_given_healthy_table_when_rebuild_then_data_preserved(self, conn):
        """Rebuild preserves all rows and indexes."""
        from db.schema import _rebuild_all_tables

        upsert_item(conn, _make_retirement_item("10001", "A"))
        upsert_item(conn, _make_retirement_item("10002", "B"))

        _rebuild_all_tables(conn)

        assert count_items(conn)["total"] == 2
        assert get_item(conn, "10001") is not None
        assert get_item(conn, "10002") is not None

    def test_given_rebuilt_table_when_upsert_then_works(self, conn):
        """After rebuild, both UPDATE and INSERT paths work."""
        from db.schema import _rebuild_all_tables

        upsert_item(conn, _make_retirement_item("10001", "A"))

        _rebuild_all_tables(conn)
        init_schema(conn)  # re-sync sequences

        # UPDATE path
        upsert_item(conn, _make_retirement_item("10001", "A Updated", retiring_soon=True))
        row = get_item(conn, "10001")
        assert row["set_name"] == "A Updated"
        assert row["retiring_soon"] is True

        # INSERT path
        upsert_item(conn, _make_retirement_item("10002", "B New"))
        assert get_item(conn, "10002") is not None

    def test_given_wal_file_when_get_connection_then_triggers_rebuild(self):
        """WAL file presence triggers table rebuild on first connection."""
        import tempfile
        from pathlib import Path

        from db.connection import _handle_wal_recovery

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            wal_path = Path(f"{db_path}.wal")

            # No WAL → no recovery needed
            assert _handle_wal_recovery(db_path) is False

            # Create fake WAL → recovery triggered
            wal_path.write_bytes(b"fake wal data")
            assert _handle_wal_recovery(db_path) is True
            assert not wal_path.exists()
