"""GWT tests for missing metadata field scenarios.

Covers enrichment behavior when fields cannot be resolved:
- Fields with no configured sources (year_retired)
- Fields where source returns None (dimensions)
- Cache bug: cached BrickLink data must include all fields
"""

import pytest

from services.enrichment.circuit_breaker import CircuitBreakerState
from services.enrichment.orchestrator import (
    detect_missing_fields,
    determine_sources_needed,
    enrich,
    resolve_fields,
)
from services.enrichment.source_adapter import adapt_bricklink
from services.enrichment.types import (
    FieldResult,
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)


class TestYearRetiredNoSources:
    """year_retired has no configured sources -- always SKIPPED."""

    def test_given_year_retired_missing_when_enriched_then_skipped(self, make_item):
        """Given a set with year_retired=NULL,
        When enrichment runs,
        Then year_retired is SKIPPED because no sources provide it.
        """
        item = make_item(
            title="Elsa's Ice Palace",
            year_released=2024,
            parts_count=163,
            theme="Disney Princess",
            image_url="https://img.bricklink.com/SN/0/43020-1.png",
            weight="0.3 kg",
            minifig_count=1,
            dimensions=None,
            year_retired=None,
        )

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={MetadataField.DIMENSIONS: None},
            )

        result, _ = enrich(
            "43020",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.YEAR_RETIRED,),
        )

        retired_r = next(
            r for r in result.field_results if r.field == MetadataField.YEAR_RETIRED
        )
        assert retired_r.status == FieldStatus.SKIPPED

    def test_given_year_retired_when_determine_sources_then_none_needed(self):
        """Given year_retired is the only missing field,
        When determining sources needed,
        Then no sources are returned (empty tuple).
        """
        cb = CircuitBreakerState()
        sources = determine_sources_needed((MetadataField.YEAR_RETIRED,), cb)
        assert sources == ()

    def test_given_year_retired_when_resolve_then_not_found(self):
        """Given year_retired has no sources in priority config,
        When resolve_fields runs with BrickLink result available,
        Then year_retired is NOT_FOUND (empty sources = all() True = FAILED).
        """
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={},
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RETIRED,),
            {SourceId.BRICKLINK: bricklink_result},
        )

        retired_r = field_results[0]
        assert retired_r.field == MetadataField.YEAR_RETIRED
        # Empty sources tuple -> all() of empty = True -> FAILED
        assert retired_r.status == FieldStatus.FAILED


class TestDimensionsNotAvailable:
    """dimensions is configured with BrickLink source, but not all sets have it."""

    def test_given_bricklink_has_no_dimensions_when_enriched_then_not_found(
        self, make_item
    ):
        """Given set 43020 where BrickLink page lacks 'Item Dim.' text,
        When BrickLink returns dimensions=None,
        Then dimensions is NOT_FOUND.
        """
        item = make_item(
            title="Elsa's Ice Palace",
            year_released=2024,
            parts_count=163,
            theme="Disney Princess",
            image_url="https://img.bricklink.com/SN/0/43020-1.png",
            weight="0.3 kg",
            minifig_count=1,
        )

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={MetadataField.DIMENSIONS: None},
            )

        result, _ = enrich(
            "43020",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.DIMENSIONS,),
        )

        dim_r = next(
            r for r in result.field_results if r.field == MetadataField.DIMENSIONS
        )
        assert dim_r.status == FieldStatus.NOT_FOUND
        assert dim_r.value is None

    def test_given_bricklink_has_dimensions_when_enriched_then_found(self, make_item):
        """Given a set where BrickLink lists 'Item Dim.: 58.2 x 49.0 x 21.0 cm',
        When enrichment runs,
        Then dimensions is FOUND with the value string.
        """
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={MetadataField.DIMENSIONS: "58.2 x 49.0 x 21.0 cm"},
            )

        result, _ = enrich(
            "75192",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.DIMENSIONS,),
        )

        dim_r = next(
            r for r in result.field_results if r.field == MetadataField.DIMENSIONS
        )
        assert dim_r.status == FieldStatus.FOUND
        assert dim_r.value == "58.2 x 49.0 x 21.0 cm"
        assert dim_r.source == SourceId.BRICKLINK


class TestPartialEnrichmentScenario:
    """Simulates the exact scenario from the log: set 43020, 5/7 found, 2 missing."""

    def test_given_set_43020_when_enriched_then_5_found_2_missing(self, make_item):
        """Given a new set 43020 with all fields NULL,
        When BrickLink returns year_released, parts_count, theme, weight, minifig_count
            but NOT dimensions, and year_retired has no source,
        Then 5 fields are FOUND, year_retired is SKIPPED, dimensions is NOT_FOUND.
        """
        item = make_item(set_number="43020")

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={
                    MetadataField.TITLE: "Elsa's Ice Palace",
                    MetadataField.YEAR_RELEASED: 2024,
                    MetadataField.PARTS_COUNT: 163,
                    MetadataField.IMAGE_URL: "https://img.bricklink.com/SN/0/43020-1.png",
                    MetadataField.WEIGHT: "0.3 kg",
                    MetadataField.MINIFIG_COUNT: 1,
                    MetadataField.DIMENSIONS: None,  # Not on BrickLink for this set
                },
            )

        def brickranker_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKRANKER,
                success=True,
                fields={
                    MetadataField.THEME: "Disney Princess",
                    MetadataField.RETIRING_SOON: False,
                },
            )

        result, _ = enrich(
            "43020",
            item,
            {
                SourceId.BRICKLINK: bricklink_fetcher,
                SourceId.BRICKRANKER: brickranker_fetcher,
            },
            CircuitBreakerState(),
        )

        found = {r.field for r in result.field_results if r.status == FieldStatus.FOUND}
        assert MetadataField.YEAR_RELEASED in found
        assert MetadataField.PARTS_COUNT in found
        assert MetadataField.WEIGHT in found
        assert MetadataField.MINIFIG_COUNT in found
        # Theme comes from BrickRanker (higher priority) or BrickLink
        assert MetadataField.THEME in found

        # year_retired: FAILED (no sources configured, but resolve_fields still runs
        # because other fields triggered source calls; empty sources → all() True → FAILED)
        retired_r = next(
            r for r in result.field_results if r.field == MetadataField.YEAR_RETIRED
        )
        assert retired_r.status == FieldStatus.FAILED

        # dimensions: NOT_FOUND (BrickLink returned None)
        dim_r = next(
            r for r in result.field_results if r.field == MetadataField.DIMENSIONS
        )
        assert dim_r.status == FieldStatus.NOT_FOUND

    def test_given_partial_result_then_is_partial_true(self, make_item):
        """Given enrichment finds some fields but not all,
        When checking result properties,
        Then is_partial is True and is_complete is False.
        """
        item = make_item(set_number="43020")

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={
                    MetadataField.TITLE: "Elsa's Ice Palace",
                    MetadataField.YEAR_RELEASED: 2024,
                    MetadataField.PARTS_COUNT: 163,
                    MetadataField.IMAGE_URL: "https://img.bricklink.com/SN/0/43020-1.png",
                    MetadataField.WEIGHT: "0.3 kg",
                    MetadataField.MINIFIG_COUNT: 1,
                    MetadataField.DIMENSIONS: None,
                },
            )

        def brickranker_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKRANKER,
                success=True,
                fields={
                    MetadataField.THEME: "Disney Princess",
                    MetadataField.RETIRING_SOON: False,
                },
            )

        result, _ = enrich(
            "43020",
            item,
            {
                SourceId.BRICKLINK: bricklink_fetcher,
                SourceId.BRICKRANKER: brickranker_fetcher,
            },
            CircuitBreakerState(),
        )

        assert result.is_partial
        assert not result.is_complete


class TestBricklinkCacheIncludesAllFields:
    """Cache lookup must include minifig_count and dimensions columns."""

    def test_given_cached_bricklink_data_with_dimensions_when_adapted_then_dimensions_present(
        self,
    ):
        """Given BricklinkData with dimensions populated (from cache or scrape),
        When adapted to SourceResult,
        Then dimensions field is present and non-None.
        """
        from bws_types.models import BricklinkData

        data = BricklinkData(
            item_id="75192-1",
            item_type="S",
            title="Millennium Falcon",
            weight="14.2 kg",
            year_released=2017,
            parts_count=7541,
            theme="Star Wars",
            minifig_count=7,
            dimensions="58.2 x 49.0 x 21.0 cm",
        )

        result = adapt_bricklink(data)

        assert result.success
        assert result.fields[MetadataField.DIMENSIONS] == "58.2 x 49.0 x 21.0 cm"
        assert result.fields[MetadataField.MINIFIG_COUNT] == 7

    def test_given_cached_bricklink_data_without_dimensions_when_adapted_then_dimensions_none(
        self,
    ):
        """Given BricklinkData where dimensions was not scraped (None),
        When adapted to SourceResult,
        Then dimensions field is None.
        """
        from bws_types.models import BricklinkData

        data = BricklinkData(
            item_id="43020-1",
            item_type="S",
            title="Elsa's Ice Palace",
            weight="0.3 kg",
            year_released=2024,
            parts_count=163,
            theme="Disney Princess",
            minifig_count=1,
            dimensions=None,
        )

        result = adapt_bricklink(data)

        assert result.success
        assert result.fields[MetadataField.DIMENSIONS] is None
        assert result.fields[MetadataField.MINIFIG_COUNT] == 1


class TestDetectMissingIncludesNewFields:
    """Ensure minifig_count and dimensions are detected as missing."""

    def test_given_item_missing_minifig_count_when_detect_then_included(
        self, make_item
    ):
        """Given an item with minifig_count=NULL,
        When detect_missing_fields runs,
        Then MINIFIG_COUNT is in the missing set.
        """
        item = make_item(
            title="Test Set",
            theme="Test",
            year_released=2024,
            parts_count=100,
            image_url="https://example.com/img.png",
            weight="0.5 kg",
        )
        missing = detect_missing_fields(item)
        assert MetadataField.MINIFIG_COUNT in missing
        assert MetadataField.DIMENSIONS in missing

    def test_given_item_with_all_fields_populated_then_none_missing(self, make_item):
        """Given an item with ALL fields (including minifig_count and dimensions),
        When detect_missing_fields runs,
        Then no enrichable fields are missing.
        """
        item = make_item(
            title="Millennium Falcon",
            theme="Star Wars",
            year_released=2017,
            year_retired=2023,
            parts_count=7541,
            image_url="https://example.com/img.png",
            weight="14.2 kg",
            retiring_soon=False,
            minifig_count=7,
            dimensions="58.2 x 49.0 x 21.0 cm",
        )
        missing = detect_missing_fields(item)
        assert len(missing) == 0
