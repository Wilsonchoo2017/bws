"""Tests for portfolio repository -- FIFO P&L, holdings, sell validation."""

import pytest

import duckdb

from db.schema import init_schema
from services.portfolio.repository import (
    create_transaction,
    delete_transaction,
    get_holdings,
    get_holding_detail,
    get_portfolio_summary,
    get_transaction,
    list_transactions,
    _fifo_cost_basis,
    _fifo_realized_pl,
)


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema initialized."""
    c = duckdb.connect(":memory:")
    init_schema(c)
    yield c
    c.close()


@pytest.fixture
def seed_item(conn):
    """Insert a lego_items row and a price record for testing."""

    def _seed(
        set_number: str = "75192",
        title: str = "Millennium Falcon",
        price_cents: int = 50000,
    ):
        conn.execute(
            """
            INSERT INTO lego_items (id, set_number, title, theme)
            VALUES (nextval('lego_items_id_seq'), ?, ?, 'Star Wars')
            """,
            [set_number, title],
        )
        conn.execute(
            """
            INSERT INTO price_records (id, set_number, source, price_cents, currency)
            VALUES (nextval('price_records_id_seq'), ?, 'shopee', ?, 'MYR')
            """,
            [set_number, price_cents],
        )

    return _seed


class TestFifoCostBasis:
    """Unit tests for FIFO cost basis calculation."""

    def test_single_buy(self):
        txns = [("75192", "new", "BUY", 2, 10000, "2025-01-01")]
        cost, qty = _fifo_cost_basis(txns)
        assert qty == 2
        assert cost == 20000

    def test_buy_then_partial_sell(self):
        txns = [
            ("75192", "new", "BUY", 3, 10000, "2025-01-01"),
            ("75192", "new", "SELL", 1, 15000, "2025-02-01"),
        ]
        cost, qty = _fifo_cost_basis(txns)
        assert qty == 2
        assert cost == 20000  # 2 remaining at 10000 each

    def test_multiple_buys_fifo_order(self):
        txns = [
            ("75192", "new", "BUY", 2, 10000, "2025-01-01"),
            ("75192", "new", "BUY", 2, 20000, "2025-02-01"),
            ("75192", "new", "SELL", 3, 25000, "2025-03-01"),
        ]
        cost, qty = _fifo_cost_basis(txns)
        # FIFO: sell consumes 2 @ 10000 + 1 @ 20000
        # Remaining: 1 @ 20000
        assert qty == 1
        assert cost == 20000

    def test_sell_all(self):
        txns = [
            ("75192", "new", "BUY", 2, 10000, "2025-01-01"),
            ("75192", "new", "SELL", 2, 15000, "2025-02-01"),
        ]
        cost, qty = _fifo_cost_basis(txns)
        assert qty == 0
        assert cost == 0


class TestFifoRealizedPL:
    """Unit tests for FIFO realized P&L calculation."""

    def test_no_sells(self):
        txns = [("75192", "new", "BUY", 2, 10000, "2025-01-01")]
        assert _fifo_realized_pl(txns) == 0

    def test_single_sell_profit(self):
        txns = [
            ("75192", "new", "BUY", 2, 10000, "2025-01-01"),
            ("75192", "new", "SELL", 1, 15000, "2025-02-01"),
        ]
        # Profit: 1 * (15000 - 10000) = 5000
        assert _fifo_realized_pl(txns) == 5000

    def test_single_sell_loss(self):
        txns = [
            ("75192", "new", "BUY", 2, 10000, "2025-01-01"),
            ("75192", "new", "SELL", 1, 8000, "2025-02-01"),
        ]
        assert _fifo_realized_pl(txns) == -2000

    def test_fifo_matching_across_lots(self):
        txns = [
            ("75192", "new", "BUY", 1, 10000, "2025-01-01"),
            ("75192", "new", "BUY", 1, 20000, "2025-02-01"),
            ("75192", "new", "SELL", 2, 18000, "2025-03-01"),
        ]
        # FIFO: sell 1 @ 10000 -> profit 8000, sell 1 @ 20000 -> loss -2000
        # Total: 6000
        assert _fifo_realized_pl(txns) == 6000


class TestCreateTransaction:
    """Tests for transaction creation and validation."""

    def test_create_buy(self, conn, seed_item):
        seed_item()
        from datetime import datetime

        txn_id = create_transaction(
            conn, "75192", "BUY", 2, 30000, "new",
            datetime(2025, 1, 15),
        )
        assert txn_id > 0
        txn = get_transaction(conn, txn_id)
        assert txn is not None
        assert txn["set_number"] == "75192"
        assert txn["txn_type"] == "BUY"
        assert txn["quantity"] == 2
        assert txn["price_cents"] == 30000

    def test_sell_validation_rejects_oversell(self, conn, seed_item):
        seed_item()
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 2, 30000, "new", datetime(2025, 1, 15))

        with pytest.raises(ValueError, match="Cannot sell 3 units"):
            create_transaction(
                conn, "75192", "SELL", 3, 40000, "new", datetime(2025, 2, 15)
            )

    def test_sell_validation_allows_valid_sell(self, conn, seed_item):
        seed_item()
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 2, 30000, "new", datetime(2025, 1, 15))
        txn_id = create_transaction(
            conn, "75192", "SELL", 1, 40000, "new", datetime(2025, 2, 15)
        )
        assert txn_id > 0

    def test_invalid_txn_type(self, conn):
        from datetime import datetime

        with pytest.raises(ValueError, match="Invalid txn_type"):
            create_transaction(conn, "75192", "HOLD", 1, 10000, "new", datetime(2025, 1, 1))

    def test_invalid_quantity(self, conn):
        from datetime import datetime

        with pytest.raises(ValueError, match="Quantity must be positive"):
            create_transaction(conn, "75192", "BUY", 0, 10000, "new", datetime(2025, 1, 1))


class TestListAndDeleteTransactions:
    """Tests for listing and deleting transactions."""

    def test_list_transactions(self, conn, seed_item):
        seed_item()
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 1, 10000, "new", datetime(2025, 1, 1))
        create_transaction(conn, "75192", "BUY", 2, 20000, "new", datetime(2025, 2, 1))

        txns = list_transactions(conn)
        assert len(txns) == 2
        # Ordered by date DESC
        assert txns[0]["quantity"] == 2
        assert txns[1]["quantity"] == 1

    def test_list_filter_by_set(self, conn, seed_item):
        seed_item("75192")
        seed_item("10305", "Lion Knights Castle", 40000)
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 1, 10000, "new", datetime(2025, 1, 1))
        create_transaction(conn, "10305", "BUY", 1, 20000, "new", datetime(2025, 1, 1))

        txns = list_transactions(conn, set_number="10305")
        assert len(txns) == 1
        assert txns[0]["set_number"] == "10305"

    def test_delete_transaction(self, conn, seed_item):
        seed_item()
        from datetime import datetime

        txn_id = create_transaction(conn, "75192", "BUY", 1, 10000, "new", datetime(2025, 1, 1))
        assert delete_transaction(conn, txn_id)
        assert get_transaction(conn, txn_id) is None


class TestHoldings:
    """Tests for holdings derivation and portfolio summary."""

    def test_holdings_with_market_value(self, conn, seed_item):
        seed_item("75192", "Millennium Falcon", 50000)
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 2, 30000, "new", datetime(2025, 1, 1))

        holdings = get_holdings(conn)
        assert len(holdings) == 1
        h = holdings[0]
        assert h["set_number"] == "75192"
        assert h["quantity"] == 2
        assert h["total_cost_cents"] == 60000
        assert h["avg_cost_cents"] == 30000
        assert h["current_value_cents"] == 100000  # 2 * 50000
        assert h["unrealized_pl_cents"] == 40000
        assert h["title"] == "Millennium Falcon"

    def test_holdings_after_partial_sell(self, conn, seed_item):
        seed_item("75192", "Millennium Falcon", 50000)
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 3, 30000, "new", datetime(2025, 1, 1))
        create_transaction(conn, "75192", "SELL", 1, 40000, "new", datetime(2025, 2, 1))

        holdings = get_holdings(conn)
        assert len(holdings) == 1
        assert holdings[0]["quantity"] == 2
        assert holdings[0]["total_cost_cents"] == 60000  # 2 * 30000 remaining via FIFO

    def test_no_holdings_when_fully_sold(self, conn, seed_item):
        seed_item("75192", "Millennium Falcon", 50000)
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 1, 30000, "new", datetime(2025, 1, 1))
        create_transaction(conn, "75192", "SELL", 1, 40000, "new", datetime(2025, 2, 1))

        holdings = get_holdings(conn)
        assert len(holdings) == 0

    def test_portfolio_summary(self, conn, seed_item):
        seed_item("75192", "Millennium Falcon", 50000)
        seed_item("10305", "Lion Knights Castle", 40000)
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 1, 30000, "new", datetime(2025, 1, 1))
        create_transaction(conn, "10305", "BUY", 2, 35000, "new", datetime(2025, 1, 1))

        summary = get_portfolio_summary(conn)
        assert summary["total_cost_cents"] == 100000  # 30000 + 70000
        assert summary["total_market_value_cents"] == 130000  # 50000 + 80000
        assert summary["unrealized_pl_cents"] == 30000
        assert summary["holdings_count"] == 3
        assert summary["unique_sets"] == 2

    def test_holding_detail(self, conn, seed_item):
        seed_item("75192", "Millennium Falcon", 50000)
        from datetime import datetime

        create_transaction(conn, "75192", "BUY", 2, 30000, "new", datetime(2025, 1, 1))
        create_transaction(conn, "75192", "SELL", 1, 45000, "new", datetime(2025, 2, 1))

        detail = get_holding_detail(conn, "75192")
        assert detail is not None
        assert detail["set_number"] == "75192"
        assert len(detail["transactions"]) == 2
        assert len(detail["conditions"]) == 1
        cond = detail["conditions"][0]
        assert cond["condition"] == "new"
        assert cond["quantity"] == 1
        assert cond["realized_pl_cents"] == 15000  # 45000 - 30000
