"""Types for the metadata enrichment system.

Frozen dataclasses for enrichment jobs, field results, and source configuration.
"""

from dataclasses import dataclass
from enum import Enum


class FieldStatus(Enum):
    """Result status for a single metadata field."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    NOT_AVAILABLE = "not_available"
    FAILED = "failed"
    SKIPPED = "skipped"


class SourceId(Enum):
    """Identifier for each metadata source."""

    BRICKLINK = "bricklink"
    WORLDBRICKS = "worldbricks"
    BRICKRANKER = "brickranker"


class MetadataField(Enum):
    """Metadata fields that can be enriched."""

    TITLE = "title"
    YEAR_RELEASED = "year_released"
    YEAR_RETIRED = "year_retired"
    PARTS_COUNT = "parts_count"
    THEME = "theme"
    IMAGE_URL = "image_url"
    WEIGHT = "weight"
    RETIRING_SOON = "retiring_soon"


@dataclass(frozen=True)
class FieldResult:
    """Result of enriching a single field."""

    field: MetadataField
    status: FieldStatus
    value: str | int | bool | None = None
    source: SourceId | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceResult:
    """Result of calling a single source."""

    source: SourceId
    success: bool
    fields: dict[MetadataField, str | int | bool | None]
    error: str | None = None


@dataclass(frozen=True)
class EnrichmentResult:
    """Complete result of enriching a LEGO set."""

    set_number: str
    field_results: tuple[FieldResult, ...]
    sources_called: tuple[SourceId, ...] = ()

    @property
    def fields_found(self) -> int:
        return sum(1 for r in self.field_results if r.status == FieldStatus.FOUND)

    @property
    def fields_missing(self) -> int:
        return sum(
            1
            for r in self.field_results
            if r.status in (FieldStatus.NOT_FOUND, FieldStatus.FAILED)
        )

    @property
    def is_partial(self) -> bool:
        return self.fields_found > 0 and self.fields_missing > 0

    @property
    def is_complete(self) -> bool:
        return self.fields_missing == 0
