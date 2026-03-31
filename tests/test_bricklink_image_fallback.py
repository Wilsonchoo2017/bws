"""GWT tests for BrickLink image URL fallback.

Ensures every LEGO item gets a BrickLink image URL when no image is provided,
across all read paths: items list, portfolio holdings, transactions, and metadata.
"""

from datetime import datetime

import duckdb
import pytest

from db.schema import init_schema
from services.items.repository import get_all_items, get_or_create_item, record_price
from services.portfolio.repository import (
    create_transaction,
    get_holdings,
    get_transaction,
    list_transactions,
)

_TXN_DATE = datetime(2024, 1, 1)


def _expected_image_url(set_number: str) -> str:
    return f"https://img.bricklink.com/ItemImage/SN/0/{set_number}-1.png"


@pytest.fixture()
def conn():
    """In-memory DuckDB connection with schema initialized."""
    c = duckdb.connect(":memory:")
    init_schema(c)
    yield c
    c.close()


@pytest.fixture()
def seed_item(conn):
    """Insert a lego_items row with a price record for market value."""

    def _seed(
        set_number: str = "75192",
        title: str = "Millennium Falcon",
        price_cents: int = 50000,
        image_url: str | None = None,
    ):
        if image_url is not None:
            conn.execute(
                """
                INSERT INTO lego_items (id, set_number, title, theme, image_url)
                VALUES (nextval('lego_items_id_seq'), ?, ?, 'Star Wars', ?)
                """,
                [set_number, title, image_url],
            )
        else:
            conn.execute(
                """
                INSERT INTO lego_items (id, set_number, title, theme)
                VALUES (nextval('lego_items_id_seq'), ?, ?, 'Star Wars')
                """,
                [set_number, title],
            )
        conn.execute(
            """
            INSERT INTO price_records (id, set_number, source, price_cents, currency)
            VALUES (nextval('price_records_id_seq'), ?, 'shopee', ?, 'MYR')
            """,
            [set_number, price_cents],
        )

    return _seed


# ---------------------------------------------------------------------------
# Group 1: get_or_create_item -- image_url is auto-filled on insert
# ---------------------------------------------------------------------------


class TestGetOrCreateItemImageFallback:
    """Given a new item without image_url, get_or_create_item fills BrickLink URL."""

    def test_given_no_image_when_creating_item_then_bricklink_url_stored(
        self, conn,
    ):
        """Given no image_url is provided,
        when get_or_create_item is called,
        then the stored image_url is the BrickLink constructed URL."""
        get_or_create_item(conn, "75192", title="Millennium Falcon")

        row = conn.execute(
            "SELECT image_url FROM lego_items WHERE set_number = '75192'"
        ).fetchone()

        assert row is not None
        assert row[0] == _expected_image_url("75192")

    def test_given_explicit_image_when_creating_item_then_explicit_preserved(
        self, conn,
    ):
        """Given an explicit image_url is provided,
        when get_or_create_item is called,
        then the provided URL is stored (not overwritten by fallback)."""
        custom_url = "https://example.com/my-image.jpg"
        get_or_create_item(conn, "75192", image_url=custom_url)

        row = conn.execute(
            "SELECT image_url FROM lego_items WHERE set_number = '75192'"
        ).fetchone()

        assert row is not None
        assert row[0] == custom_url

    def test_given_existing_image_when_updating_without_image_then_original_kept(
        self, conn,
    ):
        """Given an item already has an image_url,
        when get_or_create_item is called again without image_url,
        then the original image is preserved (COALESCE keeps existing)."""
        custom_url = "https://example.com/original.jpg"
        get_or_create_item(conn, "75192", image_url=custom_url)

        # Call again -- the fallback URL will be passed, but COALESCE
        # keeps the existing non-NULL value
        get_or_create_item(conn, "75192", title="Updated Title")

        row = conn.execute(
            "SELECT image_url FROM lego_items WHERE set_number = '75192'"
        ).fetchone()

        assert row is not None
        assert row[0] == custom_url

    def test_given_different_set_numbers_when_creating_then_urls_match_set(
        self, conn,
    ):
        """Given multiple sets without images,
        when creating them,
        then each gets a BrickLink URL matching its own set number."""
        get_or_create_item(conn, "10300", title="DeLorean")
        get_or_create_item(conn, "21330", title="Home Alone")

        for sn in ("10300", "21330"):
            row = conn.execute(
                "SELECT image_url FROM lego_items WHERE set_number = ?", [sn]
            ).fetchone()
            assert row[0] == _expected_image_url(sn)


# ---------------------------------------------------------------------------
# Group 2: get_all_items -- COALESCE fallback for NULL image_url
# ---------------------------------------------------------------------------


class TestGetAllItemsImageFallback:
    """Given items in the list view, verify image_url is never NULL."""

    def test_given_item_with_null_image_when_listing_then_bricklink_url_returned(
        self, conn, seed_item,
    ):
        """Given an item with NULL image_url in the database,
        when get_all_items is called,
        then the result contains the BrickLink fallback URL."""
        seed_item("75192", "Millennium Falcon")

        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "75192")

        assert item["image_url"] == _expected_image_url("75192")

    def test_given_item_with_real_image_when_listing_then_real_url_returned(
        self, conn, seed_item,
    ):
        """Given an item with a real image_url,
        when get_all_items is called,
        then the real URL is returned (not the fallback)."""
        seed_item("75192", "Millennium Falcon", image_url="https://example.com/real.jpg")

        items = get_all_items(conn)
        item = next(i for i in items if i["set_number"] == "75192")

        assert item["image_url"] == "https://example.com/real.jpg"

    def test_given_multiple_items_when_listing_then_all_have_image_urls(
        self, conn, seed_item,
    ):
        """Given multiple items (some with images, some without),
        when get_all_items is called,
        then every item has a non-NULL image_url."""
        seed_item("75192", "Millennium Falcon")
        seed_item("10300", "DeLorean", image_url="https://example.com/delorean.jpg")

        items = get_all_items(conn)

        for item in items:
            assert item["image_url"] is not None, (
                f"Item {item['set_number']} has NULL image_url"
            )


# ---------------------------------------------------------------------------
# Group 3: Portfolio holdings -- image_url via _item_metadata
# ---------------------------------------------------------------------------


class TestPortfolioHoldingsImageFallback:
    """Given portfolio holdings, verify image_url is never NULL."""

    def test_given_holding_with_null_image_when_getting_holdings_then_fallback(
        self, conn, seed_item,
    ):
        """Given a portfolio holding whose lego_item has NULL image_url,
        when get_holdings is called,
        then the holding's image_url is the BrickLink fallback."""
        seed_item("75192", "Millennium Falcon")
        create_transaction(conn, "75192", "BUY", 1, 350000, "new", _TXN_DATE)

        holdings = get_holdings(conn)

        assert len(holdings) == 1
        assert holdings[0]["image_url"] == _expected_image_url("75192")

    def test_given_holding_with_real_image_when_getting_holdings_then_real_url(
        self, conn, seed_item,
    ):
        """Given a portfolio holding whose lego_item has a real image_url,
        when get_holdings is called,
        then the real URL is returned."""
        seed_item("75192", "Millennium Falcon", image_url="https://example.com/falcon.jpg")
        create_transaction(conn, "75192", "BUY", 1, 350000, "new", _TXN_DATE)

        holdings = get_holdings(conn)

        assert len(holdings) == 1
        assert holdings[0]["image_url"] == "https://example.com/falcon.jpg"

    def test_given_multiple_holdings_when_getting_then_all_have_images(
        self, conn, seed_item,
    ):
        """Given multiple holdings with mixed image states,
        when get_holdings is called,
        then every holding has a non-NULL image_url."""
        seed_item("75192", "Millennium Falcon")
        seed_item("10300", "DeLorean", image_url="https://example.com/d.jpg")
        create_transaction(conn, "75192", "BUY", 1, 350000, "new", _TXN_DATE)
        create_transaction(conn, "10300", "BUY", 2, 50000, "new", _TXN_DATE)

        holdings = get_holdings(conn)

        for h in holdings:
            assert h["image_url"] is not None, (
                f"Holding {h['set_number']} has NULL image_url"
            )


# ---------------------------------------------------------------------------
# Group 4: Portfolio transactions -- image_url in list and detail
# ---------------------------------------------------------------------------


class TestPortfolioTransactionsImageFallback:
    """Given portfolio transactions, verify image_url is never NULL."""

    def test_given_txn_with_null_image_when_listing_then_fallback(
        self, conn, seed_item,
    ):
        """Given a transaction whose item has NULL image_url,
        when list_transactions is called,
        then the transaction's image_url is the BrickLink fallback."""
        seed_item("75192", "Millennium Falcon")
        create_transaction(conn, "75192", "BUY", 1, 350000, "new", _TXN_DATE)

        txns = list_transactions(conn)

        assert len(txns) == 1
        assert txns[0]["image_url"] == _expected_image_url("75192")

    def test_given_txn_with_real_image_when_listing_then_real_url(
        self, conn, seed_item,
    ):
        """Given a transaction whose item has a real image_url,
        when list_transactions is called,
        then the real URL is returned."""
        seed_item("75192", "Millennium Falcon", image_url="https://example.com/falcon.jpg")
        create_transaction(conn, "75192", "BUY", 1, 350000, "new", _TXN_DATE)

        txns = list_transactions(conn)

        assert len(txns) == 1
        assert txns[0]["image_url"] == "https://example.com/falcon.jpg"

    def test_given_txn_when_getting_by_id_then_image_url_present(
        self, conn, seed_item,
    ):
        """Given a transaction for an item without image,
        when get_transaction is called by ID,
        then image_url is the BrickLink fallback."""
        seed_item("75192", "Millennium Falcon")
        txn_id = create_transaction(conn, "75192", "BUY", 1, 350000, "new", _TXN_DATE)

        txn = get_transaction(conn, txn_id)

        assert txn is not None
        assert txn["image_url"] == _expected_image_url("75192")


# ---------------------------------------------------------------------------
# Group 5: URL format correctness
# ---------------------------------------------------------------------------


class TestBricklinkImageUrlFormat:
    """Given different set numbers, verify the constructed URL format is correct."""

    @pytest.mark.parametrize(
        "set_number",
        ["75192", "10300", "21330", "40567", "854"],
    )
    def test_given_set_number_when_creating_then_url_format_correct(
        self, conn, set_number,
    ):
        """Given a set number,
        when get_or_create_item is called without image,
        then the stored URL follows BrickLink's SN/0/{set}-1.png pattern."""
        get_or_create_item(conn, set_number, title="Test Set")

        row = conn.execute(
            "SELECT image_url FROM lego_items WHERE set_number = ?",
            [set_number],
        ).fetchone()

        assert row[0] is not None
        assert row[0].startswith("https://img.bricklink.com/ItemImage/SN/0/")
        assert row[0].endswith("-1.png")
        assert set_number in row[0]
