"""GROUP 3: Edge Case tests for metadata enrichment."""

import pytest

from services.enrichment.circuit_breaker import CircuitBreakerState
from services.enrichment.orchestrator import detect_missing_fields, enrich, resolve_fields
from services.enrichment.types import (
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)
from services.enrichment.validator import validate_field


class TestEdgeCases:
    """GROUP 3: Edge cases in enrichment."""

    def test_3_2_idempotency_all_populated(self, make_item):
        """Given all fields already populated.
        When enrichment runs, no sources called, no DB writes."""
        item = make_item(
            title="Millennium Falcon",
            theme="Star Wars",
            year_released=2017,
            year_retired=2023,
            parts_count=7541,
            image_url="https://example.com/img.png",
            weight="14.2 kg",
            retiring_soon=False,
        )

        call_count = 0

        def any_fetcher(set_number: str) -> SourceResult:
            nonlocal call_count
            call_count += 1
            return SourceResult(source=SourceId.BRICKLINK, success=True, fields={})

        result, _ = enrich(
            "42151",
            item,
            {SourceId.BRICKLINK: any_fetcher},
            CircuitBreakerState(),
        )

        assert len(result.field_results) == 0
        assert call_count == 0

    def test_3_3_re_enrichment_after_field_cleared(self, make_item):
        """Given set had year_retired cleared to NULL.
        When enrichment runs, detects year_retired missing.
        Since YEAR_RETIRED has no sources, result is empty."""
        item = make_item(
            title="Palace Cinema",
            theme="Creator Expert",
            year_released=2013,
            year_retired=None,  # cleared
            parts_count=2194,
            image_url="https://example.com/img.png",
            weight="3.0 kg",
            retiring_soon=False,
        )

        result, _ = enrich(
            "10305",
            item,
            {SourceId.BRICKLINK: lambda sn: SourceResult(
                source=SourceId.BRICKLINK, success=True, fields={},
            )},
            CircuitBreakerState(),
            fields=(MetadataField.YEAR_RETIRED,),
        )

        # YEAR_RETIRED has no sources in FIELD_SOURCE_PRIORITY, so it is SKIPPED
        retired_r = next(
            r for r in result.field_results if r.field == MetadataField.YEAR_RETIRED
        )
        assert retired_r.status == FieldStatus.SKIPPED

    def test_3_4_garbage_year_rejected(self):
        """Given source returns year_released=9999.
        Then validation rejects it (outside valid range)."""
        assert validate_field(MetadataField.YEAR_RELEASED, 9999) is None

    def test_3_4_garbage_negative_parts_rejected(self):
        """Given parts_count=-5.
        Then validation rejects it."""
        assert validate_field(MetadataField.PARTS_COUNT, -5) is None

    def test_3_4_garbage_data_rejected(self):
        """Given Bricklink returns year=9999 (invalid).
        Then resolve_fields rejects invalid value."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 9999},
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RELEASED,),
            {SourceId.BRICKLINK: bricklink_result},
        )

        assert field_results[0].status == FieldStatus.NOT_FOUND
        assert field_results[0].value is None

    def test_3_5_bricklink_provides_year(self):
        """Given Bricklink returns year=2017.
        Then resolve uses Bricklink value."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 2017},
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RELEASED,),
            {SourceId.BRICKLINK: bricklink_result},
        )

        assert field_results[0].value == 2017
        assert field_results[0].source == SourceId.BRICKLINK

    def test_3_6_partial_data_from_multi_field_scrape(self):
        """Given BrickLink returns year_released=2013 but parts_count=None.
        Then year stored, parts_count NOT_FOUND, no re-scrape."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={
                MetadataField.YEAR_RELEASED: 2013,
                MetadataField.PARTS_COUNT: None,
            },
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RELEASED, MetadataField.PARTS_COUNT),
            {SourceId.BRICKLINK: bricklink_result},
        )

        year_r = next(r for r in field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.FOUND
        assert year_r.value == 2013

        parts_r = next(r for r in field_results if r.field == MetadataField.PARTS_COUNT)
        assert parts_r.status == FieldStatus.NOT_FOUND

    def test_3_7_whitespace_title_normalized_to_none(self):
        """Given Bricklink returns title='   '.
        Then validation normalizes to None."""
        assert validate_field(MetadataField.TITLE, "   ") is None

    def test_3_7_empty_weight_normalized_to_none(self):
        """Given weight=''.
        Then validation normalizes to None."""
        assert validate_field(MetadataField.WEIGHT, "") is None

    def test_3_7_whitespace_title_not_found(self):
        """Given Bricklink returns title='   '.
        Then resolve returns NOT_FOUND since no other sources available."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.TITLE: "   "},
        )

        field_results = resolve_fields(
            (MetadataField.TITLE,),
            {SourceId.BRICKLINK: bricklink_result},
        )

        assert field_results[0].status == FieldStatus.NOT_FOUND
        assert field_results[0].value is None
