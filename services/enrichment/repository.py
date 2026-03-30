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
        SELECT li.set_number, li.title, li.theme, li.year_released,
               li.year_retired, li.parts_count, li.weight, li.image_url,
               li.retiring_soon
        FROM lego_items li
        WHERE (li.title IS NULL
           OR li.theme IS NULL
           OR li.year_released IS NULL
           OR li.parts_count IS NULL
           OR li.image_url IS NULL)
          AND EXISTS (
              SELECT 1 FROM price_records pr
              WHERE pr.set_number = li.set_number
                AND pr.source IN ('toysrus', 'shopee')
          )
        ORDER BY li.created_at DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()

    columns = [
        "set_number", "title", "theme", "year_released", "year_retired",
        "parts_count", "weight", "image_url", "retiring_soon",
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
        retiring_soon=found.get(MetadataField.RETIRING_SOON),
    )
