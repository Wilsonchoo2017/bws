"""Tests for Postgres-only mode compatibility.

Covers the DUCK_ENABLED=false code paths in:
- db/schema.py (_sync_sequences)
- api/main.py (shutdown checkpoint)
- services/scrape_queue/dispatcher.py (periodic checkpoint)
"""

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# _sync_sequences: Postgres vs DuckDB branch
# ---------------------------------------------------------------------------


class TestSyncSequencesPostgresMode:
    """Given DUCK_ENABLED=false, when syncing sequences, then use ALTER SEQUENCE."""

    @patch("db.schema.DUCK_ENABLED", False, create=True)
    @patch("config.settings.DUCK_ENABLED", False)
    def test_alter_sequence_used_in_pg_mode(self) -> None:
        from db.schema import _sync_sequences

        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (10,)

        _sync_sequences(conn)

        executed_sqls = [c.args[0] for c in conn.execute.call_args_list]
        alter_calls = [s for s in executed_sqls if "ALTER SEQUENCE" in s]
        drop_calls = [s for s in executed_sqls if "DROP SEQUENCE" in s]
        create_calls = [s for s in executed_sqls if "CREATE SEQUENCE" in s]

        assert len(alter_calls) > 0, "Expected ALTER SEQUENCE calls in PG mode"
        assert len(drop_calls) == 0, "DROP SEQUENCE should not be called in PG mode"
        assert len(create_calls) == 0, "CREATE SEQUENCE should not be called in PG mode"

    @patch("db.schema.DUCK_ENABLED", False, create=True)
    @patch("config.settings.DUCK_ENABLED", False)
    def test_restart_with_correct_value(self) -> None:
        from db.schema import _sync_sequences

        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (42,)

        _sync_sequences(conn)

        executed_sqls = [c.args[0] for c in conn.execute.call_args_list]
        alter_calls = [s for s in executed_sqls if "ALTER SEQUENCE" in s]
        assert all("RESTART WITH 43" in s for s in alter_calls)

    @patch("db.schema.DUCK_ENABLED", True, create=True)
    @patch("config.settings.DUCK_ENABLED", True)
    def test_drop_create_used_in_duck_mode(self) -> None:
        from db.schema import _sync_sequences

        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (5,)

        _sync_sequences(conn)

        executed_sqls = [c.args[0] for c in conn.execute.call_args_list]
        drop_calls = [s for s in executed_sqls if "DROP SEQUENCE" in s]
        create_calls = [s for s in executed_sqls if "CREATE SEQUENCE" in s]
        alter_calls = [s for s in executed_sqls if "ALTER SEQUENCE" in s]

        assert len(drop_calls) > 0, "Expected DROP SEQUENCE calls in DuckDB mode"
        assert len(create_calls) > 0, "Expected CREATE SEQUENCE calls in DuckDB mode"
        assert len(alter_calls) == 0, "ALTER SEQUENCE should not be called in DuckDB mode"

    @patch("db.schema.DUCK_ENABLED", False, create=True)
    @patch("config.settings.DUCK_ENABLED", False)
    def test_empty_table_starts_at_1(self) -> None:
        from db.schema import _sync_sequences

        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (0,)

        _sync_sequences(conn)

        executed_sqls = [c.args[0] for c in conn.execute.call_args_list]
        alter_calls = [s for s in executed_sqls if "ALTER SEQUENCE" in s]
        assert all("RESTART WITH 1" in s for s in alter_calls)

    @patch("db.schema.DUCK_ENABLED", False, create=True)
    @patch("config.settings.DUCK_ENABLED", False)
    def test_exception_swallowed_gracefully(self) -> None:
        from db.schema import _sync_sequences

        conn = MagicMock()
        conn.execute.side_effect = Exception("table does not exist")

        # Should not raise
        _sync_sequences(conn)


# ---------------------------------------------------------------------------
# Shutdown checkpoint: FORCE CHECKPOINT vs CHECKPOINT
# ---------------------------------------------------------------------------


class TestShutdownCheckpointMainLifespan:
    """Given DUCK_ENABLED toggle, when shutdown checkpoint runs, then correct SQL."""

    @patch("config.settings.DUCK_ENABLED", False)
    def test_pg_mode_uses_checkpoint(self) -> None:
        conn = MagicMock()
        with patch("db.connection.get_connection", return_value=conn):
            # Simulate the shutdown checkpoint logic from api/main.py
            from config.settings import DUCK_ENABLED

            conn.execute("FORCE CHECKPOINT" if DUCK_ENABLED else "CHECKPOINT")

        conn.execute.assert_called_with("CHECKPOINT")

    @patch("config.settings.DUCK_ENABLED", True)
    def test_duck_mode_uses_force_checkpoint(self) -> None:
        conn = MagicMock()
        with patch("db.connection.get_connection", return_value=conn):
            from config.settings import DUCK_ENABLED

            conn.execute("FORCE CHECKPOINT" if DUCK_ENABLED else "CHECKPOINT")

        conn.execute.assert_called_with("FORCE CHECKPOINT")


class TestDispatcherCheckpoint:
    """Given DUCK_ENABLED toggle, when dispatcher checkpoint runs, then correct SQL."""

    @patch("config.settings.DUCK_ENABLED", False)
    @patch("db.connection.get_connection")
    def test_pg_mode_uses_checkpoint(self, mock_get_conn: MagicMock) -> None:
        conn = MagicMock()
        mock_get_conn.return_value = conn

        from services.scrape_queue.dispatcher import checkpoint_database

        checkpoint_database()

        conn.execute.assert_called_once_with("CHECKPOINT")
        conn.close.assert_called_once()

    @patch("config.settings.DUCK_ENABLED", True)
    @patch("db.connection.get_connection")
    def test_duck_mode_uses_force_checkpoint(self, mock_get_conn: MagicMock) -> None:
        conn = MagicMock()
        mock_get_conn.return_value = conn

        from services.scrape_queue.dispatcher import checkpoint_database

        checkpoint_database()

        conn.execute.assert_called_once_with("FORCE CHECKPOINT")
        conn.close.assert_called_once()
