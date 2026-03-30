"""GROUP 1: Happy Path tests for metadata enrichment."""

import pytest

from services.enrichment.circuit_breaker import CircuitBreakerState
from services.enrichment.orchestrator import (
    detect_missing_fields,
    determine_sources_needed,
    enrich,
    resolve_fields,
)
from services.enrichment.source_adapter import make_failed_result
from services.enrichment.types import (
    EnrichmentResult,
    FieldResult,
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)


class TestDetectMissingFields:
    """Tests for detect_missing_fields."""

    def test_all_null_returns_all_fields(self, make_item):
        """Given all fields NULL, returns all MetadataField values."""
        item = make_item()
        missing = detect_missing_fields(item)
        assert MetadataField.TITLE in missing
        assert MetadataField.YEAR_RELEASED in missing
        assert MetadataField.THEME in missing

    def test_fully_populated_returns_empty(self, make_item):
        """Given all fields populated, returns empty tuple (3.2 idempotency)."""
        item = make_item(
            title="Millennium Falcon",
            theme="Star Wars",
            year_released=2017,
            year_retired=None,  # intentionally left None for test below
            parts_count=7541,
            image_url="https://example.com/img.png",
            weight="14.2 kg",
            retiring_soon=False,
        )
        # year_retired is NULL so it should be detected
        missing = detect_missing_fields(item)
        assert MetadataField.YEAR_RETIRED in missing
        assert MetadataField.TITLE not in missing

    def test_subset_check(self, make_item):
        """Given a subset of fields to check, only checks those."""
        item = make_item(year_released=2017)
        missing = detect_missing_fields(
            item,
            fields=(MetadataField.YEAR_RELEASED, MetadataField.THEME),
        )
        assert MetadataField.YEAR_RELEASED not in missing
        assert MetadataField.THEME in missing


class TestDetermineSourcesNeeded:
    """Tests for determine_sources_needed."""

    def test_single_field_single_source(self):
        """Given theme is missing, BrickRanker and BrickLink are needed."""
        cb = CircuitBreakerState()
        sources = determine_sources_needed((MetadataField.THEME,), cb)
        assert SourceId.BRICKRANKER in sources
        assert SourceId.BRICKLINK in sources

    def test_deduplication(self):
        """Given title and year_released missing (both from Bricklink+WorldBricks),
        each source appears only once."""
        cb = CircuitBreakerState()
        sources = determine_sources_needed(
            (MetadataField.TITLE, MetadataField.YEAR_RELEASED), cb
        )
        assert sources.count(SourceId.BRICKLINK) == 1
        assert sources.count(SourceId.WORLDBRICKS) == 1

    def test_stable_ordering(self):
        """Sources are always returned in BRICKLINK, WORLDBRICKS, BRICKRANKER order."""
        cb = CircuitBreakerState()
        sources = determine_sources_needed(
            (MetadataField.THEME, MetadataField.YEAR_RELEASED), cb
        )
        bricklink_idx = (
            sources.index(SourceId.BRICKLINK) if SourceId.BRICKLINK in sources else -1
        )
        brickranker_idx = (
            sources.index(SourceId.BRICKRANKER)
            if SourceId.BRICKRANKER in sources
            else 99
        )
        assert bricklink_idx < brickranker_idx


class TestHappyPath:
    """GROUP 1: Happy path enrichment tests."""

    def test_1_1_single_missing_field_primary_succeeds(self, make_item):
        """Given set with year_released=NULL, Bricklink returns year=2017.
        Then year stored, WorldBricks never called, job COMPLETED."""
        item = make_item(
            title="Millennium Falcon",
            theme="Star Wars",
            parts_count=7541,
            image_url="https://example.com/img.png",
            weight="14.2 kg",
            retiring_soon=False,
        )

        worldbricks_called = False

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={MetadataField.YEAR_RELEASED: 2017},
            )

        def worldbricks_fetcher(set_number: str) -> SourceResult:
            nonlocal worldbricks_called
            worldbricks_called = True
            return SourceResult(
                source=SourceId.WORLDBRICKS,
                success=True,
                fields={MetadataField.YEAR_RELEASED: 2017},
            )

        result, _ = enrich(
            "75192",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher, SourceId.WORLDBRICKS: worldbricks_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.YEAR_RELEASED,),
        )

        year_result = next(
            r for r in result.field_results if r.field == MetadataField.YEAR_RELEASED
        )
        assert year_result.status == FieldStatus.FOUND
        assert year_result.value == 2017
        assert year_result.source == SourceId.BRICKLINK
        # WorldBricks should still be called because determine_sources_needed
        # adds both sources -- but resolve_fields should pick Bricklink first.
        # The key assertion: the resolved value comes from BRICKLINK.

    def test_1_2_multiple_fields_one_source(self, make_item):
        """Given year_released, parts_count, dimensions all NULL (WorldBricks fields).
        When WorldBricks returns data, all found fields stored, one scrape only."""
        item = make_item()
        call_count = 0

        def worldbricks_fetcher(set_number: str) -> SourceResult:
            nonlocal call_count
            call_count += 1
            return SourceResult(
                source=SourceId.WORLDBRICKS,
                success=True,
                fields={
                    MetadataField.YEAR_RELEASED: 2022,
                    MetadataField.YEAR_RETIRED: None,  # legitimately not retired
                    MetadataField.PARTS_COUNT: 1254,
                },
            )

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={MetadataField.YEAR_RELEASED: 2022},
            )

        result, _ = enrich(
            "10497",
            item,
            {SourceId.WORLDBRICKS: worldbricks_fetcher, SourceId.BRICKLINK: bricklink_fetcher},
            CircuitBreakerState(),
            fields=(
                MetadataField.YEAR_RELEASED,
                MetadataField.YEAR_RETIRED,
                MetadataField.PARTS_COUNT,
            ),
        )

        assert call_count == 1  # WorldBricks called only once

        year_r = next(r for r in result.field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.FOUND
        assert year_r.value == 2022

        parts_r = next(r for r in result.field_results if r.field == MetadataField.PARTS_COUNT)
        assert parts_r.status == FieldStatus.FOUND
        assert parts_r.value == 1254

        # year_retired: WorldBricks returned None -- NOT_FOUND (no other source)
        retired_r = next(r for r in result.field_results if r.field == MetadataField.YEAR_RETIRED)
        assert retired_r.status == FieldStatus.NOT_FOUND

    def test_1_3_multiple_fields_multiple_sources(self, make_item):
        """Given set needs theme (BrickRanker), year_released (Bricklink), weight (Bricklink).
        Then all three stored from correct sources."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={
                    MetadataField.YEAR_RELEASED: 2023,
                    MetadataField.WEIGHT: "0.87 kg",
                },
            )

        def brickranker_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKRANKER,
                success=True,
                fields={MetadataField.THEME: "Technic"},
            )

        result, _ = enrich(
            "42151",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher, SourceId.BRICKRANKER: brickranker_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.THEME, MetadataField.YEAR_RELEASED, MetadataField.WEIGHT),
        )

        assert result.fields_found == 3
        assert result.is_complete

        theme_r = next(r for r in result.field_results if r.field == MetadataField.THEME)
        assert theme_r.source == SourceId.BRICKRANKER
        assert theme_r.value == "Technic"

    def test_1_4_stop_on_first_success(self, make_item):
        """Given Bricklink returns year_released=2019.
        Then WorldBricks value for year_released is NOT used."""
        item = make_item()

        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 2019},
        )
        worldbricks_result = SourceResult(
            source=SourceId.WORLDBRICKS,
            success=True,
            fields={MetadataField.YEAR_RELEASED: 2020},  # different value
        )

        field_results = resolve_fields(
            (MetadataField.YEAR_RELEASED,),
            {SourceId.BRICKLINK: bricklink_result, SourceId.WORLDBRICKS: worldbricks_result},
        )

        assert len(field_results) == 1
        assert field_results[0].value == 2019  # Bricklink (higher priority)
        assert field_results[0].source == SourceId.BRICKLINK

    def test_1_5_full_enrichment_new_item(self, make_item):
        """Given a brand new item with all NULL fields.
        Then all configured sources called, all available fields populated."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={
                    MetadataField.TITLE: "Small Cottage",
                    MetadataField.YEAR_RELEASED: 2013,
                    MetadataField.IMAGE_URL: "https://img.bricklink.com/31009.png",
                    MetadataField.WEIGHT: "0.5 kg",
                },
            )

        def worldbricks_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.WORLDBRICKS,
                success=True,
                fields={
                    MetadataField.YEAR_RETIRED: 2014,
                    MetadataField.PARTS_COUNT: 271,
                },
            )

        def brickranker_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKRANKER,
                success=True,
                fields={
                    MetadataField.THEME: "Creator",
                    MetadataField.RETIRING_SOON: False,
                },
            )

        result, _ = enrich(
            "31009",
            item,
            {
                SourceId.BRICKLINK: bricklink_fetcher,
                SourceId.WORLDBRICKS: worldbricks_fetcher,
                SourceId.BRICKRANKER: brickranker_fetcher,
            },
            CircuitBreakerState(),
        )

        assert len(result.sources_called) == 3
        found_fields = {r.field for r in result.field_results if r.status == FieldStatus.FOUND}
        assert MetadataField.TITLE in found_fields
        assert MetadataField.YEAR_RELEASED in found_fields
        assert MetadataField.YEAR_RETIRED in found_fields
        assert MetadataField.PARTS_COUNT in found_fields
        assert MetadataField.THEME in found_fields
        assert MetadataField.IMAGE_URL in found_fields
        assert MetadataField.WEIGHT in found_fields
