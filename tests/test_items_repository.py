"""GWT tests for items repository — ensures all price sources appear in list query."""

import duckdb
import pytest

from db.schema import init_schema
from services.items.repository import (
    get_all_items,
    get_item_detail,
    get_or_create_item,
    record_price,
)


@pytest.fixture
def conn():
    """In-memory DuckDB connection with schema initialized."""
    connection = duckdb.connect(":memory:")
    init_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def item_with_toysrus_price(conn):
    """Create a lego item with a toysrus price record."""
    get_or_create_item(conn, "21282", title="LEGO Adidas Originals Superstar")
    record_price(
        conn,
        "21282",
        source="toysrus",
        price_cents=54990,
        currency="MYR",
        title="LEGO Adidas Originals Superstar",
        url="https://www.toysrus.com.my/lego-adidas.html",
    )
    return "21282"


@pytest.fixture
def item_with_shopee_price(conn):
    """Create a lego item with a shopee price record."""
    get_or_create_item(conn, "75192", title="Millennium Falcon")
    record_price(
        conn,
        "75192",
        source="shopee",
        price_cents=329900,
        currency="MYR",
        title="Millennium Falcon",
        url="https://shopee.com.my/product/123",
        shop_name="LEGO Shop MY",
    )
    return "75192"


@pytest.fixture
def item_with_mightyutan_price(conn):
    """Create a lego item with a mightyutan price record."""
    get_or_create_item(conn, "60400", title="LEGO City Go-Karts")
    record_price(
        conn,
        "60400",
        source="mightyutan",
        price_cents=4990,
        currency="MYR",
        title="LEGO City Go-Karts",
        url="https://mightyutan.com.my/product/60400",
    )
    return "60400"


class TestGetAllItemsPriceSources:
    """Given items with prices from different sources, verify get_all_items returns them."""

    def test_given_toysrus_price_when_listing_then_price_included(
        self, conn, item_with_toysrus_price
    ):
        """Given an item with a toysrus price, when calling get_all_items,
        then toysrus_price_cents is populated."""
        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "21282")
        assert item["toysrus_price_cents"] == 54990
        assert item["toysrus_currency"] == "MYR"
        assert item["toysrus_url"] == "https://www.toysrus.com.my/lego-adidas.html"

    def test_given_shopee_price_when_listing_then_price_included(
        self, conn, item_with_shopee_price
    ):
        """Given an item with a shopee price, when calling get_all_items,
        then shopee_price_cents is populated."""
        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "75192")
        assert item["shopee_price_cents"] == 329900
        assert item["shopee_currency"] == "MYR"

    def test_given_mightyutan_price_when_listing_then_price_included(
        self, conn, item_with_mightyutan_price
    ):
        """Given an item with a mightyutan price, when calling get_all_items,
        then mightyutan_price_cents is populated."""
        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "60400")
        assert item["mightyutan_price_cents"] == 4990
        assert item["mightyutan_currency"] == "MYR"
        assert item["mightyutan_url"] == "https://mightyutan.com.my/product/60400"

    def test_given_no_toysrus_price_when_listing_then_toysrus_null(
        self, conn, item_with_shopee_price
    ):
        """Given an item with only shopee price, when calling get_all_items,
        then toysrus fields are None."""
        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "75192")
        assert item["toysrus_price_cents"] is None
        assert item["toysrus_url"] is None

    def test_given_no_mightyutan_price_when_listing_then_mightyutan_null(
        self, conn, item_with_shopee_price
    ):
        """Given an item with only shopee price, when calling get_all_items,
        then mightyutan fields are None."""
        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "75192")
        assert item["mightyutan_price_cents"] is None
        assert item["mightyutan_url"] is None

    def test_given_item_with_all_retail_sources_when_listing_then_all_present(self, conn):
        """Given an item with shopee, toysrus, and mightyutan prices, when listing,
        then all three retail price columns are populated."""
        get_or_create_item(conn, "10300", title="DeLorean")
        record_price(conn, "10300", source="shopee", price_cents=89900, currency="MYR",
                     shop_name="Shop A")
        record_price(conn, "10300", source="toysrus", price_cents=79990, currency="MYR")
        record_price(conn, "10300", source="mightyutan", price_cents=84900, currency="MYR")

        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "10300")
        assert item["shopee_price_cents"] == 89900
        assert item["toysrus_price_cents"] == 79990
        assert item["mightyutan_price_cents"] == 84900


class TestShopeeBestPrice:
    """Given multiple Shopee shops selling the same set, verify cheapest is picked."""

    def test_given_two_shopee_shops_when_listing_then_cheapest_shown(self, conn):
        """Given two Shopee shops with different prices, when listing,
        then the cheapest price is selected."""
        get_or_create_item(conn, "42151", title="Bugatti Bolide")
        record_price(conn, "42151", source="shopee", price_cents=25900,
                     shop_name="Expensive Shop", url="https://shopee.com.my/exp")
        record_price(conn, "42151", source="shopee", price_cents=19900,
                     shop_name="Cheap Shop", url="https://shopee.com.my/cheap")

        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "42151")
        assert item["shopee_price_cents"] == 19900
        assert item["shopee_shop_name"] == "Cheap Shop"
        assert item["shopee_url"] == "https://shopee.com.my/cheap"

    def test_given_two_shopee_shops_when_listing_then_shop_count_correct(self, conn):
        """Given two Shopee shops, when listing, then shopee_shop_count is 2."""
        get_or_create_item(conn, "42151", title="Bugatti Bolide")
        record_price(conn, "42151", source="shopee", price_cents=25900,
                     shop_name="Shop A", url="https://shopee.com.my/a")
        record_price(conn, "42151", source="shopee", price_cents=19900,
                     shop_name="Shop B", url="https://shopee.com.my/b")

        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "42151")
        assert item["shopee_shop_count"] == 2

    def test_given_single_shopee_shop_when_listing_then_shop_count_one(
        self, conn, item_with_shopee_price
    ):
        """Given one Shopee shop, when listing, then shopee_shop_count is 1."""
        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "75192")
        assert item["shopee_shop_count"] == 1
        assert item["shopee_shop_name"] == "LEGO Shop MY"

    def test_given_no_shopee_when_listing_then_shop_count_zero(
        self, conn, item_with_toysrus_price
    ):
        """Given no Shopee prices, when listing, then shopee_shop_count is 0."""
        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "21282")
        assert item["shopee_shop_count"] == 0


class TestGetAllItemsColumnCompleteness:
    """Given the get_all_items query, verify all expected columns are present."""

    EXPECTED_COLUMNS = {
        "set_number", "title", "theme", "year_released", "year_retired",
        "retiring_soon", "watchlist", "image_url", "minifig_count", "dimensions",
        "rrp_cents", "rrp_currency", "updated_at",
        "shopee_price_cents", "shopee_currency", "shopee_url",
        "shopee_shop_name", "shopee_last_seen", "shopee_shop_count",
        "toysrus_price_cents", "toysrus_currency", "toysrus_url", "toysrus_last_seen",
        "mightyutan_price_cents", "mightyutan_currency", "mightyutan_url", "mightyutan_last_seen",
        "bricklink_new_cents", "bricklink_new_currency", "bricklink_new_last_seen",
        "bricklink_used_cents", "bricklink_used_currency", "bricklink_used_last_seen",
    }

    def test_given_items_when_listing_then_all_columns_present(
        self, conn, item_with_toysrus_price
    ):
        """Given items exist, when calling get_all_items,
        then result dicts contain all expected columns."""
        items = get_all_items(conn)
        assert len(items) > 0
        actual_columns = set(items[0].keys())
        assert actual_columns == self.EXPECTED_COLUMNS


class TestListDetailConsistency:
    """Given a price record, verify it appears in both list and detail views."""

    def test_given_toysrus_price_when_checking_both_views_then_consistent(
        self, conn, item_with_toysrus_price
    ):
        """Given a toysrus price record, when checking list vs detail,
        then the price is visible in both."""
        items = get_all_items(conn)
        list_item = next(i for i in items if i["set_number"] == "21282")
        assert list_item["toysrus_price_cents"] == 54990

        detail = get_item_detail(conn, "21282")
        toysrus_prices = [p for p in detail["prices"] if p["source"] == "toysrus"]
        assert len(toysrus_prices) == 1
        assert toysrus_prices[0]["price_cents"] == 54990

    def test_given_shopee_price_when_checking_both_views_then_consistent(
        self, conn, item_with_shopee_price
    ):
        """Given a shopee price record, when checking list vs detail,
        then the price is visible in both."""
        items = get_all_items(conn)
        list_item = next(i for i in items if i["set_number"] == "75192")
        assert list_item["shopee_price_cents"] == 329900

        detail = get_item_detail(conn, "75192")
        shopee_prices = [p for p in detail["prices"] if p["source"] == "shopee"]
        assert len(shopee_prices) == 1
        assert shopee_prices[0]["price_cents"] == 329900

    def test_given_mightyutan_price_when_checking_both_views_then_consistent(
        self, conn, item_with_mightyutan_price
    ):
        """Given a mightyutan price record, when checking list vs detail,
        then the price is visible in both."""
        items = get_all_items(conn)
        list_item = next(i for i in items if i["set_number"] == "60400")
        assert list_item["mightyutan_price_cents"] == 4990

        detail = get_item_detail(conn, "60400")
        mu_prices = [p for p in detail["prices"] if p["source"] == "mightyutan"]
        assert len(mu_prices) == 1
        assert mu_prices[0]["price_cents"] == 4990
