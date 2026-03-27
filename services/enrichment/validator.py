"""Validation for enrichment data before storage.

Pure functions that validate and sanitize field values from sources.
"""

from services.enrichment.config import (
    is_valid_image_url,
    is_valid_parts_count,
    is_valid_year,
    normalize_string,
)
from services.enrichment.types import MetadataField


def validate_field(
    field: MetadataField,
    value: str | int | bool | None,
) -> str | int | bool | None:
    """Validate and sanitize a field value. Returns None if invalid."""
    if value is None:
        return None

    if field == MetadataField.YEAR_RELEASED:
        return value if isinstance(value, int) and is_valid_year(value) else None

    if field == MetadataField.YEAR_RETIRED:
        return value if isinstance(value, int) and is_valid_year(value) else None

    if field == MetadataField.PARTS_COUNT:
        return (
            value
            if isinstance(value, int) and is_valid_parts_count(value)
            else None
        )

    if field == MetadataField.IMAGE_URL:
        if isinstance(value, str):
            normalized = normalize_string(value)
            return normalized if normalized and is_valid_image_url(normalized) else None
        return None

    if field == MetadataField.TITLE:
        if isinstance(value, str):
            return normalize_string(value)
        return None

    if field == MetadataField.WEIGHT:
        if isinstance(value, str):
            return normalize_string(value)
        return None

    if field == MetadataField.THEME:
        if isinstance(value, str):
            return normalize_string(value)
        return None

    if field == MetadataField.RETIRING_SOON:
        return value if isinstance(value, bool) else None

    return value
