"""Tests for PgConnection SQL translation and compatibility API."""

from unittest.mock import MagicMock, patch

import pytest

from db.pg.pg_connection import PgConnection, PgCursorResult, _duck_to_pg_sql


# ---------------------------------------------------------------------------
# _duck_to_pg_sql translation
# ---------------------------------------------------------------------------


class TestDuckToPgSql:
    """Given legacy-flavoured SQL, when translated, then Postgres-compatible."""

    def test_no_placeholders_unchanged(self) -> None:
        sql = "SELECT * FROM lego_items WHERE set_number = '75192'"
        assert _duck_to_pg_sql(sql) == sql

    def test_question_mark_to_percent_s(self) -> None:
        sql = "SELECT * FROM lego_items WHERE set_number = ? AND theme = ?"
        assert _duck_to_pg_sql(sql) == (
            "SELECT * FROM lego_items WHERE set_number = %s AND theme = %s"
        )

    def test_literal_percent_escaped(self) -> None:
        sql = "SELECT * FROM lego_items WHERE title LIKE '%Star%' AND id = ?"
        result = _duck_to_pg_sql(sql)
        assert "%%Star%%" in result
        assert result.endswith("%s")

    def test_try_cast_replaced_with_cast(self) -> None:
        sql = "SELECT TRY_CAST(LEFT(retired_date, 4) AS INTEGER) FROM t"
        result = _duck_to_pg_sql(sql)
        assert "TRY_CAST" not in result
        assert "CAST(LEFT(retired_date, 4) AS INTEGER)" in result

    def test_try_cast_case_insensitive(self) -> None:
        sql = "SELECT try_cast(x AS INT) FROM t"
        result = _duck_to_pg_sql(sql)
        assert "try_cast" not in result
        assert "CAST(x AS INT)" in result

    def test_try_cast_with_placeholders(self) -> None:
        sql = "SELECT TRY_CAST(col AS INT) FROM t WHERE id = ?"
        result = _duck_to_pg_sql(sql)
        assert "TRY_CAST" not in result
        assert "CAST(col AS INT)" in result
        assert result.endswith("%s")

    def test_multiple_try_casts(self) -> None:
        sql = "SELECT TRY_CAST(a AS INT), TRY_CAST(b AS TEXT) FROM t"
        result = _duck_to_pg_sql(sql)
        assert result.count("CAST(") == 2
        assert "TRY_CAST" not in result


# ---------------------------------------------------------------------------
# PgCursorResult
# ---------------------------------------------------------------------------


class TestPgCursorResult:
    """Given a wrapped psycopg2 cursor, when using compatibility API, then correct results."""

    def test_fetchone_delegates(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (1, "test")
        result = PgCursorResult(cursor)
        assert result.fetchone() == (1, "test")

    def test_fetchall_delegates(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = [(1,), (2,)]
        result = PgCursorResult(cursor)
        assert result.fetchall() == [(1,), (2,)]

    def test_description_delegates(self) -> None:
        cursor = MagicMock()
        cursor.description = [("id",), ("name",)]
        result = PgCursorResult(cursor)
        assert result.description == [("id",), ("name",)]

    def test_df_returns_dataframe(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = [(1, "a"), (2, "b")]
        cursor.description = [("id",), ("name",)]
        result = PgCursorResult(cursor)
        df = result.df()
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 2
        assert df["id"].tolist() == [1, 2]

    def test_df_empty_when_no_description(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.description = None
        result = PgCursorResult(cursor)
        df = result.df()
        assert len(df) == 0


# ---------------------------------------------------------------------------
# PgConnection
# ---------------------------------------------------------------------------


class TestPgConnection:
    """Given a PgConnection wrapping a raw psycopg2 conn, when executing, then correct behaviour."""

    def _make_conn(self) -> tuple[PgConnection, MagicMock]:
        raw = MagicMock()
        cursor = MagicMock()
        raw.cursor.return_value = cursor
        return PgConnection(raw), cursor

    def test_execute_no_params(self) -> None:
        conn, cursor = self._make_conn()
        conn.execute("SELECT 1")
        cursor.execute.assert_called_once_with("SELECT 1")

    def test_execute_with_params_converts_list_to_tuple(self) -> None:
        conn, cursor = self._make_conn()
        conn.execute("SELECT * FROM t WHERE id = ?", [42])
        cursor.execute.assert_called_once_with(
            "SELECT * FROM t WHERE id = %s", (42,)
        )

    def test_execute_translates_try_cast(self) -> None:
        conn, cursor = self._make_conn()
        conn.execute("SELECT TRY_CAST(x AS INT) FROM t")
        cursor.execute.assert_called_once_with("SELECT CAST(x AS INT) FROM t")

    def test_execute_returns_pg_cursor_result(self) -> None:
        conn, _ = self._make_conn()
        result = conn.execute("SELECT 1")
        assert isinstance(result, PgCursorResult)

    def test_execute_logs_and_reraises_on_error(self) -> None:
        conn, cursor = self._make_conn()
        cursor.execute.side_effect = Exception("syntax error")
        with pytest.raises(Exception, match="syntax error"):
            conn.execute("BAD SQL")

    def test_fetchone_none_before_execute(self) -> None:
        raw = MagicMock()
        conn = PgConnection(raw)
        assert conn.fetchone() is None

    def test_fetchall_empty_before_execute(self) -> None:
        raw = MagicMock()
        conn = PgConnection(raw)
        assert conn.fetchall() == []

    def test_description_none_before_execute(self) -> None:
        raw = MagicMock()
        conn = PgConnection(raw)
        assert conn.description is None

    def test_commit_delegates(self) -> None:
        raw = MagicMock()
        conn = PgConnection(raw)
        conn.commit()
        raw.commit.assert_called_once()

    def test_rollback_delegates(self) -> None:
        raw = MagicMock()
        conn = PgConnection(raw)
        conn.rollback()
        raw.rollback.assert_called_once()

    def test_close_delegates(self) -> None:
        raw = MagicMock()
        conn = PgConnection(raw)
        conn.close()
        raw.close.assert_called_once()
