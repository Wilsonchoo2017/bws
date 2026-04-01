"""Tests for ML target variable computation."""

import pytest

from services.ml.target import (
    _add_months,
    _bricklink_price_at,
    _set_number_to_item_id,
    compute_retirement_returns,
)


class TestAddMonths:
    def test_add_positive(self):
        assert _add_months(2022, 6, 12) == (2023, 6)

    def test_add_across_year(self):
        assert _add_months(2022, 10, 5) == (2023, 3)

    def test_add_zero(self):
        assert _add_months(2022, 1, 0) == (2022, 1)

    def test_add_24(self):
        assert _add_months(2020, 1, 24) == (2022, 1)

    def test_add_to_december(self):
        assert _add_months(2022, 1, 11) == (2022, 12)

    def test_add_from_december(self):
        assert _add_months(2022, 12, 1) == (2023, 1)


class TestSetNumberToItemId:
    def test_plain_number(self):
        assert _set_number_to_item_id("75192") == "75192-1"

    def test_already_has_suffix(self):
        assert _set_number_to_item_id("75192-1") == "75192-1"


class TestBricklinkPriceAt:
    def test_exact_match(self):
        import pandas as pd

        df = pd.DataFrame({
            "item_id": ["75192-1", "75192-1", "75192-1"],
            "year": [2023, 2023, 2023],
            "month": [5, 6, 7],
            "avg_price": [50000, 52000, 54000],
        })
        price = _bricklink_price_at(df, "75192-1", 2023, 6, 1)
        # Should average months 5, 6, 7
        assert price == (50000 + 52000 + 54000) // 3

    def test_no_data(self):
        import pandas as pd

        df = pd.DataFrame({
            "item_id": ["10000-1"],
            "year": [2020],
            "month": [1],
            "avg_price": [1000],
        })
        price = _bricklink_price_at(df, "75192-1", 2023, 6, 1)
        assert price is None

    def test_partial_window(self):
        import pandas as pd

        df = pd.DataFrame({
            "item_id": ["75192-1"],
            "year": [2023],
            "month": [6],
            "avg_price": [52000],
        })
        price = _bricklink_price_at(df, "75192-1", 2023, 6, 1)
        assert price == 52000


class TestComputeRetirementReturns:
    def test_empty_db(self, tmp_path):
        """Should return empty DataFrame when no retired sets exist."""
        import duckdb

        from db.schema import init_schema

        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        init_schema(conn)

        result = compute_retirement_returns(conn)
        assert result.empty
        conn.close()

    def test_with_data(self, tmp_path):
        """Should compute returns when data exists."""
        import duckdb

        from db.schema import init_schema

        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        init_schema(conn)

        # Insert a retired set
        conn.execute("""
            INSERT INTO lego_items (id, set_number, year_retired, retired_date)
            VALUES (1, '75192', 2022, '2022-06')
        """)

        # Insert BrickEconomy snapshot with RRP
        conn.execute("""
            INSERT INTO brickeconomy_snapshots
                (id, set_number, rrp_usd_cents, scraped_at)
            VALUES (1, '75192', 80000, '2022-01-01')
        """)

        # Insert BrickLink monthly sales post-retirement
        for i, (y, m) in enumerate([(2023, 5), (2023, 6), (2023, 7)]):
            conn.execute("""
                INSERT INTO bricklink_monthly_sales
                    (id, item_id, year, month, condition, avg_price, currency)
                VALUES (?, '75192-1', ?, ?, 'N', 120000, 'USD')
            """, [i + 1, y, m])

        result = compute_retirement_returns(conn)
        assert not result.empty
        assert "75192" in result["set_number"].values

        row = result[result["set_number"] == "75192"].iloc[0]
        # 12m horizon: June 2022 + 12 = June 2023, BrickLink has data
        if row["return_12m"] is not None:
            # Return = (120000 / 80000) - 1 = 0.5
            assert row["return_12m"] == pytest.approx(0.5, abs=0.01)
            assert bool(row["profitable_12m"]) is True

        conn.close()
