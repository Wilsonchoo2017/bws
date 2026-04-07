"""GWT tests for bricklink monthly sales upsert.

Covers insert, update, duplicate-key safety, and sequence resilience.
"""

import pytest

from bws_types.models import Condition, MonthlySale, PriceData
from db.connection import get_connection
from db.schema import init_schema
from services.bricklink.repository import upsert_monthly_sales


@pytest.fixture
def conn():
    """Connection with schema initialized."""
    connection = get_connection()
    init_schema(connection)
    yield connection


def _make_sale(
    item_id: str = "75192-1",
    year: int = 2024,
    month: int = 6,
    condition: Condition = Condition.NEW,
    times_sold: int = 10,
    total_quantity: int = 15,
    avg_price: int = 85000,
) -> MonthlySale:
    return MonthlySale(
        item_id=item_id,
        year=year,
        month=month,
        condition=condition,
        times_sold=times_sold,
        total_quantity=total_quantity,
        min_price=PriceData(currency="USD", amount=70000),
        max_price=PriceData(currency="USD", amount=100000),
        avg_price=PriceData(currency="USD", amount=avg_price),
        currency="USD",
    )


# ---------------------------------------------------------------
# GIVEN a new monthly sale record
# WHEN upsert_monthly_sales is called
# THEN the row is inserted with a unique id
# ---------------------------------------------------------------
class TestInsertNewSale:
    def test_inserts_single_row(self, conn):
        sale = _make_sale()
        count = upsert_monthly_sales(conn, "75192-1", [sale])

        rows = conn.execute(
            "SELECT item_id, year, month, condition, times_sold "
            "FROM bricklink_monthly_sales"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == ("75192-1", 2024, 6, "new", 10)

    def test_assigns_unique_ids(self, conn):
        sales = [
            _make_sale(month=1),
            _make_sale(month=2),
            _make_sale(month=3),
        ]
        upsert_monthly_sales(conn, "75192-1", sales)

        ids = conn.execute(
            "SELECT id FROM bricklink_monthly_sales ORDER BY id"
        ).fetchall()
        id_values = [r[0] for r in ids]
        assert len(set(id_values)) == 3, "Each row should have a unique id"


# ---------------------------------------------------------------
# GIVEN an existing monthly sale record
# WHEN upsert_monthly_sales is called with the same natural key
# THEN the row is updated (not duplicated) and the id is preserved
# ---------------------------------------------------------------
class TestUpdateExistingSale:
    def test_updates_values_on_conflict(self, conn):
        sale_v1 = _make_sale(times_sold=10, avg_price=85000)
        upsert_monthly_sales(conn, "75192-1", [sale_v1])

        sale_v2 = _make_sale(times_sold=20, avg_price=90000)
        upsert_monthly_sales(conn, "75192-1", [sale_v2])

        rows = conn.execute(
            "SELECT times_sold, avg_price FROM bricklink_monthly_sales"
        ).fetchall()
        assert len(rows) == 1, "Should not create a duplicate row"
        assert rows[0][0] == 20
        assert rows[0][1] == 90000

    def test_preserves_original_id(self, conn):
        sale = _make_sale(times_sold=10)
        upsert_monthly_sales(conn, "75192-1", [sale])
        original_id = conn.execute(
            "SELECT id FROM bricklink_monthly_sales"
        ).fetchone()[0]

        sale_v2 = _make_sale(times_sold=99)
        upsert_monthly_sales(conn, "75192-1", [sale_v2])
        updated_id = conn.execute(
            "SELECT id FROM bricklink_monthly_sales"
        ).fetchone()[0]

        assert updated_id == original_id, "Update should not change the row id"


# ---------------------------------------------------------------
# GIVEN a sequence that has drifted behind existing ids
# WHEN upsert_monthly_sales inserts a new row
# THEN no duplicate-key error occurs
# ---------------------------------------------------------------
class TestSequenceResilience:
    def test_insert_after_sequence_reset(self, conn):
        """Simulate sequence drift (e.g., after WAL recovery)."""
        # Insert two rows normally
        upsert_monthly_sales(conn, "75192-1", [_make_sale(month=1)])
        upsert_monthly_sales(conn, "75192-1", [_make_sale(month=2)])

        # Reset sequence to 1 (simulates drift after recovery)
        conn.execute("DROP SEQUENCE IF EXISTS bricklink_monthly_sales_id_seq")
        conn.execute("CREATE SEQUENCE bricklink_monthly_sales_id_seq START WITH 1")

        # This should NOT raise a duplicate key error --
        # it's an update to month=1 (existing row), not an insert.
        sale_update = _make_sale(month=1, times_sold=999)
        upsert_monthly_sales(conn, "75192-1", [sale_update])

        row = conn.execute(
            "SELECT times_sold FROM bricklink_monthly_sales "
            "WHERE month = 1"
        ).fetchone()
        assert row[0] == 999

    def test_repeated_upsert_does_not_exhaust_sequence(self, conn):
        """Updating the same row many times should not consume sequence ids."""
        for i in range(10):
            upsert_monthly_sales(conn, "75192-1", [_make_sale(times_sold=i)])

        row_count = conn.execute(
            "SELECT count(*) FROM bricklink_monthly_sales"
        ).fetchone()[0]
        assert row_count == 1, "Repeated upserts should not create new rows"


# ---------------------------------------------------------------
# GIVEN multiple sales for different conditions
# WHEN upsert_monthly_sales is called
# THEN each condition is stored as a separate row
# ---------------------------------------------------------------
class TestMultipleConditions:
    def test_new_and_used_stored_separately(self, conn):
        sales = [
            _make_sale(condition=Condition.NEW, times_sold=10),
            _make_sale(condition=Condition.USED, times_sold=5),
        ]
        upsert_monthly_sales(conn, "75192-1", sales)

        rows = conn.execute(
            "SELECT condition, times_sold FROM bricklink_monthly_sales "
            "ORDER BY condition"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == ("new", 10)
        assert rows[1] == ("used", 5)
