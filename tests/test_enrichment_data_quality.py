"""GROUP 5: Data Quality tests for metadata enrichment."""

import pytest

from services.enrichment.config import is_valid_image_url, is_valid_year
from services.enrichment.orchestrator import resolve_fields
from services.enrichment.types import (
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)
from services.enrichment.validator import validate_field


class TestDataQuality:
    """GROUP 5: Data quality validation and normalization."""

    def test_5_1_year_boundary_1949_accepted(self):
        """Given year_released=1949 (earliest LEGO year). Then accepted."""
        assert is_valid_year(1949)
        assert validate_field(MetadataField.YEAR_RELEASED, 1949) == 1949

    def test_5_1_year_boundary_current_plus_2_accepted(self):
        """Given year_released=current+2 (borderline). Then accepted."""
        from services.enrichment.config import current_year

        future_year = current_year() + 2
        assert is_valid_year(future_year)
        assert validate_field(MetadataField.YEAR_RELEASED, future_year) == future_year

    def test_5_1_year_boundary_1948_rejected(self):
        """Given year_released=1948 (too old). Then rejected."""
        assert not is_valid_year(1948)
        assert validate_field(MetadataField.YEAR_RELEASED, 1948) is None

    def test_5_1_year_boundary_far_future_rejected(self):
        """Given year_released=current+3. Then rejected."""
        from services.enrichment.config import current_year

        too_far = current_year() + 3
        assert not is_valid_year(too_far)
        assert validate_field(MetadataField.YEAR_RELEASED, too_far) is None

    def test_5_2_cross_source_consistency_uses_primary(self):
        """Given Bricklink says year=2017, WorldBricks says year=2019.
        Then primary (Bricklink) value used."""
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

    def test_5_5_valid_https_url_accepted(self):
        """Given valid HTTPS image URL. Then accepted."""
        url = "https://img.bricklink.com/ItemImage/SN/0/75192-1.png"
        assert is_valid_image_url(url)
        assert validate_field(MetadataField.IMAGE_URL, url) == url

    def test_5_5_base64_image_rejected(self):
        """Given base64 data URI. Then rejected."""
        url = "data:image/gif;base64,R0lGODlhAQABAIAAAA=="
        assert not is_valid_image_url(url)
        assert validate_field(MetadataField.IMAGE_URL, url) is None

    def test_5_5_http_url_accepted(self):
        """Given HTTP (non-HTTPS) image URL. Then accepted."""
        url = "http://example.com/image.jpg"
        assert is_valid_image_url(url)

    def test_5_5_image_url_resolve_rejects_bad(self):
        """Given Bricklink returns valid URL, WorldBricks returns base64 placeholder.
        Then resolve picks Bricklink URL."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.IMAGE_URL: "https://img.bricklink.com/75192.png"},
        )
        worldbricks_result = SourceResult(
            source=SourceId.WORLDBRICKS,
            success=True,
            fields={MetadataField.IMAGE_URL: "data:image/gif;base64,R0lGODlh"},
        )

        field_results = resolve_fields(
            (MetadataField.IMAGE_URL,),
            {SourceId.BRICKLINK: bricklink_result, SourceId.WORLDBRICKS: worldbricks_result},
        )

        assert field_results[0].value == "https://img.bricklink.com/75192.png"
        assert field_results[0].source == SourceId.BRICKLINK

    def test_parts_count_valid_range(self):
        """Given valid parts count values. Then accepted."""
        assert validate_field(MetadataField.PARTS_COUNT, 1) == 1
        assert validate_field(MetadataField.PARTS_COUNT, 7541) == 7541
        assert validate_field(MetadataField.PARTS_COUNT, 20000) == 20000

    def test_parts_count_invalid_range(self):
        """Given invalid parts count values. Then rejected."""
        assert validate_field(MetadataField.PARTS_COUNT, 0) is None
        assert validate_field(MetadataField.PARTS_COUNT, -1) is None
        assert validate_field(MetadataField.PARTS_COUNT, 20001) is None

    def test_retiring_soon_boolean(self):
        """Given boolean retiring_soon values. Then accepted."""
        assert validate_field(MetadataField.RETIRING_SOON, True) is True
        assert validate_field(MetadataField.RETIRING_SOON, False) is False

    def test_retiring_soon_non_boolean_rejected(self):
        """Given non-boolean retiring_soon. Then rejected."""
        assert validate_field(MetadataField.RETIRING_SOON, "yes") is None
        assert validate_field(MetadataField.RETIRING_SOON, 1) is None

    def test_title_strips_whitespace(self):
        """Given title with leading/trailing whitespace. Then stripped."""
        assert validate_field(MetadataField.TITLE, "  Millennium Falcon  ") == "Millennium Falcon"

    def test_theme_strips_whitespace(self):
        """Given theme with whitespace. Then stripped."""
        assert validate_field(MetadataField.THEME, " Star Wars ") == "Star Wars"
