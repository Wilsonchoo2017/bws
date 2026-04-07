"""GWT tests for add-item feature -- validation, duplicates, and creation."""

import pytest
from fastapi.testclient import TestClient

from db.connection import get_connection
from db.schema import init_schema
from services.items.repository import (
    get_or_create_item,
    item_exists,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """Connection with schema initialized."""
    connection = get_connection()
    init_schema(connection)
    yield connection


class _NoCloseConnection:
    """Wrapper that prevents close() from destroying the in-memory DB."""

    def __init__(self, real_conn):
        self._conn = real_conn

    def close(self):
        pass  # no-op so route handlers don't destroy the test DB

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def client(conn, monkeypatch):
    """TestClient with get_db dependency overridden to use in-memory DB."""
    from api.dependencies import get_db
    from api.main import app

    wrapped = _NoCloseConnection(conn)

    def _override_get_db():
        yield wrapped

    monkeypatch.setattr("db.connection.get_connection", lambda: wrapped)
    app.dependency_overrides[get_db] = _override_get_db

    yield TestClient(app)

    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Repository: item_exists
# ---------------------------------------------------------------------------

class TestItemExists:
    """Given the item_exists function, verify duplicate detection works."""

    def test_given_empty_db_when_checking_then_false(self, conn):
        """Given empty database, when checking item_exists, then returns False."""
        assert item_exists(conn, "75192") is False

    def test_given_existing_item_when_checking_then_true(self, conn):
        """Given an item was created, when checking item_exists, then returns True."""
        get_or_create_item(conn, "75192", title="Millennium Falcon")
        assert item_exists(conn, "75192") is True

    def test_given_different_set_number_when_checking_then_false(self, conn):
        """Given item 75192 exists, when checking 10300, then returns False."""
        get_or_create_item(conn, "75192")
        assert item_exists(conn, "10300") is False


# ---------------------------------------------------------------------------
# Route: POST /api/items
# ---------------------------------------------------------------------------

class TestAddItemEndpoint:
    """Given the POST /api/items endpoint, verify add-item behavior."""

    def test_given_valid_set_number_when_posting_then_201_created(self, client):
        """Given valid set_number '75192', when POST /api/items,
        then 201 with item data returned."""
        resp = client.post("/api/items", json={"set_number": "75192"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["set_number"] == "75192"

    def test_given_invalid_format_when_posting_then_422_error(self, client):
        """Given set_number 'abc', when POST /api/items,
        then 422 validation error."""
        resp = client.post("/api/items", json={"set_number": "abc"})
        assert resp.status_code == 422

    def test_given_empty_set_number_when_posting_then_422_error(self, client):
        """Given empty set_number '', when POST /api/items,
        then 422 validation error."""
        resp = client.post("/api/items", json={"set_number": ""})
        assert resp.status_code == 422

    def test_given_too_long_set_number_when_posting_then_422_error(self, client):
        """Given set_number exceeding max length, when POST /api/items,
        then 422 validation error."""
        resp = client.post("/api/items", json={"set_number": "1234567890123456789012"})
        assert resp.status_code == 422

    def test_given_existing_item_when_posting_again_then_409_conflict(self, client):
        """Given '75192' already exists, when POST /api/items with '75192',
        then 409 Conflict returned."""
        resp1 = client.post("/api/items", json={"set_number": "75192"})
        assert resp1.status_code == 201

        resp2 = client.post("/api/items", json={"set_number": "75192"})
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]

    def test_given_set_number_with_suffix_when_posting_then_201(self, client):
        """Given valid set_number '10300-1', when POST /api/items,
        then 201 created successfully."""
        resp = client.post("/api/items", json={"set_number": "10300-1"})
        assert resp.status_code == 201
        assert resp.json()["data"]["set_number"] == "10300-1"

    def test_given_valid_post_when_getting_detail_then_item_retrievable(self, client):
        """Given a successful POST, when GET /api/items/{set_number},
        then the item is found."""
        client.post("/api/items", json={"set_number": "75192"})
        resp = client.get("/api/items/75192")
        assert resp.status_code == 200
        assert resp.json()["data"]["set_number"] == "75192"

    def test_given_missing_body_when_posting_then_422(self, client):
        """Given no request body, when POST /api/items,
        then 422 validation error."""
        resp = client.post("/api/items")
        assert resp.status_code == 422
