"""Adapters that extract metadata fields from each source's scrape result.

Pure functions mapping source-specific data models to the unified MetadataField dict.
"""

from bws_types.models import BricklinkData
from services.brickeconomy.parser import BrickeconomySnapshot
from services.enrichment.types import MetadataField, SourceId, SourceResult


def adapt_bricklink(data: BricklinkData) -> SourceResult:
    """Extract enrichment fields from BricklinkData."""
    image_url = data.image_url
    # Fallback: construct BrickLink image URL from item_id if scraper missed it
    if image_url is None and data.item_id:
        image_url = f"https://img.bricklink.com/ItemImage/SN/0/{data.item_id}.png"

    fields: dict[MetadataField, str | int | bool | None] = {
        MetadataField.TITLE: data.title,
        MetadataField.YEAR_RELEASED: data.year_released,
        MetadataField.IMAGE_URL: image_url,
        MetadataField.WEIGHT: data.weight,
        MetadataField.PARTS_COUNT: data.parts_count,
        MetadataField.THEME: data.theme,
        MetadataField.MINIFIG_COUNT: data.minifig_count,
        MetadataField.DIMENSIONS: data.dimensions,
    }
    return SourceResult(
        source=SourceId.BRICKLINK,
        success=True,
        fields=fields,
    )


def adapt_brickeconomy(snapshot: BrickeconomySnapshot) -> SourceResult:
    """Extract enrichment fields from BrickeconomySnapshot."""
    fields: dict[MetadataField, str | int | bool | None] = {
        MetadataField.TITLE: snapshot.title,
        MetadataField.YEAR_RELEASED: snapshot.year_released,
        MetadataField.YEAR_RETIRED: snapshot.year_retired,
        MetadataField.PARTS_COUNT: snapshot.pieces,
        MetadataField.THEME: snapshot.theme,
        MetadataField.IMAGE_URL: snapshot.image_url,
        MetadataField.MINIFIG_COUNT: snapshot.minifigs,
        MetadataField.RETIRING_SOON: snapshot.retiring_soon,
        MetadataField.RELEASE_DATE: snapshot.release_date,
        MetadataField.RETIRED_DATE: snapshot.retired_date,
    }
    return SourceResult(
        source=SourceId.BRICKECONOMY,
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
