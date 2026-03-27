"""Tests for source adapters -- mapping source data to enrichment fields."""

import pytest

from bws_types.models import BricklinkData
from services.brickranker.parser import RetirementItem
from services.enrichment.source_adapter import (
    adapt_bricklink,
    adapt_brickranker,
    adapt_worldbricks,
    make_failed_result,
)
from services.enrichment.types import MetadataField, SourceId
from services.worldbricks.parser import WorldBricksData


class TestAdaptBricklink:
    def test_extracts_all_fields(self):
        data = BricklinkData(
            item_id="75192-1",
            item_type="S",
            title="Millennium Falcon",
            weight="14.2 kg",
            year_released=2017,
            image_url="https://img.bricklink.com/75192.png",
        )
        result = adapt_bricklink(data)
        assert result.success
        assert result.source == SourceId.BRICKLINK
        assert result.fields[MetadataField.TITLE] == "Millennium Falcon"
        assert result.fields[MetadataField.YEAR_RELEASED] == 2017
        assert result.fields[MetadataField.WEIGHT] == "14.2 kg"
        assert result.fields[MetadataField.IMAGE_URL] == "https://img.bricklink.com/75192.png"

    def test_handles_none_fields(self):
        data = BricklinkData(item_id="99999-1", item_type="S")
        result = adapt_bricklink(data)
        assert result.success
        assert result.fields[MetadataField.TITLE] is None
        assert result.fields[MetadataField.YEAR_RELEASED] is None


class TestAdaptWorldBricks:
    def test_extracts_all_fields(self):
        data = WorldBricksData(
            set_number="31009",
            set_name="Small Cottage",
            year_released=2013,
            year_retired=2014,
            parts_count=271,
            dimensions="26x19x14 cm",
            image_url="https://worldbricks.com/31009.jpg",
        )
        result = adapt_worldbricks(data)
        assert result.success
        assert result.source == SourceId.WORLDBRICKS
        assert result.fields[MetadataField.TITLE] == "Small Cottage"
        assert result.fields[MetadataField.YEAR_RELEASED] == 2013
        assert result.fields[MetadataField.YEAR_RETIRED] == 2014
        assert result.fields[MetadataField.PARTS_COUNT] == 271
        assert result.fields[MetadataField.IMAGE_URL] == "https://worldbricks.com/31009.jpg"


class TestAdaptBrickRanker:
    def test_extracts_all_fields(self):
        item = RetirementItem(
            set_number="75375",
            set_name="Millennium Falcon",
            year_released=2024,
            retiring_soon=True,
            expected_retirement_date="2025-12-31",
            theme="Star Wars",
            image_url="https://brickranker.com/75375.jpg",
        )
        result = adapt_brickranker(item)
        assert result.success
        assert result.source == SourceId.BRICKRANKER
        assert result.fields[MetadataField.THEME] == "Star Wars"
        assert result.fields[MetadataField.RETIRING_SOON] is True

    def test_none_theme(self):
        item = RetirementItem(set_number="99999", set_name="Unknown")
        result = adapt_brickranker(item)
        assert result.fields[MetadataField.THEME] is None
        assert result.fields[MetadataField.RETIRING_SOON] is False


class TestMakeFailedResult:
    def test_creates_failed_result(self):
        result = make_failed_result(SourceId.BRICKLINK, "HTTP 503")
        assert not result.success
        assert result.source == SourceId.BRICKLINK
        assert result.error == "HTTP 503"
        assert result.fields == {}
