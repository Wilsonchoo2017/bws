"""Integration tests for the backtesting engine.

Uses a small in-memory DuckDB with known data to verify the engine
produces correct trades with no look-ahead bias.
"""

import duckdb
import pytest

from services.backtesting.analysis import trades_to_dataframe
from services.backtesting.engine import run_backtest
from services.backtesting.types import BacktestConfig


@pytest.fixture()
def backtest_db() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with known test data."""
    conn = duckdb.connect(":memory:")

    conn.execute("""
        CREATE TABLE bricklink_monthly_sales (
            id INTEGER PRIMARY KEY,
            item_id VARCHAR NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            condition VARCHAR NOT NULL,
            times_sold INTEGER,
            total_quantity INTEGER,
            min_price INTEGER,
            avg_price INTEGER,
            max_price INTEGER,
            currency VARCHAR DEFAULT 'USD',
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(item_id, year, month, condition)
        )
    """)

    conn.execute("""
        CREATE TABLE bricklink_items (
            id INTEGER PRIMARY KEY,
            item_id VARCHAR NOT NULL UNIQUE,
            item_type VARCHAR DEFAULT 'S',
            title VARCHAR,
            weight FLOAT,
            year_released INTEGER,
            image_url VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE lego_items (
            id INTEGER PRIMARY KEY,
            set_number VARCHAR NOT NULL UNIQUE,
            title VARCHAR,
            theme VARCHAR,
            year_released INTEGER,
            year_retired INTEGER,
            parts_count INTEGER,
            rrp_cents INTEGER,
            rrp_currency VARCHAR,
            retiring_soon BOOLEAN DEFAULT FALSE
        )
    """)

    conn.execute("""
        CREATE TABLE bricklink_price_history (
            id INTEGER PRIMARY KEY,
            item_id VARCHAR NOT NULL,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            six_month_new VARCHAR,
            six_month_used VARCHAR,
            current_new VARCHAR,
            current_used VARCHAR
        )
    """)

    # Insert a well-known item with 8 months of rising prices
    # Set 75192 (Millennium Falcon): $500 -> $800 over 8 months
    prices = [50000, 52000, 55000, 58000, 62000, 67000, 73000, 80000]
    for i, price in enumerate(prices):
        month_idx = i + 1
        conn.execute(
            """INSERT INTO bricklink_monthly_sales
               (id, item_id, year, month, condition, times_sold, total_quantity,
                min_price, avg_price, max_price, currency)
               VALUES (?, '75192-1', 2025, ?, 'new', ?, ?, ?, ?, ?, 'USD')""",
            [
                i + 1,
                month_idx,
                15 + i,        # rising sales
                20 + i * 2,    # rising quantity
                int(price * 0.85),
                price,
                int(price * 1.15),
            ],
        )

    # Insert a second item with 6 months of declining prices
    prices2 = [30000, 28000, 25000, 22000, 20000, 18000]
    for i, price in enumerate(prices2):
        conn.execute(
            """INSERT INTO bricklink_monthly_sales
               (id, item_id, year, month, condition, times_sold, total_quantity,
                min_price, avg_price, max_price, currency)
               VALUES (?, '10280-1', 2025, ?, 'new', ?, ?, ?, ?, ?, 'USD')""",
            [
                100 + i + 1,
                i + 1,
                5,
                5,
                int(price * 0.9),
                price,
                int(price * 1.1),
            ],
        )

    # Insert metadata
    conn.execute("""
        INSERT INTO bricklink_items (id, item_id, title, year_released)
        VALUES (1, '75192-1', 'Millennium Falcon', 2017),
               (2, '10280-1', 'Flower Bouquet', 2021)
    """)

    conn.execute("""
        INSERT INTO lego_items (id, set_number, title, theme, year_released, year_retired, rrp_cents, rrp_currency)
        VALUES (1, '75192', 'Millennium Falcon', 'Star Wars', 2017, 2023, 84999, 'USD'),
               (2, '10280', 'Flower Bouquet', 'Icons', 2021, 2024, 5999, 'USD')
    """)

    return conn


class TestEngineIntegration:
    def test_generates_trades(self, backtest_db: duckdb.DuckDBPyConnection) -> None:
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)
        assert len(trades) > 0

    def test_correct_item_count(self, backtest_db: duckdb.DuckDBPyConnection) -> None:
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)
        item_ids = {t.item_id for t in trades}
        assert "75192-1" in item_ids
        assert "10280-1" in item_ids

    def test_entry_price_is_positive(self, backtest_db: duckdb.DuckDBPyConnection) -> None:
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)
        for trade in trades:
            assert trade.entry_price_cents > 0

    def test_flip_returns_available(self, backtest_db: duckdb.DuckDBPyConnection) -> None:
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)
        has_flip = any(
            t.returns.get("flip_1m") is not None
            for t in trades
        )
        assert has_flip

    def test_no_hold_returns_with_short_data(
        self, backtest_db: duckdb.DuckDBPyConnection
    ) -> None:
        """With only 8 months of data, hold_12m should always be None."""
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)
        for trade in trades:
            assert trade.returns.get("hold_12m") is None

    def test_signals_populated(self, backtest_db: duckdb.DuckDBPyConnection) -> None:
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)
        for trade in trades:
            # At least demand_pressure should be computed
            assert trade.signals.demand_pressure is not None


class TestNoLookAheadBias:
    """Verify that signals only use data available at evaluation time."""

    def test_early_trade_ignores_later_prices(
        self, backtest_db: duckdb.DuckDBPyConnection
    ) -> None:
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)

        # Find the earliest trade for 75192-1
        item_trades = [t for t in trades if t.item_id == "75192-1"]
        item_trades.sort(key=lambda t: (t.entry_year, t.entry_month))
        earliest = item_trades[0]

        # The earliest trade should be at month 4 (after 3 months min history)
        assert earliest.entry_month == 4
        # Entry price should be month 4's avg_price (58000)
        assert earliest.entry_price_cents == 58000

    def test_returns_use_future_prices(
        self, backtest_db: duckdb.DuckDBPyConnection
    ) -> None:
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)

        # 75192-1 month 4 -> month 5 return
        item_trades = [t for t in trades if t.item_id == "75192-1"]
        item_trades.sort(key=lambda t: (t.entry_year, t.entry_month))
        earliest = item_trades[0]

        flip_1m = earliest.returns.get("flip_1m")
        assert flip_1m is not None
        # Expected: (62000 - 58000) / 58000 = 0.06896...
        assert abs(flip_1m - (62000 - 58000) / 58000) < 0.001


class TestTradesToDataframe:
    def test_converts_to_dataframe(
        self, backtest_db: duckdb.DuckDBPyConnection
    ) -> None:
        config = BacktestConfig(min_history_months=3)
        trades = run_backtest(backtest_db, config)
        df = trades_to_dataframe(trades)

        assert len(df) == len(trades)
        assert "item_id" in df.columns
        assert "demand_pressure" in df.columns
        assert "return_flip_1m" in df.columns
