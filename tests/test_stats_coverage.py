"""Tests for /stats/coverage endpoint column mappings and response shape."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.stats import _SOURCES, router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Actual Postgres column names per table (ground truth from schema)
_PG_COLUMNS: dict[str, set[str]] = {
    "bricklink_items": {"id", "item_id", "set_number", "item_type", "title", "weight", "year_released", "image_url", "last_scraped_at"},
    "brickeconomy_snapshots": {"id", "set_number", "scraped_at", "title", "theme", "subtheme", "pieces", "minifigs", "rrp_usd_cents", "rrp_gbp_cents", "rating_value", "review_count", "annual_growth_pct", "year_retired"},
    "keepa_snapshots": {"id", "set_number", "scraped_at", "amazon_asin", "amazon_price_cents", "amazon_title"},
    "shopee_products": {"id", "title", "price_display", "price_cents", "sold_count", "rating", "shop_name", "product_url", "image_url", "source_url", "is_sold_out", "scraped_at"},
    "mightyutan_products": {"id", "sku", "name", "price_myr", "original_price_myr", "url", "image_url", "available", "quantity", "total_sold", "rating", "rating_count", "last_scraped_at", "created_at", "updated_at"},
    "toysrus_products": {"id", "sku", "name", "price_myr", "brand", "category", "age_range", "url", "image_url", "available", "last_scraped_at", "created_at", "updated_at"},
    "google_trends_snapshots": {"id", "set_number", "scraped_at"},
    "set_minifigures": {"id", "set_item_id", "set_number", "minifig_id", "quantity", "scraped_at"},
    "image_assets": {"id", "asset_type", "item_id", "source_url", "local_path", "file_size_bytes", "content_type", "downloaded_at", "status", "error", "retry_count", "created_at"},
    "ml_prediction_snapshots": {"id", "snapshot_date", "set_number", "predicted_growth_pct", "confidence", "tier", "model_version", "actual_growth_pct", "actual_measured_at"},
}


def _make_mock_conn(total_sets: int = 10, row_count: int = 5, distinct: int = 3, latest: str = "2026-01-01") -> MagicMock:
    """Build a mock connection that returns predictable values for every query."""
    conn = MagicMock()

    def _execute(sql: str) -> MagicMock:
        result = MagicMock()
        if "COUNT(*) FROM lego_items" in sql:
            result.fetchone.return_value = (total_sets,)
        elif "set_number FROM lego_items" in sql:
            result.fetchall.return_value = [(f"S{i}",) for i in range(total_sets)]
        elif "COUNT(*)" in sql:
            result.fetchone.return_value = (row_count,)
        elif "COUNT(DISTINCT" in sql:
            result.fetchone.return_value = (distinct,)
        elif "MAX(" in sql:
            result.fetchone.return_value = (latest,)
        elif "SELECT DISTINCT" in sql:
            result.fetchall.return_value = [(f"S{i}",) for i in range(distinct)]
        return result

    conn.execute.side_effect = _execute
    return conn


def _get_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


# ---------------------------------------------------------------------------
# GWT: Column name correctness
# ---------------------------------------------------------------------------


class TestSourceColumnMappings:
    """Given _SOURCES config, when compared to actual PG schema, then all columns exist."""

    @pytest.mark.parametrize(
        "label, table, key_col, date_col, key_expr",
        _SOURCES,
        ids=[s[0] for s in _SOURCES],
    )
    def test_key_column_exists_in_schema(self, label: str, table: str, key_col: str, date_col: str | None, key_expr: str | None) -> None:
        assert table in _PG_COLUMNS, f"Unknown table {table}"
        assert key_col in _PG_COLUMNS[table], (
            f"{label}: key_col '{key_col}' not in {table} columns {_PG_COLUMNS[table]}"
        )

    @pytest.mark.parametrize(
        "label, table, key_col, date_col, key_expr",
        [s for s in _SOURCES if s[3] is not None],
        ids=[s[0] for s in _SOURCES if s[3] is not None],
    )
    def test_date_column_exists_in_schema(self, label: str, table: str, key_col: str, date_col: str | None, key_expr: str | None) -> None:
        assert date_col in _PG_COLUMNS[table], (
            f"{label}: date_col '{date_col}' not in {table} columns {_PG_COLUMNS[table]}"
        )


# ---------------------------------------------------------------------------
# GWT: Endpoint response shape
# ---------------------------------------------------------------------------


class TestCoverageEndpoint:
    """Given a mock DB, when calling /api/stats/coverage, then correct response shape."""

    def test_returns_success_with_sources(self) -> None:
        app = _get_app()
        mock_conn = _make_mock_conn()
        app.dependency_overrides[__import__("api.dependencies", fromlist=["get_db"]).get_db] = lambda: mock_conn

        client = TestClient(app)
        resp = client.get("/api/stats/coverage")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "data" in body
        assert "total_sets" in body["data"]
        assert "sources" in body["data"]

    def test_source_count_matches_config(self) -> None:
        app = _get_app()
        mock_conn = _make_mock_conn()
        app.dependency_overrides[__import__("api.dependencies", fromlist=["get_db"]).get_db] = lambda: mock_conn

        client = TestClient(app)
        resp = client.get("/api/stats/coverage")
        sources = resp.json()["data"]["sources"]
        assert len(sources) == len(_SOURCES)

    def test_each_source_has_required_fields(self) -> None:
        app = _get_app()
        mock_conn = _make_mock_conn()
        app.dependency_overrides[__import__("api.dependencies", fromlist=["get_db"]).get_db] = lambda: mock_conn

        client = TestClient(app)
        resp = client.get("/api/stats/coverage")
        required = {"source", "total_rows", "distinct_sets", "missing_sets", "coverage_pct", "latest_scraped"}
        for src in resp.json()["data"]["sources"]:
            assert required <= set(src.keys()), f"Missing fields in {src['source']}"

    def test_coverage_pct_calculation(self) -> None:
        app = _get_app()
        mock_conn = _make_mock_conn(total_sets=100, distinct=25)
        app.dependency_overrides[__import__("api.dependencies", fromlist=["get_db"]).get_db] = lambda: mock_conn

        client = TestClient(app)
        resp = client.get("/api/stats/coverage")
        for src in resp.json()["data"]["sources"]:
            assert src["coverage_pct"] == 25.0

    def test_zero_sets_no_division_error(self) -> None:
        app = _get_app()
        mock_conn = _make_mock_conn(total_sets=0, distinct=0)
        app.dependency_overrides[__import__("api.dependencies", fromlist=["get_db"]).get_db] = lambda: mock_conn

        client = TestClient(app)
        resp = client.get("/api/stats/coverage")
        assert resp.status_code == 200
        for src in resp.json()["data"]["sources"]:
            assert src["coverage_pct"] == 0
