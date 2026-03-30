"""Tests for source-specific enrichment (Part 1 of the plan)."""

import pytest

from services.enrichment.circuit_breaker import CircuitBreakerState
from services.enrichment.config import SOURCE_CONFIGS
from services.enrichment.orchestrator import enrich
from services.enrichment.types import (
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)


class TestSourceSpecificEnrichment:
    """Tests for enriching from a single specified source."""

    def test_bricklink_only_calls_bricklink(self, make_item):
        """Given source=bricklink.
        When enrichment runs with only Bricklink fields.
        Then only Bricklink fetcher called, only Bricklink fields attempted."""
        item = make_item()
        worldbricks_called = False

        def bricklink_fetcher(sn: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={
                    MetadataField.TITLE: "Millennium Falcon",
                    MetadataField.YEAR_RELEASED: 2017,
                    MetadataField.WEIGHT: "14.2 kg",
                    MetadataField.IMAGE_URL: "https://img.bricklink.com/75192.png",
                },
            )

        def worldbricks_fetcher(sn: str) -> SourceResult:
            nonlocal worldbricks_called
            worldbricks_called = True
            return SourceResult(source=SourceId.WORLDBRICKS, success=True, fields={})

        fields = tuple(SOURCE_CONFIGS[SourceId.BRICKLINK].fields_provided)

        result, _ = enrich(
            "75192",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            CircuitBreakerState(),
            fields=fields,
        )

        assert not worldbricks_called
        assert SourceId.BRICKLINK in result.sources_called
        assert SourceId.WORLDBRICKS not in result.sources_called

        # Should have results for Bricklink fields only
        result_fields = {r.field for r in result.field_results}
        assert MetadataField.TITLE in result_fields
        assert MetadataField.YEAR_RELEASED in result_fields
        assert MetadataField.WEIGHT in result_fields
        assert MetadataField.IMAGE_URL in result_fields
        # Should NOT have WorldBricks-only fields
        assert MetadataField.YEAR_RETIRED not in result_fields
        # PARTS_COUNT and THEME are now also provided by BrickLink
        assert MetadataField.PARTS_COUNT in result_fields
        assert MetadataField.THEME in result_fields

    def test_worldbricks_only_calls_worldbricks(self, make_item):
        """Given source=worldbricks.
        When enrichment runs.
        Then only WorldBricks fetcher called."""
        item = make_item()

        def worldbricks_fetcher(sn: str) -> SourceResult:
            return SourceResult(
                source=SourceId.WORLDBRICKS,
                success=True,
                fields={
                    MetadataField.YEAR_RETIRED: 2023,
                    MetadataField.PARTS_COUNT: 7541,
                },
            )

        fields = tuple(SOURCE_CONFIGS[SourceId.WORLDBRICKS].fields_provided)

        result, _ = enrich(
            "75192",
            item,
            {SourceId.WORLDBRICKS: worldbricks_fetcher},
            CircuitBreakerState(),
            fields=fields,
        )

        assert SourceId.WORLDBRICKS in result.sources_called
        assert len(result.sources_called) == 1

        retired_r = next(
            (r for r in result.field_results if r.field == MetadataField.YEAR_RETIRED),
            None,
        )
        assert retired_r is not None
        assert retired_r.status == FieldStatus.FOUND
        assert retired_r.value == 2023

    def test_brickranker_only_calls_brickranker(self, make_item):
        """Given source=brickranker.
        When enrichment runs.
        Then only BrickRanker fetcher called, only theme/retiring_soon attempted."""
        item = make_item()

        def brickranker_fetcher(sn: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKRANKER,
                success=True,
                fields={
                    MetadataField.THEME: "Star Wars",
                    MetadataField.RETIRING_SOON: True,
                },
            )

        fields = tuple(SOURCE_CONFIGS[SourceId.BRICKRANKER].fields_provided)

        result, _ = enrich(
            "75192",
            item,
            {SourceId.BRICKRANKER: brickranker_fetcher},
            CircuitBreakerState(),
            fields=fields,
        )

        assert result.sources_called == (SourceId.BRICKRANKER,)
        result_fields = {r.field for r in result.field_results}
        assert result_fields == {MetadataField.THEME, MetadataField.RETIRING_SOON}


class TestJobUrlParsing:
    """Tests for parsing job URL format '75192' or '75192:bricklink'."""

    def test_plain_set_number(self):
        """Given '75192'. Then set_number='75192', source=None."""
        job_url = "75192"
        if ":" in job_url:
            set_number, source = job_url.split(":", 1)
        else:
            set_number = job_url
            source = None
        assert set_number == "75192"
        assert source is None

    def test_set_number_with_source(self):
        """Given '75192:bricklink'. Then set_number='75192', source='bricklink'."""
        job_url = "75192:bricklink"
        set_number, source = job_url.split(":", 1)
        assert set_number == "75192"
        assert source == "bricklink"

    def test_set_number_with_suffix_and_source(self):
        """Given '75192-1:worldbricks'. Then parsed correctly."""
        job_url = "75192-1:worldbricks"
        set_number, source = job_url.split(":", 1)
        assert set_number == "75192-1"
        assert source == "worldbricks"
