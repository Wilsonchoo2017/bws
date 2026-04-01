"""Configuration for the metadata enrichment system.

Defines which sources provide which fields, priority ordering,
validation rules, and freshness windows.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from services.enrichment.types import MetadataField, SourceId

# Skip BrickLink pricing writes if last scraped within this window
PRICING_FRESHNESS = timedelta(days=7)


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
    MetadataField.TITLE: (SourceId.BRICKLINK, SourceId.BRICKECONOMY),
    MetadataField.YEAR_RELEASED: (SourceId.BRICKLINK, SourceId.BRICKECONOMY),
    MetadataField.YEAR_RETIRED: (),
    MetadataField.PARTS_COUNT: (SourceId.BRICKLINK, SourceId.BRICKECONOMY),
    MetadataField.THEME: (SourceId.BRICKRANKER, SourceId.BRICKLINK, SourceId.BRICKECONOMY),
    MetadataField.IMAGE_URL: (SourceId.BRICKLINK, SourceId.BRICKECONOMY),
    MetadataField.WEIGHT: (SourceId.BRICKLINK,),
    MetadataField.RETIRING_SOON: (SourceId.BRICKRANKER,),
    MetadataField.MINIFIG_COUNT: (SourceId.BRICKLINK, SourceId.BRICKECONOMY),
    MetadataField.DIMENSIONS: (SourceId.BRICKLINK,),
}

SOURCE_CONFIGS: dict[SourceId, SourceConfig] = {
    SourceId.BRICKLINK: SourceConfig(
        source_id=SourceId.BRICKLINK,
        fields_provided=frozenset({
            MetadataField.TITLE,
            MetadataField.YEAR_RELEASED,
            MetadataField.IMAGE_URL,
            MetadataField.WEIGHT,
            MetadataField.PARTS_COUNT,
            MetadataField.THEME,
            MetadataField.MINIFIG_COUNT,
            MetadataField.DIMENSIONS,
        }),
        circuit_breaker_cooldown_seconds=3600,  # 1 hour (matches BrickLink quota reset)
    ),
    SourceId.BRICKRANKER: SourceConfig(
        source_id=SourceId.BRICKRANKER,
        fields_provided=frozenset({
            MetadataField.THEME,
            MetadataField.RETIRING_SOON,
        }),
    ),
    SourceId.BRICKECONOMY: SourceConfig(
        source_id=SourceId.BRICKECONOMY,
        fields_provided=frozenset({
            MetadataField.TITLE,
            MetadataField.YEAR_RELEASED,
            MetadataField.PARTS_COUNT,
            MetadataField.THEME,
            MetadataField.IMAGE_URL,
            MetadataField.MINIFIG_COUNT,
        }),
        circuit_breaker_cooldown_seconds=3600,  # 1 hour
    ),
}

# Sources that must always be called during enrichment, regardless of
# which fields are missing.  This ensures every item gets a BrickEconomy
# snapshot even when all metadata fields are already filled.
MANDATORY_SOURCES: frozenset[SourceId] = frozenset({SourceId.BRICKECONOMY})


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


# Placeholder titles that should be treated as missing data.
PLACEHOLDER_TITLE_PATTERNS: tuple[str, ...] = (
    "image coming soon",
)


def is_placeholder_title(title: str | None) -> bool:
    """Return True if the title is None or a known placeholder string."""
    if title is None:
        return True
    normalized = title.strip().lower()
    return any(pattern in normalized for pattern in PLACEHOLDER_TITLE_PATTERNS)
