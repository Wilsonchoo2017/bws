"""GROUP 2: Fallback Logic tests for metadata enrichment."""

import pytest

from services.enrichment.circuit_breaker import CircuitBreakerState
from services.enrichment.orchestrator import enrich, resolve_fields
from services.enrichment.source_adapter import make_failed_result
from services.enrichment.types import (
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)


class TestFallbackLogic:
    """GROUP 2: Fallback when primary source fails or returns NULL."""

    def test_2_1_primary_fails_secondary_succeeds(self, make_item):
        """Given Bricklink returns HTTP 503, WorldBricks returns year=2018.
        Then falls through to WorldBricks, year=2018 stored."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return make_failed_result(SourceId.BRICKLINK, "HTTP 503: Service Unavailable")

        def worldbricks_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.WORLDBRICKS,
                success=True,
                fields={MetadataField.YEAR_RELEASED: 2018},
            )

        result, _ = enrich(
            "75955",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher, SourceId.WORLDBRICKS: worldbricks_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.YEAR_RELEASED,),
        )

        year_r = next(r for r in result.field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.FOUND
        assert year_r.value == 2018
        assert year_r.source == SourceId.WORLDBRICKS
        # Should have error from bricklink in the errors list
        assert any("bricklink" in e for e in year_r.errors)

    def test_2_2_primary_succeeds_but_null_for_field(self, make_item):
        """Given Bricklink succeeds but year_released=None.
        WorldBricks returns year=1980.
        Then treats NULL-field as 'not found at source', falls through."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.YEAR_RELEASED: None},
        )
        worldbricks_result = SourceResult(
            source=SourceId.WORLDBRICKS,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 1980},
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RELEASED,),
            {SourceId.BRICKLINK: bricklink_result, SourceId.WORLDBRICKS: worldbricks_result},
        )

        assert field_results[0].status == FieldStatus.FOUND
        assert field_results[0].value == 1980
        assert field_results[0].source == SourceId.WORLDBRICKS

    def test_2_3_all_sources_fail(self, make_item):
        """Given Bricklink returns error, WorldBricks returns error.
        Then year_released stays NULL, job status COMPLETED (not FAILED)."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return make_failed_result(SourceId.BRICKLINK, "Request error: ConnectionRefused")

        def worldbricks_fetcher(set_number: str) -> SourceResult:
            return make_failed_result(
                SourceId.WORLDBRICKS,
                "Set 99999 not found in WorldBricks search results",
            )

        result, _ = enrich(
            "99999",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher, SourceId.WORLDBRICKS: worldbricks_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.YEAR_RELEASED,),
        )

        year_r = next(r for r in result.field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.FAILED
        assert year_r.value is None
        assert len(year_r.errors) == 2

    def test_2_4_partial_success(self, make_item):
        """Given set needs theme, year_released, weight.
        BrickRanker returns theme. Bricklink fails. WorldBricks returns year but no weight.
        Then theme and year stored, weight NULL, job COMPLETED with partial success."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return make_failed_result(SourceId.BRICKLINK, "HTTP 500: Internal Server Error")

        def worldbricks_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.WORLDBRICKS,
                success=True,
                fields={MetadataField.YEAR_RELEASED: 2024},
            )

        def brickranker_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKRANKER,
                success=True,
                fields={MetadataField.THEME: "Star Wars"},
            )

        result, _ = enrich(
            "75375",
            item,
            {
                SourceId.BRICKLINK: bricklink_fetcher,
                SourceId.WORLDBRICKS: worldbricks_fetcher,
                SourceId.BRICKRANKER: brickranker_fetcher,
            },
            CircuitBreakerState(),
            fields=(MetadataField.THEME, MetadataField.YEAR_RELEASED, MetadataField.WEIGHT),
        )

        assert result.is_partial

        theme_r = next(r for r in result.field_results if r.field == MetadataField.THEME)
        assert theme_r.status == FieldStatus.FOUND
        assert theme_r.value == "Star Wars"

        year_r = next(r for r in result.field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.FOUND
        assert year_r.value == 2024

        weight_r = next(r for r in result.field_results if r.field == MetadataField.WEIGHT)
        assert weight_r.status == FieldStatus.FAILED  # only source (bricklink) failed
