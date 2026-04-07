"""Persistence for Google Trends snapshots."""

import json
import logging

from db.pg.writes import _get_pg, pg_insert_gtrends_snapshot
from services.google_trends.types import TrendsData, TrendsDataPoint
from typing import Any


logger = logging.getLogger("bws.google_trends.repository")


def _interest_to_json(points: tuple[TrendsDataPoint, ...]) -> str:
    """Serialize interest data points to JSON array of [date, value]."""
    from db.serialization import datapoints_to_json

    return datapoints_to_json(points)


def save_trends_snapshot(
    conn: Any, data: TrendsData
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

    # Write to Postgres
    pg = _get_pg(conn)
    if pg is not None:
        pg_insert_gtrends_snapshot(
            pg,
            set_number=data.set_number,
            keyword=data.keyword,
            search_property=data.search_property,
            geo=data.geo,
            timeframe_start=data.timeframe_start,
            timeframe_end=data.timeframe_end,
            interest_json=_interest_to_json(data.interest_over_time),
            peak_value=data.peak_value,
            peak_date=data.peak_date,
            average_value=data.average_value,
            scraped_at=data.scraped_at,
        )

    logger.info(
        "Saved Google Trends snapshot id=%d for %s (%d points)",
        row_id,
        data.set_number,
        len(data.interest_over_time),
    )
    return row_id


def get_latest_trends_snapshot(
    conn: Any, set_number: str
) -> dict | None:
    """Get the most recent Google Trends snapshot for a set."""
    from db.queries import get_latest_row

    return get_latest_row(conn, "google_trends_snapshots", key_value=set_number)
