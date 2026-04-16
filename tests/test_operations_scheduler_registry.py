"""Tests for the operations scheduler registry."""

from __future__ import annotations

import asyncio

import pytest

from db.connection import get_connection
from db.schema import init_schema
from services.operations import scheduler_registry as reg


def _run(coro):
    """Drive a coroutine to completion on a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def conn():
    c = get_connection()
    init_schema(c)
    # Clean scheduler_runs so assertions are deterministic
    c.execute("DELETE FROM scheduler_runs WHERE name LIKE '_test_%'")
    return c


def test_record_run_inserts_running_then_ok(conn):
    async def body():
        async with reg.record_run("_test_sched") as run:
            run.items_queued = 7

    _run(body())

    rows = conn.execute(
        "SELECT status, items_queued, finished_at "
        "FROM scheduler_runs WHERE name = ? "
        "ORDER BY started_at DESC LIMIT 1",
        ["_test_sched"],
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "ok"
    assert rows[0][1] == 7
    assert rows[0][2] is not None


def test_record_run_on_exception_marks_error(conn):
    async def body():
        async with reg.record_run("_test_err") as run:
            run.items_queued = 3
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        _run(body())

    row = conn.execute(
        "SELECT status, items_queued, error "
        "FROM scheduler_runs WHERE name = ? "
        "ORDER BY started_at DESC LIMIT 1",
        ["_test_err"],
    ).fetchone()
    assert row[0] == "error"
    assert row[1] == 3
    assert "boom" in row[2]


def test_record_disabled_writes_disabled_row(conn):
    _run(reg.record_disabled("_test_off"))
    row = conn.execute(
        "SELECT status, items_queued "
        "FROM scheduler_runs WHERE name = ? "
        "ORDER BY started_at DESC LIMIT 1",
        ["_test_off"],
    ).fetchone()
    assert row[0] == "disabled"
    assert row[1] == 0


def test_is_enabled_defaults_true():
    # Unknown / unset names should default to enabled so the system
    # works out of the box without needing to seed the settings file.
    assert reg.is_enabled("_test_unknown") is True


def test_set_and_read_enabled_flag():
    reg.set_enabled("enrichment", False)
    assert reg.is_enabled("enrichment") is False
    reg.set_enabled("enrichment", True)
    assert reg.is_enabled("enrichment") is True


def test_set_enabled_rejects_unknown_scheduler():
    with pytest.raises(KeyError):
        reg.set_enabled("_not_registered", True)


def test_load_scheduler_status_returns_every_registered(conn):
    rows = reg.load_scheduler_status(conn)
    names = {r["name"] for r in rows}
    # Every registered spec must appear
    assert names >= {spec.name for spec in reg.SCHEDULERS}
    # Shape check
    for r in rows:
        assert "last_run_at" in r
        assert "enabled" in r
        assert "errors_24h" in r


def test_find_duplicate_enqueues_smoke(conn):
    # Just a smoke test — real data varies.
    result = reg.find_duplicate_enqueues(conn, days=3, min_count=1, limit=5)
    assert isinstance(result, list)
    for row in result:
        assert "set_number" in row
        assert "task_type" in row
        assert row["enqueue_count"] >= 1
