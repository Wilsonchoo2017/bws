"""GWT tests for pure worker transformation functions.

These tests require NO mocks -- they exercise pure functions with plain data.
"""

from dataclasses import dataclass

from api.workers.transforms import (
    EMPTY_SATURATION_SUMMARY,
    catalog_item_to_dict,
    enrichment_log_summary,
    extract_set_numbers_from_catalog,
    mightyutan_product_to_dict,
    saturation_result_to_summary,
    shopee_item_to_dict,
    toysrus_product_to_dict,
)


# -- Shopee transforms -------------------------------------------------------


@dataclass
class FakeShopeeItem:
    title: str = "LEGO 75192 Millennium Falcon"
    price_display: str = "RM 3,299.00"
    sold_count: int = 42
    rating: float = 4.9
    shop_name: str = "LEGO Shop MY"
    product_url: str = "https://shopee.com.my/item/123"
    image_url: str = "https://img.example.com/75192.jpg"


class TestShopeeItemToDict:
    """Given a Shopee scraper item, verify pure transformation to dict."""

    def test_given_shopee_item_when_transformed_then_all_fields_present(self):
        """Given a Shopee item, when transformed, then dict has all expected keys."""
        result = shopee_item_to_dict(FakeShopeeItem())

        assert result["title"] == "LEGO 75192 Millennium Falcon"
        assert result["price_display"] == "RM 3,299.00"
        assert result["sold_count"] == 42
        assert result["rating"] == 4.9
        assert result["shop_name"] == "LEGO Shop MY"
        assert result["product_url"] == "https://shopee.com.my/item/123"
        assert result["image_url"] == "https://img.example.com/75192.jpg"

    def test_given_shopee_item_when_transformed_then_returns_new_dict(self):
        """Given a Shopee item, when transformed, then result is a plain dict (not the original)."""
        item = FakeShopeeItem()
        result = shopee_item_to_dict(item)

        assert isinstance(result, dict)
        assert len(result) == 7


# -- ToysRUs transforms ------------------------------------------------------


@dataclass
class FakeToysrusProduct:
    name: str = "LEGO Star Wars 75192"
    price_myr: float = 3299.90
    url: str = "https://toysrus.com.my/product/75192"
    image_url: str = "https://img.example.com/75192.jpg"


class TestToysrusProductToDict:
    """Given a ToysRUs product, verify pure transformation to dict."""

    def test_given_toysrus_product_when_transformed_then_price_formatted(self):
        """Given a ToysRUs product, when transformed, then price has RM prefix."""
        result = toysrus_product_to_dict(FakeToysrusProduct())

        assert result["price_display"] == "RM 3299.9"
        assert result["title"] == "LEGO Star Wars 75192"
        assert result["shop_name"] == 'Toys"R"Us Malaysia'

    def test_given_toysrus_product_when_transformed_then_sold_count_is_none(self):
        """Given a ToysRUs product, when transformed, then sold_count is None (not tracked)."""
        result = toysrus_product_to_dict(FakeToysrusProduct())

        assert result["sold_count"] is None
        assert result["rating"] is None


# -- Mighty Utan transforms --------------------------------------------------


@dataclass
class FakeMightyutanProduct:
    name: str = "LEGO City 60400"
    price_myr: float = 49.90
    total_sold: int = 25
    rating: float = 4.8
    url: str = "https://mightyutan.com.my/product/60400"
    image_url: str = "https://img.example.com/60400.jpg"
    available: bool = True
    original_price_myr: str | None = None
    is_special_price: bool = False


class TestMightyutanProductToDict:
    """Given a Mighty Utan product, verify pure transformation to dict."""

    def test_given_mightyutan_product_when_transformed_then_includes_sales(self):
        """Given a Mighty Utan product, when transformed, then sold_count and rating present."""
        result = mightyutan_product_to_dict(FakeMightyutanProduct())

        assert result["sold_count"] == 25
        assert result["rating"] == 4.8
        assert result["shop_name"] == "Mighty Utan Malaysia"

    def test_given_mightyutan_product_when_transformed_then_price_formatted(self):
        """Given a Mighty Utan product, when transformed, then price has RM prefix."""
        result = mightyutan_product_to_dict(FakeMightyutanProduct())

        assert result["price_display"] == "RM 49.9"

    def test_given_sold_out_product_when_transformed_then_available_false(self):
        """Given a sold-out product, when transformed, then available is False."""
        product = FakeMightyutanProduct(available=False)
        result = mightyutan_product_to_dict(product)

        assert result["available"] is False

    def test_given_discounted_product_when_transformed_then_original_price_present(self):
        """Given a discounted product, when transformed, then original_price_myr and is_special_price present."""
        product = FakeMightyutanProduct(
            price_myr=35.9,
            original_price_myr="44.9",
            is_special_price=True,
        )
        result = mightyutan_product_to_dict(product)

        assert result["price_display"] == "RM 35.9"
        assert result["original_price_myr"] == "44.9"
        assert result["is_special_price"] is True

    def test_given_regular_product_when_transformed_then_no_discount_fields(self):
        """Given a non-discounted product, when transformed, then original_price_myr is None."""
        result = mightyutan_product_to_dict(FakeMightyutanProduct())

        assert result["available"] is True
        assert result["original_price_myr"] is None
        assert result["is_special_price"] is False


# -- BrickLink catalog transforms --------------------------------------------


@dataclass
class FakeCatalogItem:
    item_id: str = "75192-1"
    item_type: str = "S"
    title: str = "Millennium Falcon"
    image_url: str = "https://img.bricklink.com/item.jpg"


class TestCatalogItemToDict:
    """Given a BrickLink catalog item, verify pure transformation to dict."""

    def test_given_catalog_item_when_transformed_then_url_built(self):
        """Given a catalog item, when transformed, then product_url includes type and id."""
        result = catalog_item_to_dict(FakeCatalogItem())

        assert "S=75192-1" in result["product_url"]
        assert result["title"] == "Millennium Falcon"
        assert result["price_display"] == "N/A"

    def test_given_catalog_item_with_no_title_when_transformed_then_uses_item_id(self):
        """Given a catalog item with no title, when transformed, then falls back to item_id."""
        item = FakeCatalogItem(title=None)
        result = catalog_item_to_dict(item)

        assert result["title"] == "75192-1"


class TestExtractSetNumbersFromCatalog:
    """Given catalog items, verify pure set number extraction."""

    def test_given_set_items_when_extracted_then_strips_variant_suffix(self):
        """Given set items with '-1' suffix, when extracted, then returns bare set numbers."""
        items = [
            FakeCatalogItem(item_id="75192-1", item_type="S"),
            FakeCatalogItem(item_id="10294-1", item_type="S"),
        ]
        result = extract_set_numbers_from_catalog(items)

        assert result == ["75192", "10294"]

    def test_given_non_set_items_when_extracted_then_filtered_out(self):
        """Given non-set items (minifigs, parts), when extracted, then excluded."""
        items = [
            FakeCatalogItem(item_id="75192-1", item_type="S"),
            FakeCatalogItem(item_id="sw0001", item_type="M"),
            FakeCatalogItem(item_id="3001", item_type="P"),
        ]
        result = extract_set_numbers_from_catalog(items)

        assert result == ["75192"]

    def test_given_empty_list_when_extracted_then_returns_empty(self):
        """Given no catalog items, when extracted, then returns empty list."""
        assert extract_set_numbers_from_catalog([]) == []

    def test_given_set_without_dash_when_extracted_then_filtered_out(self):
        """Given a set item with no dash in item_id, when extracted, then excluded."""
        items = [FakeCatalogItem(item_id="75192", item_type="S")]
        result = extract_set_numbers_from_catalog(items)

        assert result == []


# -- Saturation transforms ---------------------------------------------------


@dataclass
class FakeSaturationResult:
    successful: int = 5
    failed: int = 2
    skipped: int = 1
    total_items: int = 8


class TestSaturationResultToSummary:
    """Given a saturation batch result, verify pure transformation to summary."""

    def test_given_saturation_result_when_transformed_then_all_counts_present(self):
        """Given a batch result, when transformed, then summary has all count fields."""
        result = saturation_result_to_summary(FakeSaturationResult())

        assert result == {"successful": 5, "failed": 2, "skipped": 1, "total": 8}

    def test_given_empty_saturation_summary_when_accessed_then_all_zeros(self):
        """Given EMPTY_SATURATION_SUMMARY constant, when accessed, then all zeros."""
        assert EMPTY_SATURATION_SUMMARY == {
            "successful": 0, "failed": 0, "skipped": 0, "total": 0,
        }


# -- Enrichment log summary --------------------------------------------------


class TestEnrichmentLogSummary:
    """Given enrichment field details, verify pure log summary generation."""

    def test_given_mixed_results_when_summarized_then_lists_found_and_missing(self):
        """Given found and missing fields, when summarized, then both listed."""
        details = [
            {"field": "title", "status": "found"},
            {"field": "theme", "status": "found"},
            {"field": "weight", "status": "not_found"},
            {"field": "rrp", "status": "failed"},
        ]
        result = enrichment_log_summary(details)

        assert "2/4 fields found" in result
        assert "title, theme" in result
        assert "weight, rrp" in result

    def test_given_all_found_when_summarized_then_missing_shows_none(self):
        """Given all fields found, when summarized, then missing shows 'none'."""
        details = [
            {"field": "title", "status": "found"},
            {"field": "theme", "status": "found"},
        ]
        result = enrichment_log_summary(details)

        assert "2/2 fields found" in result
        assert "[missing: none]" in result

    def test_given_no_fields_when_summarized_then_zero_zero(self):
        """Given empty field details, when summarized, then 0/0."""
        result = enrichment_log_summary([])

        assert "0/0 fields found" in result
        assert "[found: none]" in result
        assert "[missing: none]" in result

    def test_given_all_missing_when_summarized_then_found_shows_none(self):
        """Given all fields missing, when summarized, then found shows 'none'."""
        details = [
            {"field": "weight", "status": "not_found"},
        ]
        result = enrichment_log_summary(details)

        assert "0/1 fields found" in result
        assert "[found: none]" in result
