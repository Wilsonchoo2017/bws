"""GWT tests for EnrichmentWorker -- proves it handles the enrichment data source."""

import asyncio
from unittest.mock import patch

from api.jobs import JobManager
from api.workers.enrichment import EnrichmentWorker


class TestEnrichmentWorkerIdentity:
    """Given an EnrichmentWorker, verify it identifies as the enrichment source."""

    def test_given_enrichment_worker_when_scraper_id_checked_then_matches_enrichment(self):
        """Given an EnrichmentWorker, when scraper_id checked, then it is 'enrichment'."""
        worker = EnrichmentWorker()
        assert worker.scraper_id == "enrichment"


class TestEnrichmentWorkerRun:
    """Given an enrichment job, verify the worker processes it correctly."""

    def test_given_enrichment_job_when_processed_then_returns_field_counts(self):
        """Given an enrichment job, when worker runs, then returns field counts in WorkResult."""
        worker = EnrichmentWorker()
        mgr = JobManager()
        job = mgr.create_job("enrichment", "75192")

        fake_result = {
            "set_number": "75192",
            "fields_found": 3,
            "fields_total": 5,
            "sources_called": ["bricklink"],
            "field_details": [
                {"field": "title", "status": "found", "value": "Millennium Falcon", "source": "bricklink", "errors": []},
                {"field": "theme", "status": "found", "value": "Star Wars", "source": "bricklink", "errors": []},
                {"field": "year_released", "status": "found", "value": "2017", "source": "bricklink", "errors": []},
                {"field": "weight", "status": "not_found", "value": None, "source": None, "errors": []},
                {"field": "rrp", "status": "not_found", "value": None, "source": None, "errors": []},
            ],
        }

        with (
            patch(
                "api.workers.enrichment._run_enrichment",
                return_value=fake_result,
            ),
            patch("services.notifications.deal_notifier.check_and_notify", return_value=0),
        ):
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 3
        assert "3/5 fields found" in result.log_summary
        assert "title" in result.log_summary
        assert "weight" in result.log_summary

    def test_given_enrichment_job_when_item_not_found_then_returns_zero(self):
        """Given an enrichment job for missing item, when run, then returns 0 fields."""
        worker = EnrichmentWorker()
        mgr = JobManager()
        job = mgr.create_job("enrichment", "99999")

        fake_result = {
            "set_number": "99999",
            "fields_found": 0,
            "fields_total": 0,
            "error": "Item 99999 not found in lego_items",
            "field_details": [],
        }

        with (
            patch(
                "api.workers.enrichment._run_enrichment",
                return_value=fake_result,
            ),
            patch("services.notifications.deal_notifier.check_and_notify", return_value=0),
        ):
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 0
