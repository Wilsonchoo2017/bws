"""GROUP 5: Data Quality tests for metadata enrichment."""

import pytest

from services.enrichment.config import is_placeholder_title, is_valid_image_url, is_valid_year
from services.enrichment.orchestrator import detect_missing_fields, resolve_fields
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
        """Given Bricklink says year=2017.
        Then primary (Bricklink) value used."""
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

    def test_5_5_image_url_resolve_accepts_valid(self):
        """Given Bricklink returns valid URL.
        Then resolve picks Bricklink URL."""
        bricklink_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.IMAGE_URL: "https://img.bricklink.com/75192.png"},
        )

        field_results = resolve_fields(
            (MetadataField.IMAGE_URL,),
            {SourceId.BRICKLINK: bricklink_result},
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


class TestPlaceholderTitleDetection:
    """Placeholder titles like 'Image Coming Soon' should be treated as missing."""

    def test_is_placeholder_returns_true_for_known_patterns(self):
        assert is_placeholder_title("Image Coming Soon") is True
        assert is_placeholder_title("  image coming soon  ") is True
        assert is_placeholder_title("IMAGE COMING SOON") is True

    def test_is_placeholder_returns_true_for_none(self):
        assert is_placeholder_title(None) is True

    def test_is_placeholder_returns_false_for_real_titles(self):
        assert is_placeholder_title("Millennium Falcon") is False
        assert is_placeholder_title("Elsa's Ice Palace") is False

    def test_validate_field_rejects_placeholder_title(self):
        assert validate_field(MetadataField.TITLE, "Image Coming Soon") is None
        assert validate_field(MetadataField.TITLE, "  image coming soon  ") is None

    def test_validate_field_accepts_real_title(self):
        assert validate_field(MetadataField.TITLE, "Millennium Falcon") == "Millennium Falcon"

    def test_detect_missing_fields_includes_placeholder_title(self, make_item):
        """Given an item with a placeholder title, detect_missing_fields treats it as missing."""
        item = make_item(
            title="Image Coming Soon",
            theme="Star Wars",
            year_released=2017,
            parts_count=7541,
            image_url="https://example.com/img.png",
            weight="14.2 kg",
            minifig_count=7,
            dimensions="58.2 x 49.0 x 21.0 cm",
        )
        missing = detect_missing_fields(item)
        assert MetadataField.TITLE in missing

    def test_detect_missing_fields_excludes_real_title(self, make_item):
        """Given an item with a real title, it is not flagged as missing."""
        item = make_item(
            title="Millennium Falcon",
            theme="Star Wars",
            year_released=2017,
            parts_count=7541,
            image_url="https://example.com/img.png",
            weight="14.2 kg",
            minifig_count=7,
            dimensions="58.2 x 49.0 x 21.0 cm",
        )
        missing = detect_missing_fields(item)
        assert MetadataField.TITLE not in missing
