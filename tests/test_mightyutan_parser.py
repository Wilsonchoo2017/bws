"""GWT tests for Mighty Utan parser.

Covers: RSC extraction, product parsing, pagination, sold-out detection,
special pricing, edge cases, and malformed input handling.
"""

import json

import pytest

from services.mightyutan.parser import (
    MightyUtanProduct,
    PaginationInfo,
    _find_matching_brace,
    _parse_product,
    parse_page,
)


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

def _build_rsc_html(pagination_data: dict) -> str:
    """Build minimal HTML with RSC push block containing pagination data.

    Mimics the real Next.js RSC format: the JSON is wrapped in a JS string
    literal inside self.__next_f.push([1,"..."]), so it goes through
    one level of JS string escaping (unicode_escape decode reverses this).
    """
    pagination_json = json.dumps(pagination_data, separators=(",", ":"))
    inner = f'{{"productListingPagination":{pagination_json}}}'
    js_escaped = inner.encode("unicode_escape").decode("ascii")
    return f'<script>self.__next_f.push([1,"{js_escaped}"])</script>'


def _sample_product_raw(
    *,
    product_id: int = 12345,
    name: str = "LEGO Star Wars 75192 Millennium Falcon",
    sku: str = "75192",
    price: str = "3199.9",
    total_qty: int = 5,
    total_sold: int = 10,
    product_status: str = "available",
    url_handle: str = "lego-star-wars-75192-millennium-falcon",
    is_special_price: bool = False,
    min_price: float | None = None,
    min_ori_price: float | None = None,
    rating: str = "4.50",
    rating_count: int = 12,
    images: list[dict] | None = None,
) -> dict:
    actual_min_price = min_price if min_price is not None else float(price)
    actual_min_ori_price = min_ori_price if min_ori_price is not None else float(price)
    return {
        "id": product_id,
        "store_id": 6067,
        "parent_id": 0,
        "item_id": 99999,
        "type": "product",
        "name": name,
        "sku": sku,
        "taxable": 0,
        "brand_id": 14985,
        "product_status": product_status,
        "total_sold": total_sold,
        "set_allocated_stock": "no",
        "price": price,
        "quantity": total_qty,
        "images": images if images is not None else [
            {"x420_url": "https://cdn1.sgliteasset.com/test_420x420.jpg"},
        ],
        "product_label_status": True,
        "seo": {"url_handle": url_handle},
        "brands": {"id": 14985, "name": "LEGO"},
        "add_on_main_product": [],
        "product_labels": None,
        "vouchers": [],
        "point_redemption_promotion_products": None,
        "converted_price": price,
        "rating": rating,
        "rating_count": rating_count,
        "atomeMessage": False,
        "isSpecialPrice": is_special_price,
        "maxPrice": 0,
        "minPrice": actual_min_price,
        "maxOriPrice": 0,
        "minOriPrice": actual_min_ori_price,
        "totalQty": total_qty,
        "seoData": {"url_handle": url_handle},
        "product_subscription": None,
    }


# ---------------------------------------------------------------------------
# Parser: Product parsing
# ---------------------------------------------------------------------------

class TestParseProductAvailability:
    """GIVEN a product dict from SiteGiant API, WHEN parsing availability."""

    def test_given_positive_qty_when_parsed_then_available(self) -> None:
        """GIVEN a product with totalQty=5, WHEN parsed, THEN available is True."""
        raw = _sample_product_raw(total_qty=5)
        product = _parse_product(raw)
        assert product is not None
        assert product.available is True
        assert product.quantity == 5

    def test_given_zero_qty_when_parsed_then_sold_out(self) -> None:
        """GIVEN a product with totalQty=0, WHEN parsed, THEN available is False."""
        raw = _sample_product_raw(total_qty=0)
        product = _parse_product(raw)
        assert product is not None
        assert product.available is False
        assert product.quantity == 0

    def test_given_null_status_zero_qty_when_parsed_then_sold_out(self) -> None:
        """GIVEN product_status=None and totalQty=0, WHEN parsed, THEN sold out."""
        raw = _sample_product_raw(total_qty=0, product_status=None)
        product = _parse_product(raw)
        assert product is not None
        assert product.available is False

    def test_given_available_status_zero_qty_when_parsed_then_sold_out(self) -> None:
        """GIVEN product_status='available' but totalQty=0, WHEN parsed, THEN sold out.
        (quantity is the source of truth, not status)
        """
        raw = _sample_product_raw(total_qty=0, product_status="available")
        product = _parse_product(raw)
        assert product is not None
        assert product.available is False


class TestParseProductPricing:
    """GIVEN product pricing data, WHEN parsing prices."""

    def test_given_regular_price_when_parsed_then_correct_myr(self) -> None:
        """GIVEN price=119.9, WHEN parsed, THEN price_myr='119.9'."""
        raw = _sample_product_raw(price="119.9")
        product = _parse_product(raw)
        assert product is not None
        assert product.price_myr == "119.9"

    def test_given_converted_price_when_parsed_then_uses_converted(self) -> None:
        """GIVEN converted_price differs from price, WHEN parsed, THEN uses converted_price."""
        raw = _sample_product_raw(price="119.9")
        raw["converted_price"] = "99.9"
        product = _parse_product(raw)
        assert product is not None
        assert product.price_myr == "99.9"

    def test_given_special_price_when_parsed_then_captures_original(self) -> None:
        """GIVEN isSpecialPrice=True with discount, WHEN parsed,
        THEN original_price_myr reflects pre-discount price.
        """
        raw = _sample_product_raw(
            price="191.04",
            is_special_price=True,
            min_price=191.04,
            min_ori_price=238.8,
        )
        product = _parse_product(raw)
        assert product is not None
        assert product.is_special_price is True
        assert product.original_price_myr == "238.8"
        assert product.price_myr == "191.04"

    def test_given_no_discount_when_parsed_then_no_original_price(self) -> None:
        """GIVEN isSpecialPrice=False, WHEN parsed, THEN original_price_myr is None."""
        raw = _sample_product_raw(is_special_price=False)
        product = _parse_product(raw)
        assert product is not None
        assert product.original_price_myr is None

    def test_given_special_price_same_as_original_when_parsed_then_no_original(self) -> None:
        """GIVEN isSpecialPrice=True but minPrice == minOriPrice,
        WHEN parsed, THEN no original_price (not actually discounted).
        """
        raw = _sample_product_raw(
            price="100.0",
            is_special_price=True,
            min_price=100.0,
            min_ori_price=100.0,
        )
        product = _parse_product(raw)
        assert product is not None
        assert product.original_price_myr is None


class TestParseProductMetadata:
    """GIVEN product metadata, WHEN parsing fields."""

    def test_given_full_product_when_parsed_then_all_fields_populated(self) -> None:
        """GIVEN a complete product dict, WHEN parsed, THEN all fields are correct."""
        raw = _sample_product_raw(
            product_id=6945906,
            name="LEGO Speed Champions 77259 Audi Revolut F1 Team R26 Race Car",
            sku="77259",
            price="119.9",
            total_qty=24,
            total_sold=14,
            url_handle="lego-speed-champions-77259-audi-revolut-f1-team-r26-race-car",
            rating="4.50",
            rating_count=12,
        )
        product = _parse_product(raw)
        assert product is not None
        assert product.product_id == 6945906
        assert product.sku == "77259"
        assert product.name == "LEGO Speed Champions 77259 Audi Revolut F1 Team R26 Race Car"
        assert product.total_sold == 14
        assert product.rating == "4.50"
        assert product.rating_count == 12
        assert product.url == (
            "https://mightyutan.com.my/product/"
            "lego-speed-champions-77259-audi-revolut-f1-team-r26-race-car"
        )
        assert product.image_url == "https://cdn1.sgliteasset.com/test_420x420.jpg"

    def test_given_empty_images_when_parsed_then_empty_image_url(self) -> None:
        """GIVEN images=[], WHEN parsed, THEN image_url is empty string."""
        raw = _sample_product_raw(images=[])
        product = _parse_product(raw)
        assert product is not None
        assert product.image_url == ""

    def test_given_multiple_images_when_parsed_then_uses_first(self) -> None:
        """GIVEN multiple images, WHEN parsed, THEN uses the first one."""
        raw = _sample_product_raw(images=[
            {"x420_url": "https://cdn1.sgliteasset.com/first.jpg"},
            {"x420_url": "https://cdn1.sgliteasset.com/second.jpg"},
        ])
        product = _parse_product(raw)
        assert product is not None
        assert product.image_url == "https://cdn1.sgliteasset.com/first.jpg"

    def test_given_none_total_sold_when_parsed_then_zero(self) -> None:
        """GIVEN total_sold=None (new product), WHEN parsed, THEN total_sold=0."""
        raw = _sample_product_raw()
        raw["total_sold"] = None
        product = _parse_product(raw)
        assert product is not None
        assert product.total_sold == 0

    def test_given_none_rating_when_parsed_then_none(self) -> None:
        """GIVEN rating=None, WHEN parsed, THEN rating is None."""
        raw = _sample_product_raw()
        raw["rating"] = None
        product = _parse_product(raw)
        assert product is not None
        assert product.rating is None

    def test_given_missing_seo_when_parsed_then_empty_url(self) -> None:
        """GIVEN no seo or seoData, WHEN parsed, THEN url is empty."""
        raw = _sample_product_raw()
        raw["seo"] = None
        raw["seoData"] = None
        product = _parse_product(raw)
        assert product is not None
        assert product.url == ""


class TestParseProductEdgeCases:
    """GIVEN edge-case product data, WHEN parsing."""

    def test_given_empty_name_when_parsed_then_returns_none(self) -> None:
        """GIVEN name='', WHEN parsed, THEN returns None (skipped)."""
        raw = _sample_product_raw()
        raw["name"] = ""
        assert _parse_product(raw) is None

    def test_given_none_name_when_parsed_then_returns_none(self) -> None:
        """GIVEN name=None, WHEN parsed, THEN returns None (skipped)."""
        raw = _sample_product_raw()
        raw["name"] = None
        assert _parse_product(raw) is None

    def test_given_missing_name_key_when_parsed_then_returns_none(self) -> None:
        """GIVEN 'name' key missing, WHEN parsed, THEN returns None."""
        raw = _sample_product_raw()
        del raw["name"]
        assert _parse_product(raw) is None

    def test_given_none_totalqty_when_parsed_then_zero_qty(self) -> None:
        """GIVEN totalQty=None, WHEN parsed, THEN quantity=0, available=False."""
        raw = _sample_product_raw()
        raw["totalQty"] = None
        product = _parse_product(raw)
        assert product is not None
        assert product.quantity == 0
        assert product.available is False

    def test_product_is_frozen_dataclass(self) -> None:
        """GIVEN a parsed product, WHEN trying to mutate, THEN raises error."""
        raw = _sample_product_raw()
        product = _parse_product(raw)
        assert product is not None
        with pytest.raises(AttributeError):
            product.name = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Parser: JSON brace matching
# ---------------------------------------------------------------------------

class TestFindMatchingBrace:
    """GIVEN a JSON string, WHEN finding matching braces."""

    def test_given_simple_object_when_matched_then_correct_end(self) -> None:
        text = '{"key": "value"}'
        assert _find_matching_brace(text, 0) == len(text)

    def test_given_nested_objects_when_matched_then_correct_end(self) -> None:
        text = '{"a": {"b": {"c": 1}}}'
        assert _find_matching_brace(text, 0) == len(text)

    def test_given_braces_inside_strings_when_matched_then_ignored(self) -> None:
        text = '{"a": "hello {world} }"}'
        assert _find_matching_brace(text, 0) == len(text)

    def test_given_escaped_quotes_when_matched_then_handled(self) -> None:
        text = '{"a": "he said \\"hi\\"", "b": 1}'
        assert _find_matching_brace(text, 0) == len(text)

    def test_given_unclosed_brace_when_matched_then_returns_zero(self) -> None:
        assert _find_matching_brace("{", 0) == 0

    def test_given_empty_object_when_matched_then_correct(self) -> None:
        assert _find_matching_brace("{}", 0) == 2

    def test_given_offset_when_matched_then_starts_at_offset(self) -> None:
        text = 'prefix{"key": 1}'
        assert _find_matching_brace(text, 6) == len(text)


# ---------------------------------------------------------------------------
# Parser: Full page parsing (RSC extraction + pagination)
# ---------------------------------------------------------------------------

class TestParsePagePagination:
    """GIVEN an HTML page with RSC data, WHEN parsing pagination."""

    def test_given_page_1_when_parsed_then_correct_pagination(self) -> None:
        """GIVEN page 1 of 15 with 100 products, WHEN parsed,
        THEN pagination shows total=1403, last_page=15.
        """
        data = {
            "current_page": 1,
            "last_page": 15,
            "total": 1403,
            "per_page": 100,
            "data": [_sample_product_raw(name=f"Product {i}", sku=str(i)) for i in range(3)],
        }
        html = _build_rsc_html(data)
        products, info = parse_page(html)

        assert info is not None
        assert info.current_page == 1
        assert info.last_page == 15
        assert info.total == 1403
        assert info.per_page == 100
        assert len(products) == 3

    def test_given_last_page_when_parsed_then_fewer_products(self) -> None:
        """GIVEN the last page with only 3 products, WHEN parsed,
        THEN returns 3 products with correct pagination.
        """
        data = {
            "current_page": 15,
            "last_page": 15,
            "total": 1403,
            "per_page": 100,
            "data": [
                _sample_product_raw(name="Product A", sku="111"),
                _sample_product_raw(name="Product B", sku="222"),
                _sample_product_raw(name="Product C", sku="333"),
            ],
        }
        html = _build_rsc_html(data)
        products, info = parse_page(html)

        assert info is not None
        assert info.current_page == 15
        assert len(products) == 3

    def test_given_empty_page_when_parsed_then_zero_products(self) -> None:
        """GIVEN a page beyond the last page, WHEN parsed, THEN 0 products."""
        data = {
            "current_page": 16,
            "last_page": 15,
            "total": 1403,
            "per_page": 100,
            "data": [],
        }
        html = _build_rsc_html(data)
        products, info = parse_page(html)

        assert info is not None
        assert len(products) == 0


class TestParsePageMixedAvailability:
    """GIVEN a page with mixed available and sold-out products."""

    def test_given_mixed_stock_when_parsed_then_both_included(self) -> None:
        """GIVEN 2 in-stock and 2 sold-out products, WHEN parsed,
        THEN all 4 are returned with correct availability.
        """
        data = {
            "current_page": 11,
            "last_page": 15,
            "total": 1403,
            "per_page": 100,
            "data": [
                _sample_product_raw(name="Available A", sku="1", total_qty=10),
                _sample_product_raw(name="Sold Out B", sku="2", total_qty=0),
                _sample_product_raw(name="Available C", sku="3", total_qty=3),
                _sample_product_raw(name="Sold Out D", sku="4", total_qty=0),
            ],
        }
        html = _build_rsc_html(data)
        products, _ = parse_page(html)

        assert len(products) == 4
        available = [p for p in products if p.available]
        sold_out = [p for p in products if not p.available]
        assert len(available) == 2
        assert len(sold_out) == 2
        assert {p.name for p in available} == {"Available A", "Available C"}
        assert {p.name for p in sold_out} == {"Sold Out B", "Sold Out D"}

    def test_given_all_sold_out_page_when_parsed_then_all_unavailable(self) -> None:
        """GIVEN a page where all products have qty=0 (like page 12+),
        WHEN parsed, THEN all products are marked unavailable.
        """
        data = {
            "current_page": 12,
            "last_page": 15,
            "total": 1403,
            "per_page": 100,
            "data": [
                _sample_product_raw(name=f"Sold Out {i}", sku=str(i), total_qty=0)
                for i in range(5)
            ],
        }
        html = _build_rsc_html(data)
        products, _ = parse_page(html)

        assert len(products) == 5
        assert all(not p.available for p in products)


class TestParsePageEdgeCases:
    """GIVEN edge-case HTML input, WHEN parsing."""

    def test_given_no_rsc_data_when_parsed_then_empty(self) -> None:
        """GIVEN plain HTML without RSC push blocks, WHEN parsed,
        THEN returns empty tuple and None pagination.
        """
        products, info = parse_page("<html><body>Hello</body></html>")
        assert products == ()
        assert info is None

    def test_given_rsc_without_pagination_when_parsed_then_empty(self) -> None:
        """GIVEN RSC push blocks that don't contain productListingPagination,
        WHEN parsed, THEN returns empty.
        """
        html = '<script>self.__next_f.push([1,"some other data"])</script>'
        products, info = parse_page(html)
        assert products == ()
        assert info is None

    def test_given_malformed_json_in_rsc_when_parsed_then_empty(self) -> None:
        """GIVEN corrupt JSON in the RSC payload, WHEN parsed,
        THEN returns empty gracefully (no exception).
        """
        html = '<script>self.__next_f.push([1,"productListingPagination{broken"])</script>'
        products, info = parse_page(html)
        assert products == ()
        assert info is None

    def test_given_product_with_invalid_fields_when_parsed_then_skipped(self) -> None:
        """GIVEN one valid and one invalid product, WHEN parsed,
        THEN only valid product is returned.
        """
        data = {
            "current_page": 1,
            "last_page": 1,
            "total": 2,
            "per_page": 100,
            "data": [
                _sample_product_raw(name="Valid Product", sku="111"),
                {"id": 999, "name": "", "sku": "bad"},  # invalid: empty name
            ],
        }
        html = _build_rsc_html(data)
        products, _ = parse_page(html)
        assert len(products) == 1
        assert products[0].name == "Valid Product"


class TestParsePageSpecialPricing:
    """GIVEN products with various pricing scenarios on a page."""

    def test_given_discounted_products_when_parsed_then_captures_both_prices(self) -> None:
        """GIVEN a product on sale, WHEN parsed,
        THEN price_myr is the sale price and original_price_myr is the pre-sale price.
        """
        data = {
            "current_page": 1,
            "last_page": 1,
            "total": 1,
            "per_page": 100,
            "data": [
                _sample_product_raw(
                    name="LEGO City 60400 Go-Karts",
                    sku="60400",
                    price="35.9",
                    is_special_price=True,
                    min_price=35.9,
                    min_ori_price=44.9,
                ),
            ],
        }
        html = _build_rsc_html(data)
        products, _ = parse_page(html)

        assert len(products) == 1
        assert products[0].price_myr == "35.9"
        assert products[0].original_price_myr == "44.9"
        assert products[0].is_special_price is True
