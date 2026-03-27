"""Adapters that extract metadata fields from each source's scrape result.

Pure functions mapping source-specific data models to the unified MetadataField dict.
"""

from bws_types.models import BricklinkData
from services.brickranker.parser import RetirementItem
from services.enrichment.types import MetadataField, SourceId, SourceResult
from services.worldbricks.parser import WorldBricksData


def adapt_bricklink(data: BricklinkData) -> SourceResult:
    """Extract enrichment fields from BricklinkData."""
    fields: dict[MetadataField, str | int | bool | None] = {
        MetadataField.TITLE: data.title,
        MetadataField.YEAR_RELEASED: data.year_released,
        MetadataField.IMAGE_URL: data.image_url,
        MetadataField.WEIGHT: data.weight,
    }
    return SourceResult(
        source=SourceId.BRICKLINK,
        success=True,
        fields=fields,
    )


def adapt_worldbricks(data: WorldBricksData) -> SourceResult:
    """Extract enrichment fields from WorldBricksData."""
    fields: dict[MetadataField, str | int | bool | None] = {
        MetadataField.TITLE: data.set_name,
        MetadataField.YEAR_RELEASED: data.year_released,
        MetadataField.YEAR_RETIRED: data.year_retired,
        MetadataField.PARTS_COUNT: data.parts_count,
        MetadataField.IMAGE_URL: data.image_url,
    }
    return SourceResult(
        source=SourceId.WORLDBRICKS,
        success=True,
        fields=fields,
    )


def adapt_brickranker(item: RetirementItem) -> SourceResult:
    """Extract enrichment fields from RetirementItem."""
    fields: dict[MetadataField, str | int | bool | None] = {
        MetadataField.THEME: item.theme,
        MetadataField.RETIRING_SOON: item.retiring_soon,
    }
    return SourceResult(
        source=SourceId.BRICKRANKER,
        success=True,
        fields=fields,
    )


def make_failed_result(source_id: SourceId, error: str) -> SourceResult:
    """Create a failed SourceResult."""
    return SourceResult(
        source=source_id,
        success=False,
        fields={},
        error=error,
    )
