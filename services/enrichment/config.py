"""Configuration for the metadata enrichment system.

Defines which sources provide which fields, priority ordering,
validation rules, and freshness windows.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from services.enrichment.types import MetadataField, SourceId


@dataclass(frozen=True)
class SourceConfig:
    """Configuration for a single metadata source."""

    source_id: SourceId
    fields_provided: frozenset[MetadataField]
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown_seconds: int = 1800  # 30 minutes
    freshness_window_seconds: int = 86400  # 24 hours


# Which sources provide which fields, in priority order per field.
FIELD_SOURCE_PRIORITY: dict[MetadataField, tuple[SourceId, ...]] = {
    MetadataField.TITLE: (SourceId.BRICKLINK, SourceId.WORLDBRICKS),
    MetadataField.YEAR_RELEASED: (SourceId.BRICKLINK, SourceId.WORLDBRICKS),
    MetadataField.YEAR_RETIRED: (SourceId.WORLDBRICKS,),
    MetadataField.PARTS_COUNT: (SourceId.WORLDBRICKS,),
    MetadataField.THEME: (SourceId.BRICKRANKER,),
    MetadataField.IMAGE_URL: (SourceId.BRICKLINK, SourceId.WORLDBRICKS),
    MetadataField.WEIGHT: (SourceId.BRICKLINK,),
    MetadataField.RETIRING_SOON: (SourceId.BRICKRANKER,),
}

SOURCE_CONFIGS: dict[SourceId, SourceConfig] = {
    SourceId.BRICKLINK: SourceConfig(
        source_id=SourceId.BRICKLINK,
        fields_provided=frozenset({
            MetadataField.TITLE,
            MetadataField.YEAR_RELEASED,
            MetadataField.IMAGE_URL,
            MetadataField.WEIGHT,
        }),
    ),
    SourceId.WORLDBRICKS: SourceConfig(
        source_id=SourceId.WORLDBRICKS,
        fields_provided=frozenset({
            MetadataField.TITLE,
            MetadataField.YEAR_RELEASED,
            MetadataField.YEAR_RETIRED,
            MetadataField.PARTS_COUNT,
            MetadataField.IMAGE_URL,
        }),
    ),
    SourceId.BRICKRANKER: SourceConfig(
        source_id=SourceId.BRICKRANKER,
        fields_provided=frozenset({
            MetadataField.THEME,
            MetadataField.RETIRING_SOON,
        }),
    ),
}


# Validation rules

EARLIEST_LEGO_YEAR = 1949
MAX_FUTURE_YEARS = 2


def current_year() -> int:
    return datetime.now(tz=timezone.utc).year


def is_valid_year(year: int) -> bool:
    return EARLIEST_LEGO_YEAR <= year <= current_year() + MAX_FUTURE_YEARS


def is_valid_parts_count(count: int) -> bool:
    return 1 <= count <= 20_000


def is_valid_image_url(url: str) -> bool:
    return url.startswith(("http://", "https://")) and not url.startswith("data:")


def normalize_string(value: str | None) -> str | None:
    """Normalize string fields: strip whitespace, return None for empty."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None
