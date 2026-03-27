"""GWT tests for scrape route — ensures all registered scrapers are accepted."""

import pytest
from fastapi.testclient import TestClient

from api.routes.scrape import SCRAPERS, VALID_SCRAPER_IDS


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from api.main import app

    return TestClient(app)


class TestScraperRegistry:
    """Given the scraper registry, verify all expected scrapers are present."""

    def test_given_registry_when_checking_shopee_then_present(self):
        """Given SCRAPERS registry, when checking for shopee, then it exists."""
        assert "shopee" in VALID_SCRAPER_IDS

    def test_given_registry_when_checking_toysrus_then_present(self):
        """Given SCRAPERS registry, when checking for toysrus, then it exists."""
        assert "toysrus" in VALID_SCRAPER_IDS

    def test_given_registry_when_listing_then_ids_match_valid_set(self):
        """Given SCRAPERS list, when extracting IDs, then they match VALID_SCRAPER_IDS."""
        ids_from_list = {s.id for s in SCRAPERS}
        assert ids_from_list == VALID_SCRAPER_IDS

    def test_given_registry_when_checking_unknown_then_not_present(self):
        """Given SCRAPERS registry, when checking unknown ID, then rejected."""
        assert "nonexistent" not in VALID_SCRAPER_IDS


class TestStartScrapeValidation:
    """Given scrape job requests, verify validation accepts/rejects correctly."""

    def test_given_shopee_request_when_valid_url_then_accepted(self, client):
        """Given shopee scraper_id with valid URL, when posting, then job created."""
        resp = client.post(
            "/api/scrape/jobs",
            json={
                "scraper_id": "shopee",
                "url": "https://shopee.com.my/legoshopmy?page=0&shopCollection=258084132",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scraper_id"] == "shopee"
        assert data["status"] == "queued"

    def test_given_toysrus_request_when_valid_url_then_accepted(self, client):
        """Given toysrus scraper_id with valid URL, when posting, then job created."""
        resp = client.post(
            "/api/scrape/jobs",
            json={
                "scraper_id": "toysrus",
                "url": "https://www.toysrus.com.my/lego/",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scraper_id"] == "toysrus"
        assert data["status"] == "queued"

    def test_given_unknown_scraper_when_posting_then_400(self, client):
        """Given unknown scraper_id, when posting, then 400 returned."""
        resp = client.post(
            "/api/scrape/jobs",
            json={
                "scraper_id": "nonexistent",
                "url": "https://example.com",
            },
        )
        assert resp.status_code == 400
        assert "Unknown scraper" in resp.json()["detail"]

    def test_given_shopee_request_when_wrong_domain_then_400(self, client):
        """Given shopee scraper_id with wrong domain, when posting, then 400."""
        resp = client.post(
            "/api/scrape/jobs",
            json={
                "scraper_id": "shopee",
                "url": "https://www.toysrus.com.my/lego/",
            },
        )
        assert resp.status_code == 400
        assert "shopee.com.my" in resp.json()["detail"]

    def test_given_toysrus_request_when_wrong_domain_then_400(self, client):
        """Given toysrus scraper_id with wrong domain, when posting, then 400."""
        resp = client.post(
            "/api/scrape/jobs",
            json={
                "scraper_id": "toysrus",
                "url": "https://shopee.com.my/something",
            },
        )
        assert resp.status_code == 400
        assert "toysrus.com.my" in resp.json()["detail"]


class TestListScrapers:
    """Given the scrapers endpoint, verify all scrapers are returned."""

    def test_given_scrapers_endpoint_when_listing_then_all_returned(self, client):
        """Given GET /scrapers, when called, then all registered scrapers returned."""
        resp = client.get("/api/scrape/scrapers")
        assert resp.status_code == 200
        data = resp.json()
        ids = {s["id"] for s in data}
        assert "shopee" in ids
        assert "toysrus" in ids

    def test_given_toysrus_id_when_getting_by_id_then_details_returned(self, client):
        """Given toysrus scraper ID, when fetching, then correct details returned."""
        resp = client.get("/api/scrape/scrapers/toysrus")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "toysrus"
        assert len(data["targets"]) == 1
        assert data["targets"][0]["id"] == "lego-catalog"
