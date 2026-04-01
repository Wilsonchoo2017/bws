"""DuckDB persistence for Google Trends snapshots."""

import json
import logging
from typing import TYPE_CHECKING

from services.google_trends.types import TrendsData, TrendsDataPoint

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.google_trends.repository")


def _interest_to_json(points: tuple[TrendsDataPoint, ...]) -> str:
    """Serialize interest data points to JSON array of [date, value]."""
    return json.dumps([[p.date, p.value] for p in points])


def save_trends_snapshot(
    conn: "DuckDBPyConnection", data: TrendsData
) -> int:
    """Insert a Google Trends snapshot row and return the new row ID."""
    row_id = conn.execute(
        "SELECT nextval('google_trends_snapshots_id_seq')"
    ).fetchone()[0]

    conn.execute(
        """
        INSERT INTO google_trends_snapshots (
            id, set_number, keyword, search_property, geo,
            timeframe_start, timeframe_end,
            interest_json, peak_value, peak_date,
            average_value, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row_id,
            data.set_number,
            data.keyword,
            data.search_property,
            data.geo,
            data.timeframe_start,
            data.timeframe_end,
            _interest_to_json(data.interest_over_time),
            data.peak_value,
            data.peak_date,
            data.average_value,
            data.scraped_at,
        ],
    )

    logger.info(
        "Saved Google Trends snapshot id=%d for %s (%d points)",
        row_id,
        data.set_number,
        len(data.interest_over_time),
    )
    return row_id


def get_latest_trends_snapshot(
    conn: "DuckDBPyConnection", set_number: str
) -> dict | None:
    """Get the most recent Google Trends snapshot for a set."""
    row = conn.execute(
        """
        SELECT * FROM google_trends_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        [set_number],
    ).fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in conn.description]
    return dict(zip(columns, row))
