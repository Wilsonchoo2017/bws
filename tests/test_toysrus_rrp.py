"""GWT tests for ToysRUs RRP pipeline — parser, repository, and list query."""

import pytest

from db.connection import get_connection
from db.schema import init_schema
from services.items.repository import get_all_items, get_item_detail, get_or_create_item
from services.toysrus.parser import ToysRUsProduct, parse_products


@pytest.fixture
def conn():
    """Connection with schema initialized."""
    connection = get_connection()
    init_schema(connection)
    yield connection


# --- Sample HTML fragments for parser tests ---

TILE_NO_DISCOUNT = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-metadata='{"id":"58944","name":"LEGO Minecraft The Parrot Houses 21282","price":"339.90","sku":"10057384","brand":"lego","category":"building_blocks_lego_my","akeneo_ageRangeYears":"8_11yrs","quantity":1}'
>
<a href="/lego-minecraft-21282.html" data-gtm-product-link>
<img data-src="https://www.toysrus.com.my/dw/image/v2/test/21282.jpg">
<div class="status">instock</div>
<div class="price">
    <span class="price-items">
        <span class="sales" itemprop="price">
            <span class="value" content="339.90">RM339.90</span>
        </span>
    </span>
</div>
"""

TILE_WITH_DISCOUNT = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-metadata='{"id":"935163","name":"Jurassic World Wild Roar 76946","price":"99.50","sku":"10085879","brand":"jurassicworld","category":"action_figures","akeneo_ageRangeYears":"5_7yrs","quantity":1}'
>
<a href="/jurassic-world-76946.html" data-gtm-product-link>
<img data-src="https://www.toysrus.com.my/dw/image/v2/test/76946.jpg">
<div class="status">instock</div>
<div class="price">
    <span class="price-items">
        <del class="old">
            <span class="strike-through list">
                <span class="value" content="129.90">RM129.90</span>
            </span>
        </del>
        <span class="sales" itemprop="price">
            <span class="value" content="99.50">RM99.50</span>
        </span>
    </span>
</div>
"""


class TestParserOriginalPrice:
    """Given ToysRUs HTML tiles, verify original price extraction."""

    def test_given_tile_without_discount_when_parsed_then_original_price_is_none(self):
        """Given a tile with no strike-through price, when parsed,
        then original_price_myr is None."""
        products = parse_products(TILE_NO_DISCOUNT)
        assert len(products) == 1
        assert products[0].price_myr == "339.90"
        assert products[0].original_price_myr is None

    def test_given_tile_with_discount_when_parsed_then_original_price_captured(self):
        """Given a tile with a strike-through original price, when parsed,
        then original_price_myr contains the undiscounted price."""
        products = parse_products(TILE_WITH_DISCOUNT)
        assert len(products) == 1
        assert products[0].price_myr == "99.50"
        assert products[0].original_price_myr == "129.90"

    def test_given_tile_with_discount_when_parsed_then_sale_price_in_metadata(self):
        """Given a discounted tile, when parsed, then price_myr is the sale price
        (from metadata), not the original."""
        products = parse_products(TILE_WITH_DISCOUNT)
        # metadata has "price":"99.50" which is the sale price
        assert products[0].price_myr == "99.50"
        # original is the higher undiscounted price
        assert float(products[0].original_price_myr) > float(products[0].price_myr)


class TestRrpStorage:
    """Given ToysRUs products, verify RRP is stored correctly on lego_items."""

    def test_given_product_without_discount_when_upserted_then_rrp_is_regular_price(self, conn):
        """Given a non-discounted product, when upserted via repository,
        then rrp_cents equals the regular price."""
        from services.toysrus.repository import _parse_myr_cents, upsert_product

        product = ToysRUsProduct(
            sku="10057384",
            name="LEGO Minecraft The Parrot Houses 21282",
            price_myr="339.90",
            brand="lego",
            category="building_blocks_lego_my",
            age_range="8_11yrs",
            url="https://www.toysrus.com.my/lego-21282.html",
            image_url="https://www.toysrus.com.my/dw/image/21282.jpg",
            available=True,
            original_price_myr=None,
        )
        upsert_product(conn, product)

        item = get_item_detail(conn, "21282")
        assert item is not None
        assert item["rrp_cents"] == 33990
        assert item["rrp_currency"] == "MYR"

    def test_given_product_with_discount_when_upserted_then_rrp_is_original_price(self, conn):
        """Given a discounted product, when upserted via repository,
        then rrp_cents is the original (undiscounted) price, not the sale price."""
        from services.toysrus.repository import upsert_product

        product = ToysRUsProduct(
            sku="10085879",
            name="Jurassic World Wild Roar 76946",
            price_myr="99.50",
            brand="jurassicworld",
            category="action_figures",
            age_range="5_7yrs",
            url="https://www.toysrus.com.my/jurassic-76946.html",
            image_url="https://www.toysrus.com.my/dw/image/76946.jpg",
            available=True,
            original_price_myr="129.90",
        )
        upsert_product(conn, product)

        item = get_item_detail(conn, "76946")
        assert item is not None
        # RRP should be the original undiscounted price
        assert item["rrp_cents"] == 12990
        assert item["rrp_currency"] == "MYR"

    def test_given_product_with_discount_when_upserted_then_sale_price_in_records(self, conn):
        """Given a discounted product, when upserted, then price_records
        contains the sale price (not the RRP)."""
        from services.toysrus.repository import upsert_product

        product = ToysRUsProduct(
            sku="10085879",
            name="Jurassic World Wild Roar 76946",
            price_myr="99.50",
            brand="jurassicworld",
            category="action_figures",
            age_range="5_7yrs",
            url="https://www.toysrus.com.my/jurassic-76946.html",
            image_url="https://www.toysrus.com.my/dw/image/76946.jpg",
            available=True,
            original_price_myr="129.90",
        )
        upsert_product(conn, product)

        detail = get_item_detail(conn, "76946")
        toysrus_prices = [p for p in detail["prices"] if p["source"] == "toysrus"]
        assert len(toysrus_prices) == 1
        # price_records should have the sale price, not RRP
        assert toysrus_prices[0]["price_cents"] == 9950


class TestRrpInListQuery:
    """Given items with RRP, verify get_all_items includes rrp_cents."""

    def test_given_item_with_rrp_when_listing_then_rrp_included(self, conn):
        """Given an item with rrp_cents set, when calling get_all_items,
        then rrp_cents is present in the result."""
        get_or_create_item(
            conn, "21282", title="LEGO Parrot Houses", rrp_cents=33990, rrp_currency="MYR"
        )

        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "21282")
        assert item["rrp_cents"] == 33990
        assert item["rrp_currency"] == "MYR"

    def test_given_item_without_rrp_when_listing_then_rrp_null(self, conn):
        """Given an item without rrp_cents, when calling get_all_items,
        then rrp_cents is None."""
        get_or_create_item(conn, "75192", title="Millennium Falcon")

        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "75192")
        assert item["rrp_cents"] is None

    def test_given_items_when_listing_then_rrp_columns_present(self, conn):
        """Given items exist, when calling get_all_items,
        then result dicts contain rrp_cents and rrp_currency keys."""
        get_or_create_item(conn, "21282", title="Test")

        items = get_all_items(conn)
        assert "rrp_cents" in items[0]
        assert "rrp_currency" in items[0]


class TestRrpListDetailConsistency:
    """Given an item with RRP, verify consistency between list and detail views."""

    def test_given_rrp_when_checking_both_views_then_consistent(self, conn):
        """Given an item with rrp_cents, when checking list vs detail,
        then RRP is visible in both."""
        get_or_create_item(
            conn, "21282", title="LEGO Parrot Houses", rrp_cents=33990, rrp_currency="MYR"
        )

        # List view
        items = get_all_items(conn)
        list_item = next(i for i in items if i["set_number"] == "21282")
        assert list_item["rrp_cents"] == 33990

        # Detail view
        detail = get_item_detail(conn, "21282")
        assert detail["rrp_cents"] == 33990
