"""Google Trends theme-level executor.

Fetches YouTube interest for theme names (e.g. "LEGO Minecraft" + "Minecraft")
rather than individual set numbers. Computes lego_share ratio.

Uses the same cooldown tracker as the set-level GT executor since both
hit the same Google Trends API.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from config.ml import LICENSED_THEMES
from services.scrape_queue.executors.google_trends import (
    _trends_cooldown,
    get_trends_cooldown_remaining,
)
from services.scrape_queue.models import ExecutorResult, TaskType
from services.scrape_queue.registry import executor
from typing import Any


logger = logging.getLogger("bws.scrape_queue.executor.google_trends_theme")

# Themes where the bare name is a real, searchable term on YouTube.
NAMED_IP_THEMES: frozenset[str] = LICENSED_THEMES | frozenset({
    "Ninjago",
    "Friends",
    "Duplo",
    "Bionicle",
    "Nexo Knights",
    "Chima",
    "Elves",
    "Monkie Kid",
    "Hidden Side",
    "Dreamzzz",
})


def _classify_theme(theme: str) -> str:
    return "named_ip" if theme in NAMED_IP_THEMES else "generic"


def _check_freshness(
    conn: Any, theme: str,
) -> bool:
    """Return True if we need fresh data."""
    from datetime import timedelta

    from db.queries import is_fresh

    row = conn.execute(
        """SELECT scraped_at FROM google_trends_theme_snapshots
           WHERE theme = ?
           ORDER BY scraped_at DESC LIMIT 1""",
        [theme],
    ).fetchone()
    if row and row[0]:
        if is_fresh(row[0], timedelta(days=30)):
            return False
    return True


def _fetch_theme_gt(
    theme: str, theme_type: str, timeframe: str,
) -> dict | None:
    """Fetch YouTube GT data for a theme. Returns summary dict or None."""
    from trendspy import Trends

    keyword_lego = f"LEGO {theme}"
    keywords = [keyword_lego, theme] if theme_type == "named_ip" else [keyword_lego]

    tr = Trends(request_delay=60.0)
    df = tr.interest_over_time(
        keywords=keywords,
        gprop="youtube",
        geo="",
        timeframe=timeframe,
    )

    if df.empty:
        return {
            "keyword_lego": keyword_lego,
            "keyword_bare": theme if theme_type == "named_ip" else "",
            "interest_lego_json": "[]",
            "interest_bare_json": "[]",
            "avg_lego": 0.0,
            "avg_bare": 0.0,
            "peak_lego": 0,
            "peak_bare": 0,
            "lego_share": None,
            "n_weeks": 0,
        }

    # Extract LEGO keyword series
    lego_points = [
        [ts.strftime("%Y-%m-%d"), int(row[keyword_lego])]
        for ts, row in df.iterrows()
    ]
    avg_lego = round(float(df[keyword_lego].mean()), 2)
    peak_lego = int(df[keyword_lego].max())
    n_weeks = len(df)

    # Extract bare keyword series (named IPs only)
    if theme_type == "named_ip" and theme in df.columns:
        bare_points = [
            [ts.strftime("%Y-%m-%d"), int(row[theme])]
            for ts, row in df.iterrows()
        ]
        avg_bare = round(float(df[theme].mean()), 2)
        peak_bare = int(df[theme].max())
        total = avg_lego + avg_bare
        lego_share = round(avg_lego / total, 4) if total > 0 else None
    else:
        bare_points = []
        avg_bare = 0.0
        peak_bare = 0
        lego_share = None

    return {
        "keyword_lego": keyword_lego,
        "keyword_bare": theme if theme_type == "named_ip" else "",
        "interest_lego_json": json.dumps(lego_points),
        "interest_bare_json": json.dumps(bare_points),
        "avg_lego": avg_lego,
        "avg_bare": avg_bare,
        "peak_lego": peak_lego,
        "peak_bare": peak_bare,
        "lego_share": lego_share,
        "n_weeks": n_weeks,
    }


def _persist(conn: Any, theme: str, theme_type: str, data: dict) -> None:
    """Save theme GT snapshot to the database."""
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    row_id = conn.execute(
        "SELECT nextval('google_trends_theme_snapshots_id_seq')"
    ).fetchone()[0]

    conn.execute(
        """
        INSERT INTO google_trends_theme_snapshots (
            id, theme, theme_type, keyword_lego, keyword_bare,
            search_property, geo, timeframe_start, timeframe_end,
            interest_lego_json, interest_bare_json,
            avg_lego, avg_bare, peak_lego, peak_bare,
            lego_share, n_weeks, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row_id,
            theme,
            theme_type,
            data["keyword_lego"],
            data["keyword_bare"],
            "youtube",
            "",
            "2018-01-01",
            today,
            data["interest_lego_json"],
            data["interest_bare_json"],
            data["avg_lego"],
            data["avg_bare"],
            data["peak_lego"],
            data["peak_bare"],
            data["lego_share"],
            data["n_weeks"],
            datetime.now(tz=timezone.utc),
        ],
    )
    logger.info(
        "Saved theme GT snapshot id=%d for %s (n_weeks=%d, lego_share=%s)",
        row_id, theme, data["n_weeks"], data["lego_share"],
    )


@executor(
    TaskType.GOOGLE_TRENDS_THEME,
    concurrency=1,
    timeout=180,
    cooldown_check=get_trends_cooldown_remaining,
)
def execute_google_trends_theme(
    conn: Any,
    set_number: str,
    *,
    worker_index: int = 0,
) -> ExecutorResult:
    """Fetch theme-level YouTube GT data.

    The set_number field is repurposed as the theme name for this task type.
    """
    theme = set_number  # set_number stores the theme name for this task type
    theme_type = _classify_theme(theme)
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    timeframe = f"2018-01-01 {today}"

    # Shared cooldown with set-level GT
    remaining = _trends_cooldown.remaining()
    if remaining > 0:
        return ExecutorResult.cooldown(remaining)

    # Freshness check
    if not _check_freshness(conn, theme):
        return ExecutorResult.ok()

    # Fetch
    try:
        data = _fetch_theme_gt(theme, theme_type, timeframe)
    except Exception as exc:
        error_str = str(exc)
        if "429" in error_str or "Too Many" in error_str:
            _trends_cooldown.activate()
            return ExecutorResult.cooldown(_trends_cooldown.DURATION_SECONDS)
        return ExecutorResult.fail(f"GT theme fetch failed: {error_str}")

    if data is None:
        return ExecutorResult.fail("No data returned from Google Trends")

    # Persist
    _persist(conn, theme, theme_type, data)

    logger.info(
        "Theme GT for %s: %d weeks, lego_share=%s",
        theme, data["n_weeks"], data["lego_share"],
    )
    return ExecutorResult.ok()
