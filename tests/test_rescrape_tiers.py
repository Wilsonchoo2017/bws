"""GWT tests for tiered BrickLink rescrape strategy.

Tiers:
  1. Portfolio/Watchlist  -> 30-day interval
  2. Retiring soon        -> 60-day interval
  3. General (not retired or retired <= 48 months) -> 150-day interval
  4. Expired (retired > 48 months, not in portfolio/watchlist) -> never
"""

from datetime import datetime, timedelta

import pytest

from db.connection import get_connection
from db.schema import init_schema
from services.items.repository import get_or_create_item
from services.scrape_queue.models import TaskType
from services.scrape_queue.repository import (
    complete_task,
    create_task,
    get_rescrape_candidates,
)


@pytest.fixture
def conn():
    c = get_connection()
    init_schema(c)
    # Clean slate for each test -- rescrape queries scan all items
    c.execute("DELETE FROM scrape_tasks")
    c.execute("DELETE FROM portfolio_transactions")
    c.execute("DELETE FROM lego_items")
    yield c
    c.close()


def _complete_task_at(conn, set_number: str, task_type: TaskType, days_ago: int) -> None:
    """Helper: create and complete a task with completed_at set to N days ago."""
    task = create_task(conn, set_number, task_type)
    if task is None:
        # Force-create by clearing existing
        conn.execute(
            "DELETE FROM scrape_tasks WHERE set_number = ? AND task_type = ?",
            [set_number, task_type.value],
        )
        task = create_task(conn, set_number, task_type)
    assert task is not None
    conn.execute(
        "UPDATE scrape_tasks SET status = 'running', locked_by = 'test' WHERE task_id = ?",
        [task.task_id],
    )
    complete_task(conn, task.task_id)
    completed_at = datetime.now() - timedelta(days=days_ago)
    conn.execute(
        "UPDATE scrape_tasks SET completed_at = ? WHERE task_id = ?",
        [completed_at, task.task_id],
    )


def _retired_date_months_ago(months: int) -> str:
    """Return an ISO month string (YYYY-MM) for N months ago."""
    now = datetime.now()
    year = now.year
    month = now.month - months
    while month <= 0:
        month += 12
        year -= 1
    return f"{year}-{month:02d}"


def _add_portfolio_holding(conn, set_number: str) -> None:
    """Add a BUY transaction so the set is in the portfolio."""
    get_or_create_item(conn, set_number)
    conn.execute(
        """INSERT INTO portfolio_transactions (set_number, txn_type, quantity, price_cents,
           currency, condition, txn_date)
           VALUES (?, 'BUY', 1, 10000, 'MYR', 'new', ?)""",
        [set_number, datetime.now()],
    )


def _set_watchlist(conn, set_number: str) -> None:
    """Flag an item as watchlisted."""
    conn.execute(
        "UPDATE lego_items SET watchlist = TRUE WHERE set_number = ?",
        [set_number],
    )


# ---------------------------------------------------------------------------
# Tier 1: Portfolio / Watchlist -> 30-day interval
# ---------------------------------------------------------------------------


class TestTier1PortfolioWatchlist:
    """Portfolio and watchlist items are scraped every 30 days."""

    def test_given_portfolio_item_scraped_31d_ago_when_candidates_then_included(
        self, conn,
    ):
        """Given a portfolio holding last scraped 31 days ago,
        when getting rescrape candidates,
        then the item is included."""
        get_or_create_item(conn, "75192")
        _add_portfolio_holding(conn, "75192")
        _complete_task_at(conn, "75192", TaskType.BRICKLINK_METADATA, days_ago=31)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75192" in candidates

    def test_given_portfolio_item_scraped_20d_ago_when_candidates_then_excluded(
        self, conn,
    ):
        """Given a portfolio holding last scraped 20 days ago,
        when getting rescrape candidates,
        then the item is NOT included (within 30-day window)."""
        get_or_create_item(conn, "75192")
        _add_portfolio_holding(conn, "75192")
        _complete_task_at(conn, "75192", TaskType.BRICKLINK_METADATA, days_ago=20)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75192" not in candidates

    def test_given_watchlist_item_scraped_35d_ago_when_candidates_then_included(
        self, conn,
    ):
        """Given a watchlisted item last scraped 35 days ago,
        when getting rescrape candidates,
        then the item is included."""
        get_or_create_item(conn, "42151")
        _set_watchlist(conn, "42151")
        _complete_task_at(conn, "42151", TaskType.BRICKLINK_METADATA, days_ago=35)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "42151" in candidates

    def test_given_portfolio_item_retired_50_months_when_candidates_then_included(
        self, conn,
    ):
        """Given a portfolio item retired > 48 months ago (normally expired),
        when getting rescrape candidates,
        then it IS included because portfolio overrides the 48-month cutoff."""
        retired_date = _retired_date_months_ago(50)
        get_or_create_item(conn, "10179", retired_date=retired_date, year_retired=2020)
        _add_portfolio_holding(conn, "10179")
        _complete_task_at(conn, "10179", TaskType.BRICKLINK_METADATA, days_ago=31)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "10179" in candidates

    def test_given_portfolio_item_never_scraped_when_candidates_then_included(
        self, conn,
    ):
        """Given a portfolio item never scraped,
        when getting rescrape candidates,
        then it is included."""
        get_or_create_item(conn, "75192")
        _add_portfolio_holding(conn, "75192")

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75192" in candidates


# ---------------------------------------------------------------------------
# Tier 2: Retiring soon -> 60-day interval
# ---------------------------------------------------------------------------


class TestTier2RetiringSoon:
    """Retiring-soon items are scraped every 60 days."""

    def test_given_retiring_soon_scraped_61d_ago_when_candidates_then_included(
        self, conn,
    ):
        """Given a retiring-soon item last scraped 61 days ago,
        when getting rescrape candidates,
        then the item is included."""
        get_or_create_item(conn, "42151", retiring_soon=True)
        _complete_task_at(conn, "42151", TaskType.BRICKLINK_METADATA, days_ago=61)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "42151" in candidates

    def test_given_retiring_soon_scraped_45d_ago_when_candidates_then_excluded(
        self, conn,
    ):
        """Given a retiring-soon item last scraped 45 days ago,
        when getting rescrape candidates,
        then the item is NOT included (within 60-day window)."""
        get_or_create_item(conn, "42151", retiring_soon=True)
        _complete_task_at(conn, "42151", TaskType.BRICKLINK_METADATA, days_ago=45)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "42151" not in candidates

    def test_given_retiring_soon_never_scraped_when_candidates_then_included(
        self, conn,
    ):
        """Given a retiring-soon item never scraped,
        when getting rescrape candidates,
        then the item is included."""
        get_or_create_item(conn, "42151", retiring_soon=True)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "42151" in candidates


# ---------------------------------------------------------------------------
# Tier 3: General (not retired OR retired <= 48 months) -> 150-day interval
# ---------------------------------------------------------------------------


class TestTier3General:
    """General items scraped every 150 days."""

    def test_given_not_retired_scraped_151d_ago_when_candidates_then_included(
        self, conn,
    ):
        """Given a not-yet-retired item last scraped 151 days ago,
        when getting rescrape candidates,
        then the item is included."""
        get_or_create_item(conn, "75192", year_released=2023)
        _complete_task_at(conn, "75192", TaskType.BRICKLINK_METADATA, days_ago=151)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75192" in candidates

    def test_given_not_retired_scraped_100d_ago_when_candidates_then_excluded(
        self, conn,
    ):
        """Given a not-yet-retired item last scraped 100 days ago,
        when getting rescrape candidates,
        then the item is NOT included (within 150-day window)."""
        get_or_create_item(conn, "75192", year_released=2023)
        _complete_task_at(conn, "75192", TaskType.BRICKLINK_METADATA, days_ago=100)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75192" not in candidates

    def test_given_retired_12_months_scraped_151d_ago_when_candidates_then_included(
        self, conn,
    ):
        """Given an item retired 12 months ago (within 48-month window),
        last scraped 151 days ago,
        when getting rescrape candidates,
        then the item is included."""
        retired_date = _retired_date_months_ago(12)
        get_or_create_item(conn, "75300", retired_date=retired_date)
        _complete_task_at(conn, "75300", TaskType.BRICKLINK_METADATA, days_ago=151)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75300" in candidates

    def test_given_retired_47_months_scraped_151d_ago_when_candidates_then_included(
        self, conn,
    ):
        """Given an item retired 47 months ago (just inside 48-month window),
        last scraped 151 days ago,
        when getting rescrape candidates,
        then the item is included."""
        retired_date = _retired_date_months_ago(47)
        get_or_create_item(conn, "75300", retired_date=retired_date)
        _complete_task_at(conn, "75300", TaskType.BRICKLINK_METADATA, days_ago=151)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75300" in candidates

    def test_given_general_item_never_scraped_when_candidates_then_included(
        self, conn,
    ):
        """Given a general item never scraped,
        when getting rescrape candidates,
        then the item is included."""
        get_or_create_item(conn, "75192", year_released=2023)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75192" in candidates

    def test_given_retired_year_only_within_48_months_when_candidates_then_included(
        self, conn,
    ):
        """Given an item with only year_retired (no retired_date),
        retired within 48 months (using Dec of that year as fallback),
        last scraped 151 days ago,
        when getting rescrape candidates,
        then the item is included."""
        # Use current year - 2 to ensure within 48 months
        get_or_create_item(conn, "75300", year_retired=datetime.now().year - 2)
        _complete_task_at(conn, "75300", TaskType.BRICKLINK_METADATA, days_ago=151)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75300" in candidates


# ---------------------------------------------------------------------------
# Tier 4: Expired (retired > 48 months, not portfolio/watchlist) -> never
# ---------------------------------------------------------------------------


class TestTier4Expired:
    """Items retired > 48 months with no portfolio/watchlist status are never scraped."""

    def test_given_retired_49_months_when_candidates_then_excluded(self, conn):
        """Given an item retired 49 months ago (beyond 48-month cutoff),
        not in portfolio or watchlist,
        when getting rescrape candidates,
        then the item is NOT included."""
        retired_date = _retired_date_months_ago(49)
        get_or_create_item(conn, "10182", retired_date=retired_date)
        _complete_task_at(conn, "10182", TaskType.BRICKLINK_METADATA, days_ago=200)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "10182" not in candidates

    def test_given_retired_60_months_never_scraped_when_candidates_then_excluded(
        self, conn,
    ):
        """Given an item retired 60 months ago, never scraped,
        when getting rescrape candidates,
        then the item is NOT included (expired)."""
        retired_date = _retired_date_months_ago(60)
        get_or_create_item(conn, "10182", retired_date=retired_date)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "10182" not in candidates

    def test_given_retired_year_only_beyond_48_months_when_candidates_then_excluded(
        self, conn,
    ):
        """Given an item with only year_retired, retired > 48 months ago
        (using Dec of that year as fallback),
        when getting rescrape candidates,
        then the item is NOT included."""
        # Use current year - 5 to ensure > 48 months from Dec of that year
        get_or_create_item(conn, "10182", year_retired=datetime.now().year - 5)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "10182" not in candidates

    def test_given_watchlist_retired_50_months_when_candidates_then_included(
        self, conn,
    ):
        """Given a watchlisted item retired > 48 months ago,
        when getting rescrape candidates,
        then it IS included because watchlist overrides the expiry cutoff."""
        retired_date = _retired_date_months_ago(50)
        get_or_create_item(conn, "10182", retired_date=retired_date)
        _set_watchlist(conn, "10182")
        _complete_task_at(conn, "10182", TaskType.BRICKLINK_METADATA, days_ago=31)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "10182" in candidates


# ---------------------------------------------------------------------------
# Tier priority: higher tier wins when item matches multiple tiers
# ---------------------------------------------------------------------------


class TestTierPriority:
    """When an item matches multiple tiers, the shortest interval wins."""

    def test_given_portfolio_and_retiring_soon_when_scraped_31d_ago_then_included(
        self, conn,
    ):
        """Given an item that is both in portfolio AND retiring soon,
        last scraped 31 days ago (stale for tier 1 but fresh for tier 2),
        when getting rescrape candidates,
        then the item IS included (portfolio 30-day interval wins)."""
        get_or_create_item(conn, "75192", retiring_soon=True)
        _add_portfolio_holding(conn, "75192")
        _complete_task_at(conn, "75192", TaskType.BRICKLINK_METADATA, days_ago=31)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75192" in candidates

    def test_given_retiring_soon_and_general_when_scraped_61d_ago_then_included(
        self, conn,
    ):
        """Given an item that is retiring soon (not yet retired),
        last scraped 61 days ago (stale for tier 2 but fresh for tier 3),
        when getting rescrape candidates,
        then the item IS included (retiring-soon 60-day interval wins)."""
        get_or_create_item(conn, "42151", retiring_soon=True)
        _complete_task_at(conn, "42151", TaskType.BRICKLINK_METADATA, days_ago=61)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "42151" in candidates


# ---------------------------------------------------------------------------
# Edge cases: active tasks should block re-enqueue
# ---------------------------------------------------------------------------


class TestActiveTaskBlocking:
    """Items with active (pending/running/blocked) tasks should not be returned."""

    def test_given_stale_item_with_pending_task_when_candidates_then_excluded(
        self, conn,
    ):
        """Given a general item stale for 200 days but with a pending task,
        when getting rescrape candidates,
        then the item is NOT included (already queued)."""
        get_or_create_item(conn, "75192", year_released=2023)
        _complete_task_at(conn, "75192", TaskType.BRICKLINK_METADATA, days_ago=200)
        # Create a new pending task
        create_task(conn, "75192", TaskType.BRICKLINK_METADATA)

        candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        assert "75192" not in candidates


# ---------------------------------------------------------------------------
# Multiple task types
# ---------------------------------------------------------------------------


class TestMultipleTaskTypes:
    """Rescrape candidates are per task_type -- staleness is independent."""

    def test_given_stale_for_bl_fresh_for_be_when_candidates_then_only_bl(
        self, conn,
    ):
        """Given an item stale for BRICKLINK_METADATA (151d) but fresh for
        BRICKECONOMY (20d),
        when getting rescrape candidates for each type,
        then only BRICKLINK_METADATA returns the item."""
        get_or_create_item(conn, "75192", year_released=2023)
        _complete_task_at(conn, "75192", TaskType.BRICKLINK_METADATA, days_ago=151)
        _complete_task_at(conn, "75192", TaskType.BRICKECONOMY, days_ago=20)

        bl_candidates = get_rescrape_candidates(conn, TaskType.BRICKLINK_METADATA)
        be_candidates = get_rescrape_candidates(conn, TaskType.BRICKECONOMY)

        assert "75192" in bl_candidates
        assert "75192" not in be_candidates
