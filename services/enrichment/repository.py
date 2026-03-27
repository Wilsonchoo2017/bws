"""Repository functions for enrichment -- find items needing enrichment, store results."""

from typing import TYPE_CHECKING

from services.enrichment.types import (
    EnrichmentResult,
    FieldStatus,
    MetadataField,
)
from services.items.repository import get_or_create_item

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def get_items_needing_enrichment(
    conn: "DuckDBPyConnection",
    limit: int = 50,
) -> list[dict]:
    """Find lego_items rows with any NULL metadata fields.

    Returns items ordered by most recently created first (newest items
    get enriched first).
    """
    result = conn.execute(
        """
        SELECT set_number, title, theme, year_released, year_retired,
               parts_count, weight, image_url
        FROM lego_items
        WHERE title IS NULL
           OR theme IS NULL
           OR year_released IS NULL
           OR parts_count IS NULL
           OR image_url IS NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    columns = [
        "set_number", "title", "theme", "year_released", "year_retired",
        "parts_count", "weight", "image_url",
    ]
    return [dict(zip(columns, row)) for row in result]


def store_enrichment_result(
    conn: "DuckDBPyConnection",
    result: EnrichmentResult,
) -> None:
    """Write enrichment results back to lego_items via COALESCE upsert.

    Only writes fields that were successfully found.
    """
    found = {
        r.field: r.value
        for r in result.field_results
        if r.status == FieldStatus.FOUND
    }

    if not found:
        return

    get_or_create_item(
        conn,
        result.set_number,
        title=found.get(MetadataField.TITLE),
        theme=found.get(MetadataField.THEME),
        year_released=found.get(MetadataField.YEAR_RELEASED),
        year_retired=found.get(MetadataField.YEAR_RETIRED),
        parts_count=found.get(MetadataField.PARTS_COUNT),
        weight=found.get(MetadataField.WEIGHT),
        image_url=found.get(MetadataField.IMAGE_URL),
    )
