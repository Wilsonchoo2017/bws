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

    def test_2_1_primary_fails_field_failed(self, make_item):
        """Given Bricklink returns HTTP 503 for year_released.
        Then year_released marked FAILED since no other source provides it."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return make_failed_result(SourceId.BRICKLINK, "HTTP 503: Service Unavailable")

        result, _ = enrich(
            "75955",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.YEAR_RELEASED,),
        )

        year_r = next(r for r in result.field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.FAILED
        assert year_r.value is None
        assert any("bricklink" in e for e in year_r.errors)

    def test_2_2_theme_fallback_brickranker_to_bricklink(self, make_item):
        """Given BrickRanker succeeds but theme=None.
        Bricklink returns theme='City'.
        Then falls through to Bricklink for theme."""
        brickranker_result = SourceResult(
            source=SourceId.BRICKRANKER,
            success=True,
            fields={MetadataField.THEME: None},
        )
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.THEME: "City"},
        )

        field_results = resolve_fields(
            (MetadataField.THEME,),
            {SourceId.BRICKRANKER: brickranker_result, SourceId.BRICKLINK: bricklink_result},
        )

        assert field_results[0].status == FieldStatus.FOUND
        assert field_results[0].value == "City"
        assert field_results[0].source == SourceId.BRICKLINK

    def test_2_3_all_sources_fail(self, make_item):
        """Given Bricklink returns error for year_released.
        Then year_released stays NULL, job status COMPLETED (not FAILED)."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return make_failed_result(SourceId.BRICKLINK, "Request error: ConnectionRefused")

        result, _ = enrich(
            "99999",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.YEAR_RELEASED,),
        )

        year_r = next(r for r in result.field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.FAILED
        assert year_r.value is None
        assert len(year_r.errors) >= 1

    def test_2_4_partial_success(self, make_item):
        """Given set needs theme, year_released, weight.
        BrickRanker returns theme. Bricklink fails.
        Then theme stored, year_released and weight NULL, job COMPLETED with partial success."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return make_failed_result(SourceId.BRICKLINK, "HTTP 500: Internal Server Error")

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
        assert year_r.status == FieldStatus.FAILED

        weight_r = next(r for r in result.field_results if r.field == MetadataField.WEIGHT)
        assert weight_r.status == FieldStatus.FAILED  # only source (bricklink) failed
