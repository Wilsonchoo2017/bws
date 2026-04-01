"""Tests for source adapters -- mapping source data to enrichment fields."""

import pytest

from bws_types.models import BricklinkData
from services.enrichment.source_adapter import (
    adapt_bricklink,
    make_failed_result,
)
from services.enrichment.types import MetadataField, SourceId


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


class TestMakeFailedResult:
    def test_creates_failed_result(self):
        result = make_failed_result(SourceId.BRICKLINK, "HTTP 503")
        assert not result.success
        assert result.source == SourceId.BRICKLINK
        assert result.error == "HTTP 503"
        assert result.fields == {}
