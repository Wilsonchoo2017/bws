"""GWT tests for the ToysRUs scrape pipeline.

Covers: parser availability detection, scraper pagination,
repository availability gate, and end-to-end data flow.
"""

import pytest

from db.connection import get_connection
from db.schema import init_schema
from services.items.repository import get_all_items
from services.items.set_number import extract_set_number
from services.toysrus.parser import ToysRUsProduct, parse_products
from services.toysrus.repository import upsert_product, upsert_products


@pytest.fixture
def conn():
    """Connection with schema initialized."""
    connection = get_connection()
    init_schema(connection)
    yield connection


def _make_product(
    sku: str = "10057384",
    name: str = "LEGO Minecraft The Parrot Houses 21282",
    price_myr: str = "339.90",
    available: bool = True,
    **overrides,
) -> ToysRUsProduct:
    defaults = {
        "sku": sku,
        "name": name,
        "price_myr": price_myr,
        "brand": "lego",
        "category": "building_blocks_lego_my",
        "age_range": "8_11yrs",
        "url": f"https://www.toysrus.com.my/lego-{sku}.html",
        "image_url": f"https://www.toysrus.com.my/dw/image/{sku}.jpg",
        "available": available,
        "original_price_myr": None,
    }
    return ToysRUsProduct(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Parser: availability detection
# ---------------------------------------------------------------------------

TILE_INSTOCK = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-metadata='{"id":"1","name":"LEGO City 60411","price":"49.90","sku":"SKU001","brand":"lego","category":"lego","akeneo_ageRangeYears":"6yrs","quantity":1}'
>
<a href="/lego-60411.html" data-gtm-product-link>
<img data-src="https://www.toysrus.com.my/dw/image/v2/test/60411.jpg">
<div class="status">instock</div>
"""

TILE_UNAVAILABLE_STATUS = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-metadata='{"id":"2","name":"LEGO Star Wars 75403","price":"199.90","sku":"SKU002","brand":"lego","category":"lego","akeneo_ageRangeYears":"9yrs","quantity":0}'
>
<a href="/lego-75403.html" data-gtm-product-link>
<img data-src="https://www.toysrus.com.my/dw/image/v2/test/75403.jpg">
<div class="status">unavailable</div>
"""

TILE_OUT_OF_STOCK_CLASS = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-metadata='{"id":"3","name":"LEGO Technic 42151","price":"89.90","sku":"SKU003","brand":"lego","category":"lego","akeneo_ageRangeYears":"10yrs","quantity":0}'
>
<a href="/lego-42151.html" data-gtm-product-link>
<img data-src="https://www.toysrus.com.my/dw/image/v2/test/42151.jpg">
<div class="availability out-of-stock">
"""

TILE_ADD_TO_CART = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-metadata='{"id":"4","name":"LEGO Icons 10497","price":"549.90","sku":"SKU004","brand":"lego","category":"lego","akeneo_ageRangeYears":"18yrs","quantity":1}'
>
<a href="/lego-10497.html" data-gtm-product-link>
<img data-src="https://www.toysrus.com.my/dw/image/v2/test/10497.jpg">
<button class="add-to-cart btn">Add to Cart</button>
"""

TILE_NO_SIGNALS = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-metadata='{"id":"5","name":"LEGO Friends 42620","price":"129.90","sku":"SKU005","brand":"lego","category":"lego","akeneo_ageRangeYears":"6yrs","quantity":1}'
>
<a href="/lego-42620.html" data-gtm-product-link>
<img data-src="https://www.toysrus.com.my/dw/image/v2/test/42620.jpg">
"""

# Matches real TRU AJAX HTML: available tiles have NO status div, no out-of-stock,
# no add-to-cart — just metadata + price + image.
TILE_REAL_AVAILABLE = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-pid="10023004"
    data-metadata='{"id":"27311","name":"LEGO Speed Champions BMW M4 GT3 76922","price":"229.90","sku":"10023004","brand":"lego_speed_champions, lego","category":"building_blocks_lego_my","akeneo_ageRangeYears":"5_7yrs,8_11yrs","quantity":1}'
>
<div class="card-image-wrapper">
    <a href="/lego-76922.html" class="card-image-container" data-gtm-product-link>
        <img class="tile-image card-image lazyload"
            data-src="https://www.toysrus.com.my/dw/image/v2/BDGJ_PRD/on/demandware.static/-/Sites-master-catalog-toysrus/default/dw8c099a86/76922.jpg?sw=394&sh=394&q=75"
            alt="LEGO Speed Champions BMW M4 GT3 76922" />
    </a>
</div>
<div class="price" itemprop="offers">
    <span class="price-items">
        <span class="sales" itemprop="price">
            <span class="value" content="229.90">RM229.90</span>
        </span>
    </span>
</div>
"""

# Real TRU AJAX HTML for unavailable: has out-of-stock markers
TILE_REAL_UNAVAILABLE = """
class="col-6 col-md-4 col-lg-3 product-tile-wrapper"
<div class="card product-tile product-data product"
    data-pid="10085000"
    data-metadata='{"id":"99999","name":"LEGO Harry Potter Malfoy Manor 76453","price":"499.90","sku":"10085000","brand":"lego","category":"building_blocks_lego_my","akeneo_ageRangeYears":"8_11yrs","quantity":1}'
>
<div class="card-image-wrapper">
    <a href="/lego-76453.html" class="card-image-container" data-gtm-product-link>
        <img class="tile-image card-image lazyload"
            data-src="https://www.toysrus.com.my/dw/image/v2/BDGJ_PRD/on/demandware.static/-/Sites-master-catalog-toysrus/default/test/76453.jpg?sw=394&sh=394&q=75"
            alt="LEGO Harry Potter Malfoy Manor 76453" />
    </a>
</div>
<div class="status">unavailable</div>
<div class="availability out-of-stock">
    <span>Out of Stock</span>
</div>
"""


class TestParserAvailability:
    """Given product tiles with various availability signals,
    verify the parser correctly detects availability."""

    def test_given_instock_status_when_parsed_then_available(self):
        """Given a tile with status 'instock', when parsed,
        then the product is marked available."""
        products = parse_products(TILE_INSTOCK)
        assert len(products) == 1
        assert products[0].available is True

    def test_given_unavailable_status_when_parsed_then_not_available(self):
        """Given a tile with status 'unavailable', when parsed,
        then the product is marked not available."""
        products = parse_products(TILE_UNAVAILABLE_STATUS)
        assert len(products) == 1
        assert products[0].available is False

    def test_given_out_of_stock_class_when_parsed_then_not_available(self):
        """Given a tile with CSS class 'out-of-stock', when parsed,
        then the product is marked not available."""
        products = parse_products(TILE_OUT_OF_STOCK_CLASS)
        assert len(products) == 1
        assert products[0].available is False

    def test_given_add_to_cart_button_when_parsed_then_available(self):
        """Given a tile with no status div but an 'add-to-cart' button,
        when parsed, then the product is marked available."""
        products = parse_products(TILE_ADD_TO_CART)
        assert len(products) == 1
        assert products[0].available is True

    def test_given_no_availability_signals_when_parsed_then_available(self):
        """Given a tile with no status div, no out-of-stock class, and no
        add-to-cart button, when parsed, then the product defaults to
        available (matches real TRU AJAX behaviour)."""
        products = parse_products(TILE_NO_SIGNALS)
        assert len(products) == 1
        assert products[0].available is True

    def test_given_real_available_tile_when_parsed_then_available(self):
        """Given a real TRU AJAX tile for an available product (no status
        div, no out-of-stock markers), when parsed, then it is available."""
        products = parse_products(TILE_REAL_AVAILABLE)
        assert len(products) == 1
        assert products[0].available is True
        assert products[0].sku == "10023004"

    def test_given_real_unavailable_tile_when_parsed_then_not_available(self):
        """Given a real TRU AJAX tile for an unavailable product (has
        status=unavailable and out-of-stock class), when parsed,
        then it is not available."""
        products = parse_products(TILE_REAL_UNAVAILABLE)
        assert len(products) == 1
        assert products[0].available is False

    def test_given_mixed_tiles_when_parsed_then_correct_counts(self):
        """Given a page with both available and unavailable tiles,
        when parsed, then all products are returned (not filtered)."""
        html = TILE_REAL_AVAILABLE + TILE_UNAVAILABLE_STATUS + TILE_REAL_UNAVAILABLE
        products = parse_products(html)
        assert len(products) == 3
        available = [p for p in products if p.available]
        assert len(available) == 1


# ---------------------------------------------------------------------------
# Set number extraction
# ---------------------------------------------------------------------------


class TestSetNumberExtraction:
    """Given product names, verify set number extraction."""

    def test_given_name_with_set_number_when_extracted_then_returns_number(self):
        assert extract_set_number("LEGO Minecraft The Parrot Houses 21282") == "21282"

    def test_given_name_with_set_at_start_when_extracted_then_returns_number(self):
        assert extract_set_number("LEGO 42151 Technic Bugatti Bolide") == "42151"

    def test_given_name_without_set_number_when_extracted_then_returns_none(self):
        assert extract_set_number("LEGO General Toy Pack") is None

    def test_given_name_with_year_only_when_extracted_then_returns_none(self):
        assert extract_set_number("LEGO Collection 2024 Edition") is None

    def test_given_name_with_piece_count_when_extracted_then_skips_pieces(self):
        assert extract_set_number("LEGO Star Wars 75192 Millennium Falcon (7541 Pcs)") == "75192"


# ---------------------------------------------------------------------------
# Repository: availability gate
# ---------------------------------------------------------------------------


class TestRepositoryAvailabilityGate:
    """Given products with different availability states,
    verify only available ones with set numbers reach lego_items."""

    def test_given_available_product_with_set_number_when_upserted_then_in_lego_items(self, conn):
        """Given an available product with an extractable set number,
        when upserted, then it appears in lego_items and get_all_items."""
        product = _make_product(available=True)
        upsert_product(conn, product)

        items = get_all_items(conn)
        set_numbers = [i["set_number"] for i in items]
        assert "21282" in set_numbers

    def test_given_unavailable_product_when_upserted_then_not_in_lego_items(self, conn):
        """Given an unavailable product, when upserted,
        then it is stored in toysrus_products but NOT in lego_items."""
        product = _make_product(available=False)
        upsert_product(conn, product)

        # In toysrus_products
        row = conn.execute(
            "SELECT available FROM toysrus_products WHERE sku = ?", [product.sku]
        ).fetchone()
        assert row is not None
        assert row[0] is False

        # Not in lego_items
        items = get_all_items(conn)
        assert len(items) == 0

    def test_given_product_without_set_number_when_upserted_then_not_in_lego_items(self, conn):
        """Given an available product whose name has no extractable set number,
        when upserted, then it is stored in toysrus_products but NOT in lego_items."""
        product = _make_product(name="LEGO General Toy Pack", available=True)
        upsert_product(conn, product)

        row = conn.execute(
            "SELECT id FROM toysrus_products WHERE sku = ?", [product.sku]
        ).fetchone()
        assert row is not None

        items = get_all_items(conn)
        assert len(items) == 0

    def test_given_unavailable_product_when_upserted_then_price_history_recorded(self, conn):
        """Given an unavailable product, when upserted,
        then price history is still recorded in toysrus_price_history."""
        product = _make_product(available=False)
        upsert_product(conn, product)

        rows = conn.execute(
            "SELECT available FROM toysrus_price_history WHERE sku = ?", [product.sku]
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is False


# ---------------------------------------------------------------------------
# Full pipeline: scraper collects all, repository filters
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """Given a mix of available and unavailable products,
    verify the full pipeline stores all but only surfaces available ones."""

    def test_given_mixed_products_when_bulk_upserted_then_all_stored_in_toysrus(self, conn):
        """Given a mix of available/unavailable products, when bulk upserted,
        then ALL are stored in toysrus_products."""
        products = (
            _make_product(sku="A1", name="LEGO Set 10001", available=True),
            _make_product(sku="A2", name="LEGO Set 10002", available=False),
            _make_product(sku="A3", name="LEGO Set 10003", available=True),
        )
        count = upsert_products(conn, products)

        assert count == 3
        total = conn.execute("SELECT count(*) FROM toysrus_products").fetchone()[0]
        assert total == 3

    def test_given_mixed_products_when_bulk_upserted_then_only_available_in_items(self, conn):
        """Given a mix of available/unavailable products, when bulk upserted,
        then only available ones with set numbers appear in get_all_items."""
        products = (
            _make_product(sku="B1", name="LEGO City 60411", available=True),
            _make_product(sku="B2", name="LEGO Star Wars 75403", available=False),
            _make_product(sku="B3", name="LEGO Technic 42151", available=True),
        )
        upsert_products(conn, products)

        items = get_all_items(conn)
        set_numbers = {i["set_number"] for i in items}
        assert "60411" in set_numbers
        assert "42151" in set_numbers
        assert "75403" not in set_numbers

    def test_given_mixed_products_when_bulk_upserted_then_all_have_price_history(self, conn):
        """Given a mix of available/unavailable products, when bulk upserted,
        then ALL have toysrus_price_history entries."""
        products = (
            _make_product(sku="C1", name="LEGO Set 10001", available=True),
            _make_product(sku="C2", name="LEGO Set 10002", available=False),
        )
        upsert_products(conn, products)

        total = conn.execute("SELECT count(*) FROM toysrus_price_history").fetchone()[0]
        assert total == 2

    def test_given_product_becomes_available_when_re_upserted_then_added_to_items(self, conn):
        """Given an unavailable product that later becomes available,
        when re-upserted, then it appears in lego_items."""
        product_v1 = _make_product(sku="D1", name="LEGO City 60411", available=False)
        upsert_product(conn, product_v1)
        assert len(get_all_items(conn)) == 0

        product_v2 = _make_product(sku="D1", name="LEGO City 60411", available=True)
        upsert_product(conn, product_v2)

        items = get_all_items(conn)
        assert len(items) == 1
        assert items[0]["set_number"] == "60411"

    def test_given_available_products_when_upserted_then_toysrus_price_in_items(self, conn):
        """Given available products, when upserted, then get_all_items
        includes toysrus_price_cents."""
        product = _make_product(sku="E1", name="LEGO City 60411", price_myr="49.90", available=True)
        upsert_product(conn, product)

        items = get_all_items(conn)
        assert len(items) == 1
        assert items[0]["toysrus_price_cents"] == 4990
