"""GWT tests for Mighty Utan repository.

Covers: upsert, price history, MYR cents parsing, unified lego_items
integration, and sold-out handling.
"""

import pytest

from db.connection import get_connection

from services.mightyutan.parser import MightyUtanProduct
from services.mightyutan.repository import (
    _parse_myr_cents,
    get_all_products,
    upsert_product,
    upsert_products,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    """Connection with schema initialized."""
    db = get_connection()
    db.execute("CREATE SEQUENCE IF NOT EXISTS mightyutan_products_id_seq")
    db.execute("CREATE SEQUENCE IF NOT EXISTS mightyutan_price_history_id_seq")
    db.execute("CREATE SEQUENCE IF NOT EXISTS lego_items_id_seq")
    db.execute("CREATE SEQUENCE IF NOT EXISTS price_records_id_seq")
    db.execute("""
        CREATE TABLE mightyutan_products (
            id INTEGER PRIMARY KEY,
            sku VARCHAR NOT NULL UNIQUE,
            name VARCHAR NOT NULL,
            price_myr VARCHAR,
            original_price_myr VARCHAR,
            url VARCHAR,
            image_url VARCHAR,
            available BOOLEAN DEFAULT TRUE,
            quantity INTEGER DEFAULT 0,
            total_sold INTEGER DEFAULT 0,
            rating VARCHAR,
            rating_count INTEGER DEFAULT 0,
            last_scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE mightyutan_price_history (
            id INTEGER PRIMARY KEY,
            sku VARCHAR NOT NULL,
            price_myr VARCHAR NOT NULL,
            available BOOLEAN DEFAULT TRUE,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE lego_items (
            id INTEGER PRIMARY KEY,
            set_number VARCHAR NOT NULL UNIQUE,
            title VARCHAR,
            theme VARCHAR,
            year_released INTEGER,
            year_retired INTEGER,
            parts_count INTEGER,
            weight VARCHAR,
            image_url VARCHAR,
            rrp_cents INTEGER,
            rrp_currency VARCHAR,
            retiring_soon BOOLEAN,
            minifig_count INTEGER,
            dimensions VARCHAR,
            release_date VARCHAR,
            retired_date VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE price_records (
            id INTEGER PRIMARY KEY,
            set_number VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            price_cents INTEGER NOT NULL,
            currency VARCHAR NOT NULL DEFAULT 'MYR',
            title VARCHAR,
            url VARCHAR,
            shop_name VARCHAR,
            condition VARCHAR,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    yield db


def _make_product(
    *,
    sku: str = "75192",
    name: str = "LEGO Star Wars 75192 Millennium Falcon",
    price_myr: str = "3199.9",
    url: str = "https://mightyutan.com.my/product/lego-star-wars-75192",
    image_url: str = "https://cdn1.sgliteasset.com/test.jpg",
    available: bool = True,
    quantity: int = 5,
    total_sold: int = 10,
    original_price_myr: str | None = None,
    is_special_price: bool = False,
    rating: str | None = "4.50",
    rating_count: int = 12,
) -> MightyUtanProduct:
    return MightyUtanProduct(
        product_id=12345,
        sku=sku,
        name=name,
        price_myr=price_myr,
        url=url,
        image_url=image_url,
        available=available,
        quantity=quantity,
        total_sold=total_sold,
        original_price_myr=original_price_myr,
        is_special_price=is_special_price,
        rating=rating,
        rating_count=rating_count,
    )


# ---------------------------------------------------------------------------
# MYR cents parsing
# ---------------------------------------------------------------------------

class TestParseMyrCents:
    """GIVEN a MYR price string, WHEN parsing to cents."""

    def test_given_standard_price_when_parsed_then_correct_cents(self) -> None:
        """GIVEN '119.9', WHEN parsed, THEN returns 11990."""
        assert _parse_myr_cents("119.9") == 11990

    def test_given_whole_number_when_parsed_then_correct_cents(self) -> None:
        """GIVEN '100', WHEN parsed, THEN returns 10000."""
        assert _parse_myr_cents("100") == 10000

    def test_given_two_decimals_when_parsed_then_correct_cents(self) -> None:
        """GIVEN '99.99', WHEN parsed, THEN returns 9999."""
        assert _parse_myr_cents("99.99") == 9999

    def test_given_comma_separator_when_parsed_then_handled(self) -> None:
        """GIVEN '1,299.90', WHEN parsed, THEN returns 129990."""
        assert _parse_myr_cents("1,299.90") == 129990

    def test_given_empty_string_when_parsed_then_returns_none(self) -> None:
        """GIVEN '', WHEN parsed, THEN returns None."""
        assert _parse_myr_cents("") is None

    def test_given_non_numeric_when_parsed_then_returns_none(self) -> None:
        """GIVEN 'abc', WHEN parsed, THEN returns None."""
        assert _parse_myr_cents("abc") is None

    def test_given_rm_prefix_when_parsed_then_extracts_number(self) -> None:
        """GIVEN 'RM 89.9', WHEN parsed, THEN returns 8990."""
        assert _parse_myr_cents("RM 89.9") == 8990


# ---------------------------------------------------------------------------
# Upsert: Insert
# ---------------------------------------------------------------------------

class TestUpsertProductInsert:
    """GIVEN a new product, WHEN upserting to empty table."""

    def test_given_new_product_when_upserted_then_inserted(self, conn) -> None:
        """GIVEN a product not in DB, WHEN upserted, THEN row is created."""
        product = _make_product()
        product_id = upsert_product(conn, product)

        assert product_id > 0
        row = conn.execute(
            "SELECT name, price_myr, available, quantity FROM mightyutan_products WHERE sku = ?",
            ["75192"],
        ).fetchone()
        assert row is not None
        assert row[0] == "LEGO Star Wars 75192 Millennium Falcon"
        assert row[1] == "3199.9"
        assert row[2] is True
        assert row[3] == 5

    def test_given_new_product_when_upserted_then_price_history_created(self, conn) -> None:
        """GIVEN a new product, WHEN upserted, THEN a price history record exists."""
        upsert_product(conn, _make_product())

        history = conn.execute(
            "SELECT sku, price_myr, available FROM mightyutan_price_history WHERE sku = ?",
            ["75192"],
        ).fetchall()
        assert len(history) == 1
        assert history[0][1] == "3199.9"
        assert history[0][2] is True

    def test_given_available_product_when_upserted_then_lego_item_created(self, conn) -> None:
        """GIVEN an available product with a set number, WHEN upserted,
        THEN a lego_items row and price_record are created.
        """
        upsert_product(conn, _make_product())

        item = conn.execute(
            "SELECT set_number, title FROM lego_items WHERE set_number = '75192'"
        ).fetchone()
        assert item is not None
        assert item[1] == "LEGO Star Wars 75192 Millennium Falcon"

        price = conn.execute(
            "SELECT source, price_cents, currency FROM price_records WHERE set_number = '75192'"
        ).fetchone()
        assert price is not None
        assert price[0] == "mightyutan"
        assert price[1] == 319990
        assert price[2] == "MYR"


# ---------------------------------------------------------------------------
# Upsert: Update
# ---------------------------------------------------------------------------

class TestUpsertProductUpdate:
    """GIVEN an existing product, WHEN upserting with new data."""

    def test_given_existing_product_when_price_changes_then_updated(self, conn) -> None:
        """GIVEN product already in DB at RM100, WHEN upserted at RM80,
        THEN price is updated and new history record added.
        """
        upsert_product(conn, _make_product(sku="111", name="Test 111", price_myr="100"))
        upsert_product(conn, _make_product(sku="111", name="Test 111", price_myr="80"))

        row = conn.execute(
            "SELECT price_myr FROM mightyutan_products WHERE sku = '111'"
        ).fetchone()
        assert row[0] == "80"

        history = conn.execute(
            "SELECT price_myr FROM mightyutan_price_history WHERE sku = '111' ORDER BY id"
        ).fetchall()
        assert len(history) == 2
        assert history[0][0] == "100"
        assert history[1][0] == "80"

    def test_given_existing_product_when_goes_sold_out_then_updated(self, conn) -> None:
        """GIVEN product in stock, WHEN upserted as sold out,
        THEN available=False and quantity=0.
        """
        upsert_product(conn, _make_product(sku="222", name="Test 222", quantity=10, available=True))
        upsert_product(conn, _make_product(sku="222", name="Test 222", quantity=0, available=False))

        row = conn.execute(
            "SELECT available, quantity FROM mightyutan_products WHERE sku = '222'"
        ).fetchone()
        assert row[0] is False
        assert row[1] == 0

    def test_given_existing_product_when_upserted_then_same_id(self, conn) -> None:
        """GIVEN product already exists, WHEN upserted again,
        THEN returns the same product ID (not a new one).
        """
        id1 = upsert_product(conn, _make_product(sku="333", name="Test 333"))
        id2 = upsert_product(conn, _make_product(sku="333", name="Test 333 Updated"))
        assert id1 == id2


# ---------------------------------------------------------------------------
# Upsert: Sold-out products and unified items
# ---------------------------------------------------------------------------

class TestUpsertSoldOutHandling:
    """GIVEN sold-out products, WHEN upserting."""

    def test_given_sold_out_product_when_upserted_then_no_lego_item(self, conn) -> None:
        """GIVEN a sold-out product, WHEN upserted,
        THEN no lego_items row is created (only available products go to unified catalog).
        """
        upsert_product(conn, _make_product(
            sku="60400", name="LEGO City 60400 Go-Karts", available=False, quantity=0,
        ))

        item = conn.execute(
            "SELECT 1 FROM lego_items WHERE set_number = '60400'"
        ).fetchone()
        assert item is None

    def test_given_sold_out_product_when_upserted_then_no_price_record(self, conn) -> None:
        """GIVEN a sold-out product, WHEN upserted,
        THEN no price_records row is created.
        """
        upsert_product(conn, _make_product(
            sku="60400", name="LEGO City 60400 Go-Karts", available=False, quantity=0,
        ))

        price = conn.execute(
            "SELECT 1 FROM price_records WHERE set_number = '60400'"
        ).fetchone()
        assert price is None

    def test_given_sold_out_product_when_upserted_then_price_history_still_recorded(self, conn) -> None:
        """GIVEN a sold-out product, WHEN upserted,
        THEN price history IS still recorded (for tracking).
        """
        upsert_product(conn, _make_product(
            sku="60400", name="LEGO City 60400 Go-Karts",
            available=False, quantity=0, price_myr="44.9",
        ))

        history = conn.execute(
            "SELECT price_myr, available FROM mightyutan_price_history WHERE sku = '60400'"
        ).fetchone()
        assert history is not None
        assert history[0] == "44.9"
        assert history[1] is False


# ---------------------------------------------------------------------------
# Upsert: RRP with discounts
# ---------------------------------------------------------------------------

class TestUpsertWithOriginalPrice:
    """GIVEN products with original (pre-discount) prices."""

    def test_given_discounted_product_when_upserted_then_rrp_uses_original(self, conn) -> None:
        """GIVEN original_price_myr=238.8 and price_myr=191.04,
        WHEN upserted, THEN lego_items.rrp_cents uses the original (238.8 = 23880).
        """
        upsert_product(conn, _make_product(
            sku="71050", name="LEGO Minifigures 71050 Spider-Man",
            price_myr="191.04", original_price_myr="238.8",
        ))

        row = conn.execute(
            "SELECT rrp_cents, rrp_currency FROM lego_items WHERE set_number = '71050'"
        ).fetchone()
        assert row is not None
        assert row[0] == 23880
        assert row[1] == "MYR"

    def test_given_no_discount_when_upserted_then_rrp_uses_price(self, conn) -> None:
        """GIVEN no original_price_myr, WHEN upserted,
        THEN rrp_cents uses the regular price.
        """
        upsert_product(conn, _make_product(
            sku="77259", name="LEGO Speed Champions 77259 Audi",
            price_myr="119.9",
        ))

        row = conn.execute(
            "SELECT rrp_cents FROM lego_items WHERE set_number = '77259'"
        ).fetchone()
        assert row is not None
        assert row[0] == 11990


# ---------------------------------------------------------------------------
# Bulk upsert
# ---------------------------------------------------------------------------

class TestBulkUpsert:
    """GIVEN multiple products, WHEN bulk upserting."""

    def test_given_multiple_products_when_bulk_upserted_then_all_saved(self, conn) -> None:
        """GIVEN 3 products, WHEN bulk upserted, THEN all 3 rows exist."""
        products = tuple(
            _make_product(sku=str(i), name=f"LEGO Test {i} Product")
            for i in range(100, 103)
        )
        count = upsert_products(conn, products)

        assert count == 3
        total = conn.execute("SELECT COUNT(*) FROM mightyutan_products").fetchone()[0]
        assert total == 3

    def test_given_empty_tuple_when_bulk_upserted_then_zero(self, conn) -> None:
        """GIVEN empty products tuple, WHEN bulk upserted, THEN returns 0."""
        assert upsert_products(conn, ()) == 0


# ---------------------------------------------------------------------------
# Get all products
# ---------------------------------------------------------------------------

class TestGetAllProducts:
    """GIVEN products in DB, WHEN querying."""

    def test_given_mixed_products_when_get_all_then_returns_all(self, conn) -> None:
        """GIVEN 2 available and 1 sold-out, WHEN get_all, THEN returns 3."""
        upsert_product(conn, _make_product(sku="1", name="A Product", available=True, quantity=5))
        upsert_product(conn, _make_product(sku="2", name="B Product", available=False, quantity=0))
        upsert_product(conn, _make_product(sku="3", name="C Product", available=True, quantity=3))

        results = get_all_products(conn)
        assert len(results) == 3

    def test_given_mixed_products_when_get_available_only_then_filters(self, conn) -> None:
        """GIVEN 2 available and 1 sold-out, WHEN get_all(available_only=True),
        THEN returns only 2.
        """
        upsert_product(conn, _make_product(sku="1", name="A Product", available=True, quantity=5))
        upsert_product(conn, _make_product(sku="2", name="B Product", available=False, quantity=0))
        upsert_product(conn, _make_product(sku="3", name="C Product", available=True, quantity=3))

        results = get_all_products(conn, available_only=True)
        assert len(results) == 2
        assert all(r["available"] for r in results)

    def test_given_products_when_get_all_then_ordered_by_name(self, conn) -> None:
        """GIVEN products, WHEN get_all, THEN sorted alphabetically by name."""
        upsert_product(conn, _make_product(sku="1", name="Zebra Set"))
        upsert_product(conn, _make_product(sku="2", name="Alpha Set"))

        results = get_all_products(conn)
        assert results[0]["name"] == "Alpha Set"
        assert results[1]["name"] == "Zebra Set"

    def test_given_product_when_get_all_then_all_fields_present(self, conn) -> None:
        """GIVEN a product, WHEN get_all, THEN dict has all expected keys."""
        upsert_product(conn, _make_product(rating="4.50", rating_count=12))

        results = get_all_products(conn)
        assert len(results) == 1
        expected_keys = {
            "sku", "name", "price_myr", "original_price_myr",
            "url", "image_url", "available", "quantity", "total_sold",
            "rating", "rating_count", "last_scraped_at",
        }
        assert set(results[0].keys()) == expected_keys
