"""Repository functions for enrichment -- find items needing enrichment, store results."""


from services.enrichment.types import (
    EnrichmentResult,
    FieldStatus,
    MetadataField,
)
from services.items.repository import get_or_create_item
from typing import Any


def get_items_needing_enrichment(
    conn: Any,
    limit: int = 50,
) -> list[dict]:
    """Find lego_items rows missing any core data source or metadata.

    An item needs enrichment when ANY of the following is true:
    - Missing metadata fields (title, theme, year_released, etc.)
    - No BrickEconomy snapshot (or missing release_date in snapshot)
    - No Keepa snapshot
    - No BrickLink metadata snapshot
    - No Google Trends snapshot (when title + year_released are known)

    Excludes retiring_soon from the NULL check -- retirement status is
    not actively sought during enrichment.  Items enriched within the
    last 90 days are also skipped.

    Returns items ordered by most recently created first (newest items
    get enriched first).
    """
    result = conn.execute(
        """
        SELECT li.set_number, li.title, li.theme, li.year_released,
               li.year_retired, li.parts_count, li.weight, li.image_url,
               li.retiring_soon, li.release_date, li.retired_date
        FROM lego_items li
        WHERE (
            (li.title IS NULL OR LOWER(TRIM(li.title)) LIKE '%image coming soon%')
            OR li.theme IS NULL
            OR li.year_released IS NULL
            OR li.parts_count IS NULL
            OR li.image_url IS NULL
            OR li.release_date IS NULL
            OR NOT EXISTS (
                SELECT 1 FROM brickeconomy_snapshots bs
                WHERE bs.set_number = li.set_number
            )
            OR NOT EXISTS (
                SELECT 1 FROM brickeconomy_snapshots bs
                WHERE bs.set_number = li.set_number
                  AND bs.release_date IS NOT NULL
            )
            OR NOT EXISTS (
                SELECT 1 FROM keepa_snapshots ks
                WHERE ks.set_number = li.set_number
            )
            OR NOT EXISTS (
                SELECT 1 FROM bricklink_items bl
                WHERE bl.set_number = li.set_number
            )
            OR (
                li.title IS NOT NULL
                AND li.year_released IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM google_trends_snapshots gts
                    WHERE gts.set_number = li.set_number
                )
            )
          )
          AND (li.last_enriched_at IS NULL
               OR li.last_enriched_at < now() - INTERVAL '90 days')
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
        "release_date", "retired_date",
    ]
    return [dict(zip(columns, row)) for row in result]


def store_enrichment_result(
    conn: Any,
    result: EnrichmentResult,
) -> None:
    """Write enrichment results back to lego_items via COALESCE upsert.

    Only writes fields that were successfully found.
    Always stamps last_enriched_at so the 90-day cooldown applies.
    """
    found = {
        r.field: r.value
        for r in result.field_results
        if r.status == FieldStatus.FOUND
    }

    # Always stamp last_enriched_at even when no fields were found,
    # so we don't retry the same item every sweep.
    conn.execute(
        """
        UPDATE lego_items SET last_enriched_at = now()
        WHERE set_number = ?
        """,
        [result.set_number],
    )

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
        minifig_count=found.get(MetadataField.MINIFIG_COUNT),
        dimensions=found.get(MetadataField.DIMENSIONS),
    )
