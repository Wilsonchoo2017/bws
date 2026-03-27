"""Enrichment orchestrator -- coordinates sources to fill missing metadata.

Core algorithm:
1. Detect which fields are missing for a set
2. Determine which sources are needed (deduplicated, respecting priority)
3. Call each source once, extract all available fields
4. For each missing field, use the first source (by priority) that returned a value
5. Validate all values before storage
"""

import logging
from typing import TYPE_CHECKING

from services.enrichment.circuit_breaker import (
    CircuitBreakerState,
    is_available,
    record_failure,
    record_success,
)
from services.enrichment.config import (
    FIELD_SOURCE_PRIORITY,
    SOURCE_CONFIGS,
)
from services.enrichment.types import (
    EnrichmentResult,
    FieldResult,
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)
from services.enrichment.validator import validate_field

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("bws.enrichment")


# Type alias for the source fetcher function.
# Each source fetcher takes a set_number and returns a SourceResult.
SourceFetcher = "Callable[[str], SourceResult]"


def detect_missing_fields(
    item: dict,
    fields: tuple[MetadataField, ...] | None = None,
) -> tuple[MetadataField, ...]:
    """Detect which metadata fields are missing (NULL) for an item.

    Args:
        item: Dict from lego_items table (keys match column names)
        fields: Optional subset of fields to check (default: all)

    Returns:
        Tuple of missing MetadataField values
    """
    check_fields = fields or tuple(MetadataField)
    missing: list[MetadataField] = []

    field_to_column = {
        MetadataField.TITLE: "title",
        MetadataField.YEAR_RELEASED: "year_released",
        MetadataField.YEAR_RETIRED: "year_retired",
        MetadataField.PARTS_COUNT: "parts_count",
        MetadataField.THEME: "theme",
        MetadataField.IMAGE_URL: "image_url",
        MetadataField.WEIGHT: "weight",
        MetadataField.RETIRING_SOON: "retiring_soon",
    }

    for f in check_fields:
        col = field_to_column.get(f)
        if col is None:
            continue
        value = item.get(col)
        if value is None:
            missing.append(f)

    return tuple(missing)


def determine_sources_needed(
    missing_fields: tuple[MetadataField, ...],
    cb_state: CircuitBreakerState,
) -> tuple[SourceId, ...]:
    """Determine which sources to call, deduplicated and ordered.

    Groups missing fields by source priority, deduplicates sources,
    and filters out circuit-broken sources.

    Returns sources in a stable order: BRICKLINK, WORLDBRICKS, BRICKRANKER.
    """
    needed: set[SourceId] = set()

    for field in missing_fields:
        sources = FIELD_SOURCE_PRIORITY.get(field, ())
        for source_id in sources:
            config = SOURCE_CONFIGS[source_id]
            if is_available(cb_state, source_id, config.circuit_breaker_cooldown_seconds):
                needed.add(source_id)

    # Stable ordering
    order = (SourceId.BRICKLINK, SourceId.WORLDBRICKS, SourceId.BRICKRANKER)
    return tuple(s for s in order if s in needed)


def resolve_fields(
    missing_fields: tuple[MetadataField, ...],
    source_results: dict[SourceId, SourceResult],
) -> tuple[FieldResult, ...]:
    """Resolve each missing field using source results and priority order.

    For each field, tries sources in priority order and uses the first
    valid (non-None, validated) value. This is the stop-on-first-success logic.
    """
    results: list[FieldResult] = []

    for field in missing_fields:
        sources = FIELD_SOURCE_PRIORITY.get(field, ())
        errors: list[str] = []
        resolved = False

        for source_id in sources:
            sr = source_results.get(source_id)
            if sr is None:
                continue

            if not sr.success:
                errors.append(f"{source_id.value}: {sr.error}")
                continue

            raw_value = sr.fields.get(field)
            validated = validate_field(field, raw_value)

            if validated is not None:
                results.append(FieldResult(
                    field=field,
                    status=FieldStatus.FOUND,
                    value=validated,
                    source=source_id,
                    errors=tuple(errors),
                ))
                resolved = True
                break

            # Source succeeded but returned None for this field
            errors.append(f"{source_id.value}: field not available")

        if not resolved:
            # Distinguish "all sources tried, none had it" from "all failed"
            all_failed = all(
                not source_results.get(s, SourceResult(source=s, success=False, fields={})).success
                for s in sources
                if s in source_results
            )
            status = FieldStatus.FAILED if all_failed else FieldStatus.NOT_FOUND
            results.append(FieldResult(
                field=field,
                status=status,
                errors=tuple(errors),
            ))

    return tuple(results)


def enrich(
    set_number: str,
    item: dict,
    fetchers: dict[SourceId, "SourceFetcher"],
    cb_state: CircuitBreakerState,
    *,
    fields: tuple[MetadataField, ...] | None = None,
) -> tuple[EnrichmentResult, CircuitBreakerState]:
    """Run enrichment for a single LEGO set.

    This is the main entry point. It:
    1. Detects missing fields
    2. Determines which sources to call
    3. Calls each source once via the fetcher functions
    4. Resolves fields using priority + stop-on-first-success
    5. Updates circuit breaker state

    Args:
        set_number: LEGO set number
        item: Dict from lego_items table
        fetchers: Map of SourceId -> callable that fetches from that source
        cb_state: Current circuit breaker state
        fields: Optional subset of fields to enrich

    Returns:
        Tuple of (EnrichmentResult, updated CircuitBreakerState)
    """
    missing = detect_missing_fields(item, fields)

    if not missing:
        return (
            EnrichmentResult(set_number=set_number, field_results=()),
            cb_state,
        )

    sources_needed = determine_sources_needed(missing, cb_state)

    if not sources_needed:
        # All sources circuit-broken
        field_results = tuple(
            FieldResult(
                field=f,
                status=FieldStatus.SKIPPED,
                errors=("all sources unavailable (circuit breaker open)",),
            )
            for f in missing
        )
        return (
            EnrichmentResult(
                set_number=set_number,
                field_results=field_results,
            ),
            cb_state,
        )

    # Call each source once
    source_results: dict[SourceId, SourceResult] = {}
    sources_called: list[SourceId] = []

    for source_id in sources_needed:
        fetcher = fetchers.get(source_id)
        if fetcher is None:
            logger.warning("No fetcher registered for %s", source_id.value)
            continue

        sources_called.append(source_id)
        result = fetcher(set_number)
        source_results[source_id] = result

        # Update circuit breaker
        config = SOURCE_CONFIGS[source_id]
        if result.success:
            cb_state = record_success(cb_state, source_id)
        else:
            cb_state = record_failure(
                cb_state, source_id, config.circuit_breaker_threshold
            )

    # Resolve fields
    field_results = resolve_fields(missing, source_results)

    return (
        EnrichmentResult(
            set_number=set_number,
            field_results=field_results,
            sources_called=tuple(sources_called),
        ),
        cb_state,
    )
