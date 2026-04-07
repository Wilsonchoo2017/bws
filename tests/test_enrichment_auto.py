"""Tests for auto-enrichment dedup and queue helpers."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from api.jobs import JobManager
from db.connection import get_connection
from db.schema import init_schema
from services.enrichment.auto import (
    queue_enrichment_batch,
    queue_enrichment_if_needed,
)


@pytest.fixture
def manager():
    """Fresh JobManager for each test."""
    return JobManager()


@pytest.fixture
def mem_conn():
    """Connection with schema initialised."""
    conn = get_connection()
    init_schema(conn)
    yield conn


class _NoCloseProxy:
    """Wraps a connection but suppresses close()."""

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass  # suppress

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def _patch_db(conn):
    """Patch get_connection/init_schema so auto.py uses our in-memory DB."""
    proxy = _NoCloseProxy(conn)
    with (
        patch("db.connection.get_connection", return_value=proxy),
        patch("db.schema.init_schema"),
    ):
        yield


class TestQueueEnrichmentIfNeeded:
    """Tests for queue_enrichment_if_needed -- single set dedup."""

    def test_queues_new_set(self, manager, mem_conn):
        """Given no pending tasks for set. Then queues and returns True."""
        with _patch_db(mem_conn):
            result = queue_enrichment_if_needed(manager, "75192")
        assert result is True

    def test_skips_already_pending(self, manager, mem_conn):
        """Given already active tasks for set. Then skips and returns False."""
        with _patch_db(mem_conn):
            queue_enrichment_if_needed(manager, "75192")
            result = queue_enrichment_if_needed(manager, "75192")
        assert result is False

    def test_queues_after_all_completed(self, manager, mem_conn):
        """Given previously completed tasks. Then queues new ones."""
        with _patch_db(mem_conn):
            queue_enrichment_if_needed(manager, "75192")
            mem_conn.execute(
                "UPDATE scrape_tasks SET status = 'completed' "
                "WHERE set_number = '75192'"
            )
            result = queue_enrichment_if_needed(manager, "75192")
        assert result is True


class TestQueueEnrichmentBatch:
    """Tests for queue_enrichment_batch -- multiple sets with dedup."""

    def test_queues_all_new(self, manager, mem_conn):
        """Given 3 new set numbers. Then all 3 queued."""
        with _patch_db(mem_conn):
            queued = queue_enrichment_batch(manager, ["75192", "42151", "31009"])
        assert queued == 3

    def test_deduplicates_against_pending(self, manager, mem_conn):
        """Given '75192' already pending. Then only queues the other 2."""
        with _patch_db(mem_conn):
            queue_enrichment_if_needed(manager, "75192")
            queued = queue_enrichment_batch(manager, ["75192", "42151", "31009"])
        assert queued == 2

    def test_deduplicates_within_batch(self, manager, mem_conn):
        """Given duplicate set numbers in batch. Then only queues unique."""
        with _patch_db(mem_conn):
            queued = queue_enrichment_batch(
                manager, ["75192", "42151", "75192", "42151"]
            )
        assert queued == 2

    def test_empty_batch(self, manager, mem_conn):
        """Given empty list. Then queues 0."""
        with _patch_db(mem_conn):
            queued = queue_enrichment_batch(manager, [])
        assert queued == 0
