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
        When enrichment runs, detects year_retired missing, queries WorldBricks."""
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

        def worldbricks_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.WORLDBRICKS,
                success=True,
                fields={MetadataField.YEAR_RETIRED: 2016},
            )

        result, _ = enrich(
            "10305",
            item,
            {SourceId.WORLDBRICKS: worldbricks_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.YEAR_RETIRED,),
        )

        retired_r = next(
            r for r in result.field_results if r.field == MetadataField.YEAR_RETIRED
        )
        assert retired_r.status == FieldStatus.FOUND
        assert retired_r.value == 2016

    def test_3_4_garbage_year_rejected(self):
        """Given WorldBricks returns year_released=9999.
        Then validation rejects it (outside valid range)."""
        assert validate_field(MetadataField.YEAR_RELEASED, 9999) is None

    def test_3_4_garbage_negative_parts_rejected(self):
        """Given parts_count=-5.
        Then validation rejects it."""
        assert validate_field(MetadataField.PARTS_COUNT, -5) is None

    def test_3_4_garbage_data_falls_through(self):
        """Given Bricklink returns year=9999 (invalid), WorldBricks returns year=2019.
        Then resolve_fields skips invalid and uses WorldBricks."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 9999},
        )
        worldbricks_result = SourceResult(
            source=SourceId.WORLDBRICKS,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 2019},
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RELEASED,),
            {SourceId.BRICKLINK: bricklink_result, SourceId.WORLDBRICKS: worldbricks_result},
        )

        assert field_results[0].status == FieldStatus.FOUND
        assert field_results[0].value == 2019
        assert field_results[0].source == SourceId.WORLDBRICKS

    def test_3_5_conflicting_data_uses_primary(self):
        """Given Bricklink returns year=2017, WorldBricks returns year=2019.
        Then resolve uses Bricklink (higher priority)."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 2017},
        )
        worldbricks_result = SourceResult(
            source=SourceId.WORLDBRICKS,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 2019},
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RELEASED,),
            {SourceId.BRICKLINK: bricklink_result, SourceId.WORLDBRICKS: worldbricks_result},
        )

        assert field_results[0].value == 2017
        assert field_results[0].source == SourceId.BRICKLINK

    def test_3_6_partial_data_from_multi_field_scrape(self):
        """Given WorldBricks returns year_released=2013 but dimensions=None.
        Then year stored, dimensions NOT_FOUND, no re-scrape."""
        worldbricks_result = SourceResult(
            source=SourceId.WORLDBRICKS,
            success=True,
            fields={
                MetadataField.YEAR_RELEASED: 2013,
                MetadataField.YEAR_RETIRED: None,
                MetadataField.PARTS_COUNT: 271,
            },
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RELEASED, MetadataField.YEAR_RETIRED, MetadataField.PARTS_COUNT),
            {SourceId.WORLDBRICKS: worldbricks_result},
        )

        year_r = next(r for r in field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.FOUND
        assert year_r.value == 2013

        retired_r = next(r for r in field_results if r.field == MetadataField.YEAR_RETIRED)
        assert retired_r.status == FieldStatus.NOT_FOUND

        parts_r = next(r for r in field_results if r.field == MetadataField.PARTS_COUNT)
        assert parts_r.status == FieldStatus.FOUND
        assert parts_r.value == 271

    def test_3_7_whitespace_title_normalized_to_none(self):
        """Given Bricklink returns title='   '.
        Then validation normalizes to None."""
        assert validate_field(MetadataField.TITLE, "   ") is None

    def test_3_7_empty_weight_normalized_to_none(self):
        """Given weight=''.
        Then validation normalizes to None."""
        assert validate_field(MetadataField.WEIGHT, "") is None

    def test_3_7_whitespace_falls_through(self):
        """Given Bricklink returns title='   ', WorldBricks returns 'Small Cottage'.
        Then resolve uses WorldBricks."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.TITLE: "   "},
        )
        worldbricks_result = SourceResult(
            source=SourceId.WORLDBRICKS,
            success=True,
            fields={MetadataField.TITLE: "Small Cottage"},
        )

        field_results = resolve_fields(
            (MetadataField.TITLE,),
            {SourceId.BRICKLINK: bricklink_result, SourceId.WORLDBRICKS: worldbricks_result},
        )

        assert field_results[0].value == "Small Cottage"
        assert field_results[0].source == SourceId.WORLDBRICKS
