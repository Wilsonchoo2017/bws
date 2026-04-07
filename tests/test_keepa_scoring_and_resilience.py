"""GWT tests for Keepa search scoring, title lookup fallback, and executor resilience.

Covers edge cases found in production where DUPLO/toddler sets (10786, 10789,
10791, etc.) failed due to:
- Missing item titles (only in lego_items, not bricklink_items)
- Wrong product selected because set-number score was too low
- Mismatches silently swallowed as success (no retry)
- No fallback search when initial query returned no candidates
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.keepa.scraper import _score_result, _title_contains_set_number
from services.scrape_queue.models import ExecutorResult


# ---------------------------------------------------------------------------
# _score_result: search result ranking
# ---------------------------------------------------------------------------


class TestScoreResult:
    """Given search result titles, verify scoring ranks correct products higher."""

    # -- Set number presence --

    def test_given_title_with_set_number_when_scored_then_gets_highest_boost(self):
        """Given 'LEGO 10787 Kitty Fairy Garden Party' for set 10787,
        when _score_result is called,
        then set-number bonus (+30) outweighs other signals."""
        score = _score_result("LEGO 10787 Kitty Fairy Garden Party", "10787")
        assert score >= 50  # +30 (set number) + +20 (starts with lego)

    def test_given_title_without_set_number_when_scored_then_lower_than_with(self):
        """Given 'LEGO Gabby Dollhouse Bakey Fun 10785' for set 10786,
        when _score_result is called,
        then scores lower than a title containing 10786."""
        wrong = _score_result(
            "LEGO Gabby's Dollhouse Bakey with Cakey Fun 10785", "10786",
        )
        right = _score_result(
            "LEGO Gabby & MerCat's Ship & Spa 10786", "10786",
        )
        assert right > wrong

    def test_given_wrong_set_starts_with_lego_when_scored_then_still_lower(self):
        """Given a LEGO-prefixed title with the WRONG set number,
        when _score_result is called,
        then it scores strictly lower than one with the correct set number,
        even if the wrong one also starts with 'LEGO'."""
        wrong = _score_result("LEGO Speed Champions 76911 Aston Martin", "10987")
        right = _score_result("LEGO DUPLO 10987 Recycling Truck", "10987")
        assert right > wrong

    # -- LEGO brand signals --

    def test_given_starts_with_lego_when_scored_then_gets_brand_boost(self):
        """Given 'LEGO Classic Creative Vehicles 11036',
        when scored for set 11036,
        then gets both set-number and starts-with-lego boosts."""
        score = _score_result("LEGO Classic Creative Vehicles 11036", "11036")
        assert score >= 50

    def test_given_by_lego_when_scored_then_gets_brand_boost(self):
        """Given 'Creative Vehicles by LEGO Group' for set 11036,
        when _score_result is called,
        then gets by-lego boost."""
        score = _score_result("Creative Vehicles by LEGO Group", "11036")
        assert score > 0

    def test_given_third_party_brand_when_scored_then_penalized(self):
        """Given 'Compatible Bricks Set by Mega Bloks' for any set,
        when _score_result is called,
        then gets negative penalty for non-LEGO brand."""
        score = _score_result("Compatible Bricks Set by Mega Bloks", "10787")
        assert score < 0

    # -- Accessory filtering --

    def test_given_display_case_when_scored_then_excluded(self):
        """Given 'Acrylic Display Case for LEGO 10787',
        when _score_result is called,
        then returns -1 (excluded as accessory)."""
        assert _score_result("Acrylic Display Case for LEGO 10787", "10787") == -1

    def test_given_led_light_kit_when_scored_then_excluded(self):
        """Given 'LED Light Kit for LEGO 10787',
        when _score_result is called,
        then returns -1."""
        assert _score_result("LED Light Kit for LEGO 10787", "10787") == -1

    def test_given_wall_mount_when_scored_then_excluded(self):
        """Given 'Wall Mount for LEGO 10787',
        when _score_result is called,
        then returns -1."""
        assert _score_result("Wall Mount for LEGO 10787", "10787") == -1

    def test_given_compatible_with_when_scored_then_excluded(self):
        """Given 'Building Blocks Compatible with LEGO 10787',
        when _score_result is called,
        then returns -1 (third-party clone)."""
        assert _score_result(
            "Building Blocks Compatible with LEGO 10787", "10787",
        ) == -1

    def test_given_moc_when_scored_then_excluded(self):
        """Given 'MOC Custom Build for LEGO 10787',
        when _score_result is called,
        then returns -1."""
        assert _score_result("MOC Custom Build for LEGO 10787", "10787") == -1

    # -- Edge cases --

    def test_given_set_number_substring_of_another_when_scored_then_both_match(self):
        """Given title 'LEGO 1078' for set 1078 vs set 10787,
        when _score_result is called for each,
        then 1078 matches its own title but 10787 does not."""
        assert _score_result("LEGO 1078 Classic Set", "1078") >= 50
        # "1078" is a substring of "10787" but "10787" is NOT in "LEGO 1078"
        score_10787 = _score_result("LEGO 1078 Classic Set", "10787")
        assert score_10787 < 50  # no set-number bonus

    def test_given_empty_title_when_scored_then_zero(self):
        """Given empty title,
        when _score_result is called,
        then returns 0 (no signals, but not excluded)."""
        assert _score_result("", "10787") == 0

    def test_given_set_number_in_middle_of_title_when_scored_then_matches(self):
        """Given 'Building Toy Set for LEGO 10787 Fans' for set 10787,
        when _score_result is called,
        then set-number bonus applies even when number is not at start."""
        score = _score_result("Building Toy Set for LEGO 10787 Fans", "10787")
        assert score >= 30  # at least the set-number bonus

    def test_given_suffixed_set_number_when_scored_then_matches_bare(self):
        """Given set number '10787-1' (with variant suffix),
        when _score_result is called with a title containing '10787',
        then the bare number '10787' still matches."""
        score = _score_result("LEGO 10787 Kitty Fairy Garden Party", "10787-1")
        assert score >= 50


# ---------------------------------------------------------------------------
# _lookup_item_title: fallback from bricklink_items to lego_items
# ---------------------------------------------------------------------------


class TestLookupItemTitle:
    """Given sets that may or may not exist in trusted sources,
    verify the cascading lookup: bricklink -> brickeconomy -> enriched lego_items."""

    def test_given_set_in_bricklink_items_when_lookup_then_returns_bricklink_title(self):
        """Given set '60305' exists in bricklink_items with title 'Car Transporter',
        when _lookup_item_title is called,
        then returns the bricklink_items title."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = ("Car Transporter",)
        assert _lookup_item_title(conn, "60305") == "Car Transporter"

    def test_given_set_only_in_brickeconomy_when_lookup_then_returns_be_title(self):
        """Given set '10789' is NOT in bricklink_items but IS in brickeconomy_snapshots,
        when _lookup_item_title is called,
        then returns the brickeconomy title."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()

        def side_effect(query, params):
            result = MagicMock()
            if "bricklink_items" in query:
                result.fetchone.return_value = None
            elif "brickeconomy_snapshots" in query:
                result.fetchone.return_value = ("Spider-Man's Car and Doc Ock",)
            else:
                result.fetchone.return_value = None
            return result

        conn.execute.side_effect = side_effect
        assert _lookup_item_title(conn, "10789") == "Spider-Man's Car and Doc Ock"

    def test_given_set_only_in_enriched_lego_items_when_lookup_then_falls_back(self):
        """Given set exists only in lego_items with last_enriched_at set,
        when _lookup_item_title is called,
        then returns the lego_items title."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()

        def side_effect(query, params):
            result = MagicMock()
            if "bricklink_items" in query:
                result.fetchone.return_value = None
            elif "brickeconomy_snapshots" in query:
                result.fetchone.return_value = None
            else:
                result.fetchone.return_value = ("Spider-Man's Car and Doc Ock",)
            return result

        conn.execute.side_effect = side_effect
        assert _lookup_item_title(conn, "10789") == "Spider-Man's Car and Doc Ock"

    def test_given_set_in_no_source_when_lookup_then_returns_none(self):
        """Given set '99999' exists in no trusted source,
        when _lookup_item_title is called,
        then returns None."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        assert _lookup_item_title(conn, "99999") is None

    def test_given_bricklink_returns_empty_string_when_lookup_then_falls_back(self):
        """Given bricklink_items returns an empty-string title,
        when _lookup_item_title is called,
        then treats it as missing and falls back to brickeconomy."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()

        def side_effect(query, params):
            result = MagicMock()
            if "bricklink_items" in query:
                result.fetchone.return_value = ("",)
            elif "brickeconomy_snapshots" in query:
                result.fetchone.return_value = ("Growing Carrot",)
            else:
                result.fetchone.return_value = None
            return result

        conn.execute.side_effect = side_effect
        assert _lookup_item_title(conn, "10981") == "Growing Carrot"

    def test_given_unenriched_lego_item_with_placeholder_when_lookup_then_returns_none(self):
        """Given a lego_item that hasn't been enriched (retail placeholder title),
        when _lookup_item_title is called,
        then returns None -- we don't trust un-enriched titles."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()

        def side_effect(query, params):
            result = MagicMock()
            # last_enriched_at IS NOT NULL filter means no row returned
            result.fetchone.return_value = None
            return result

        conn.execute.side_effect = side_effect
        assert _lookup_item_title(conn, "12345") is None

    def test_given_database_error_when_lookup_then_returns_none(self):
        """Given the database raises an exception,
        when _lookup_item_title is called,
        then returns None gracefully (no crash)."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()
        conn.execute.side_effect = Exception("connection lost")
        assert _lookup_item_title(conn, "10787") is None


# ---------------------------------------------------------------------------
# execute_keepa: executor result handling & retry behavior
# ---------------------------------------------------------------------------


class TestExecuteKeepaResultHandling:
    """Given various scrape outcomes, verify the executor returns correct
    ExecutorResult so the dispatcher retries or skips appropriately."""

    @pytest.fixture()
    def _mock_deps(self):
        """Patch all heavy dependencies so execute_keepa runs in isolation.

        Imports inside execute_keepa are deferred, so we patch at source modules.
        """
        with (
            patch("services.scrape_queue.executors.keepa._lookup_item_title", return_value="Test Set"),
            patch("services.browser.get_persistent_browser") as mock_browser_factory,
            patch("services.keepa.scheduler.record_keepa_failure") as mock_fail,
            patch("services.keepa.scheduler.record_keepa_success") as mock_success,
            patch("services.keepa.repository.save_keepa_snapshot"),
            patch("services.keepa.repository.record_keepa_prices"),
            patch("services.keepa.scraper.scrape_with_page") as mock_scrape,
            patch("config.settings.KEEPA_CONFIG") as mock_config,
        ):
            mock_config.headless = True
            mock_config.locale = "en-US"
            mock_config.viewport_width = 1366
            mock_config.viewport_height = 768
            browser = MagicMock()
            mock_browser_factory.return_value = browser
            # browser.run() wraps the async scraper -- mock it directly
            yield {
                "browser": browser,
                "scrape": browser.run,
                "fail": mock_fail,
                "success": mock_success,
            }

    def test_given_not_listed_error_when_executed_then_returns_ok(self, _mock_deps):
        """Given Keepa returns 'Not listed on Amazon (no LEGO product found)',
        when execute_keepa is called,
        then returns ExecutorResult.ok() -- item genuinely absent, skip."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        _mock_deps["scrape"].return_value = KeepaScrapeResult(
            success=False,
            set_number="10789",
            error="Not listed on Amazon (no LEGO product found for 10789)",
            not_found=True,
        )
        result = execute_keepa(MagicMock(), "10789")
        assert result.success is True

    def test_given_mismatch_error_when_executed_then_returns_permanent_fail(
        self, _mock_deps,
    ):
        """Given Keepa returns 'product title mismatch',
        when execute_keepa is called,
        then returns a permanent fail (no retries -- Amazon returns same wrong product)."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        _mock_deps["scrape"].return_value = KeepaScrapeResult(
            success=False,
            set_number="10786",
            error="Keepa product title mismatch: 'LEGO 10785 Bakey' does not contain 10786",
            mismatch=True,
        )
        result = execute_keepa(MagicMock(), "10786")
        assert result.success is False
        assert result.error is not None
        assert "mismatch" in result.error.lower()
        assert result.permanent is True

    def test_given_mismatch_when_executed_then_does_not_restart_browser(
        self, _mock_deps,
    ):
        """Given a mismatch error (data issue, not browser issue),
        when execute_keepa is called,
        then browser is NOT restarted (preserves session/cookies)."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        _mock_deps["scrape"].return_value = KeepaScrapeResult(
            success=False,
            set_number="10786",
            error="Keepa product title mismatch: wrong product",
            mismatch=True,
        )
        execute_keepa(MagicMock(), "10786")
        _mock_deps["browser"].restart.assert_not_called()

    def test_given_browser_crash_when_executed_then_restarts_browser(
        self, _mock_deps,
    ):
        """Given a browser/page error (not mismatch, not 'not listed'),
        when execute_keepa is called,
        then browser IS restarted for a clean retry."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        _mock_deps["scrape"].return_value = KeepaScrapeResult(
            success=False,
            set_number="10787",
            error="Page.evaluate: Target page has been closed",
        )
        result = execute_keepa(MagicMock(), "10787")
        assert result.success is False
        _mock_deps["browser"].restart.assert_called_once()

    def test_given_exception_during_scrape_when_executed_then_restarts_and_fails(
        self, _mock_deps,
    ):
        """Given browser.run() raises an exception,
        when execute_keepa is called,
        then records failure, restarts browser, and returns fail."""
        from services.scrape_queue.executors.keepa import execute_keepa

        _mock_deps["scrape"].side_effect = RuntimeError("Browser crashed")
        result = execute_keepa(MagicMock(), "10787")
        assert result.success is False
        assert "Browser crashed" in result.error
        _mock_deps["fail"].assert_called_once_with("10787")
        _mock_deps["browser"].restart.assert_called_once()

    def test_given_successful_scrape_when_executed_then_records_success(
        self, _mock_deps,
    ):
        """Given a successful scrape result with product data,
        when execute_keepa is called,
        then records success and returns ok."""
        from services.keepa.types import KeepaProductData, KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        product = KeepaProductData(
            set_number="10787",
            asin="B0TEST",
            title="LEGO 10787 Kitty Fairy",
            keepa_url="https://keepa.com/test",
            scraped_at=datetime.now(timezone.utc),
        )
        _mock_deps["scrape"].return_value = KeepaScrapeResult(
            success=True,
            set_number="10787",
            product_data=product,
        )
        result = execute_keepa(MagicMock(), "10787")
        assert result.success is True
        _mock_deps["success"].assert_called_once_with("10787")

    def test_given_snapshot_insert_fails_when_executed_then_returns_fail(
        self, _mock_deps,
    ):
        """Given scrape succeeds but save_keepa_snapshot raises,
        when execute_keepa is called,
        then returns fail (data not persisted)."""
        from services.keepa.types import KeepaProductData, KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        product = KeepaProductData(
            set_number="10787",
            asin="B0TEST",
            title="LEGO 10787 Kitty Fairy",
            keepa_url="https://keepa.com/test",
            scraped_at=datetime.now(timezone.utc),
        )
        _mock_deps["scrape"].return_value = KeepaScrapeResult(
            success=True,
            set_number="10787",
            product_data=product,
        )
        with patch(
            "services.keepa.repository.save_keepa_snapshot",
            side_effect=Exception("disk full"),
        ):
            result = execute_keepa(MagicMock(), "10787")
        assert result.success is False
        assert "Failed to save" in result.error

    def test_given_all_failures_are_recorded_regardless_of_error_type(
        self, _mock_deps,
    ):
        """Given any non-success result (mismatch, browser crash, not listed),
        when execute_keepa is called,
        then record_keepa_failure is always called for tracking."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        cases = [
            {"error": "Not listed on Amazon", "not_found": True},
            {"error": "Keepa product title mismatch: wrong", "mismatch": True},
            {"error": "Page.evaluate: timeout"},
        ]
        for case in cases:
            _mock_deps["fail"].reset_mock()
            _mock_deps["scrape"].return_value = KeepaScrapeResult(
                success=False,
                set_number="10787",
                error=case["error"],
                not_found=case.get("not_found", False),
                mismatch=case.get("mismatch", False),
            )
            execute_keepa(MagicMock(), "10787")
            _mock_deps["fail"].assert_called_once_with("10787")


# ---------------------------------------------------------------------------
# Scoring: real-world failure scenarios from production logs
# ---------------------------------------------------------------------------


class TestScoreResultProductionScenarios:
    """Given real product titles from production failures, verify scoring
    now correctly ranks the right product above wrong ones."""

    def test_given_10786_wrong_product_10785_when_both_scored_then_right_wins(self):
        """Given search for 10786 returned both the correct 10786 listing
        and a wrong 10785 listing (Gabby's Dollhouse sibling),
        when both are scored,
        then 10786 listing scores higher.

        Production failure: 10785 was selected because 'starts with LEGO' (+20)
        outscored 'contains set number' (was +10)."""
        wrong = _score_result(
            "LEGO Gabby's Dollhouse Bakey with Cakey Fun 10785 Building Toy Set",
            "10786",
        )
        right = _score_result(
            "LEGO Gabby's Dollhouse Gabby & MerCat's Ship 10786 Building Set",
            "10786",
        )
        assert right > wrong

    def test_given_10987_wrong_product_76911_when_both_scored_then_right_wins(self):
        """Given search for 10987 returned an Aston Martin DB5 76911,
        when both are scored,
        then the actual 10987 DUPLO set scores higher.

        Production failure: 'Lego Speed Champions 007 Aston Martin DB5 76911'
        was selected over the correct DUPLO set."""
        wrong = _score_result(
            "Lego Speed Champions 007 Aston Martin DB5 76911 Building Toy Set",
            "10987",
        )
        right = _score_result(
            "LEGO DUPLO 10987 Recycling Truck Building Toy Set",
            "10987",
        )
        assert right > wrong

    def test_given_10984_wrong_product_11036_when_both_scored_then_right_wins(self):
        """Given search for 10984 returned 'LEGO Classic Creative Vehicles 11036',
        when both are scored,
        then the actual 10984 DUPLO set scores higher.

        Production failure: wrong product had 'LEGO' prefix (+20) and
        'building set' keywords (+5) but lacked the set number."""
        wrong = _score_result(
            "LEGO Classic Creative Vehicles 11036 Building Kit",
            "10984",
        )
        right = _score_result(
            "LEGO DUPLO My First 10984 Organic Garden Building Set",
            "10984",
        )
        assert right > wrong

    def test_given_10990_wrong_product_10939_when_both_scored_then_right_wins(self):
        """Given search for 10990 returned 'LEGO DUPLO Jurassic World T. rex 10939',
        when both are scored,
        then the actual 10990 set scores higher.

        Production failure: both are DUPLO sets with similar keywords,
        only the set number distinguishes them."""
        wrong = _score_result(
            "LEGO DUPLO Jurassic World T. rex and Triceratops 10939 Building Toy",
            "10990",
        )
        right = _score_result(
            "LEGO DUPLO Town 10990 Construction Site Building Set",
            "10990",
        )
        assert right > wrong


# ---------------------------------------------------------------------------
# ExecutorResult model: ensure typed results are correct
# ---------------------------------------------------------------------------


class TestExecutorResult:
    """Given various executor outcomes, verify ExecutorResult semantics."""

    def test_given_ok_result_when_checked_then_success_true_no_error(self):
        """Given ExecutorResult.ok(),
        when checked,
        then success is True and error is None."""
        result = ExecutorResult.ok()
        assert result.success is True
        assert result.error is None
        assert result.is_cooldown is False

    def test_given_fail_result_when_checked_then_success_false_with_error(self):
        """Given ExecutorResult.fail('some error'),
        when checked,
        then success is False and error is set."""
        result = ExecutorResult.fail("some error")
        assert result.success is False
        assert result.error == "some error"
        assert result.is_cooldown is False

    def test_given_cooldown_result_when_checked_then_is_cooldown_true(self):
        """Given ExecutorResult.cooldown(3600),
        when checked,
        then is_cooldown is True."""
        result = ExecutorResult.cooldown(3600)
        assert result.success is False
        assert result.is_cooldown is True
        assert result.cooldown_seconds == 3600

    def test_given_zero_cooldown_when_checked_then_is_cooldown_false(self):
        """Given ExecutorResult with cooldown_seconds=0,
        when checked,
        then is_cooldown is False (zero means no cooldown)."""
        result = ExecutorResult(success=False, cooldown_seconds=0)
        assert result.is_cooldown is False


# ---------------------------------------------------------------------------
# Production failure regression: sets that failed unnecessarily
# ---------------------------------------------------------------------------


class TestProductionFailureRegression:
    """Given the specific sets that failed in the 2026-04-02 21:41-21:48 window,
    verify each failure mode is now handled correctly."""

    def test_given_10786_mismatch_when_executed_then_retried_not_swallowed(self):
        """Given set 10786 where Keepa found 10785 instead (title mismatch),
        when execute_keepa processes this,
        then it returns fail (triggering retry) instead of ok (swallowing).

        Before fix: returned ExecutorResult.ok() -- no retry.
        After fix: returns ExecutorResult.fail() -- dispatcher retries up to 3x."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        with (
            patch("services.scrape_queue.executors.keepa._lookup_item_title",
                  return_value="Gabby & MerCat's Ship & Spa"),
            patch("services.browser.get_persistent_browser") as mock_bf,
            patch("services.keepa.scheduler.record_keepa_failure"),
            patch("services.keepa.scheduler.record_keepa_success"),
            patch("config.settings.KEEPA_CONFIG") as cfg,
        ):
            cfg.headless = True
            cfg.locale = "en-US"
            cfg.viewport_width = 1366
            cfg.viewport_height = 768
            browser = MagicMock()
            mock_bf.return_value = browser
            browser.run.return_value = KeepaScrapeResult(
                success=False,
                set_number="10786",
                error="Keepa product title mismatch: 'LEGO Gabby's Dollhouse "
                      "Bakey with Cakey Fun 10785' does not contain 10786",
            )
            result = execute_keepa(MagicMock(), "10786")

        assert result.success is False, (
            "Mismatch should return fail (retry), not ok (swallow)"
        )
        assert result.error is not None

    def test_given_10981_title_only_in_brickeconomy_when_lookup_then_found(self):
        """Given set 10981 'Growing Carrot' exists only in brickeconomy_snapshots,
        when _lookup_item_title is called,
        then returns 'Growing Carrot' via the BrickEconomy fallback."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()

        def side_effect(query, params):
            result = MagicMock()
            if "bricklink_items" in query:
                result.fetchone.return_value = None
            elif "brickeconomy_snapshots" in query:
                result.fetchone.return_value = ("Growing Carrot",)
            else:
                result.fetchone.return_value = None
            return result

        conn.execute.side_effect = side_effect
        title = _lookup_item_title(conn, "10981")
        assert title == "Growing Carrot"

    def test_given_10789_title_used_for_fallback_search(self):
        """Given set 10789 'Spider-Man's Car and Doc Ock' has a title from
        brickeconomy, when no search candidates are found,
        then _click_first_result should attempt title-based search.

        This test verifies the title is passed through from executor to scraper,
        enabling the fallback search path added in _click_first_result."""
        from services.scrape_queue.executors.keepa import _lookup_item_title

        conn = MagicMock()

        def side_effect(query, params):
            result = MagicMock()
            if "bricklink_items" in query:
                result.fetchone.return_value = None
            elif "brickeconomy_snapshots" in query:
                result.fetchone.return_value = ("Spider-Man's Car and Doc Ock",)
            else:
                result.fetchone.return_value = None
            return result

        conn.execute.side_effect = side_effect
        title = _lookup_item_title(conn, "10789")
        assert title is not None, (
            "10789 should have a title from a trusted source for fallback search"
        )
        assert "Spider-Man" in title

    def test_given_10996_browser_crash_when_executed_then_retried(self):
        """Given set 10996 where browser crashed ('Target page has been closed'),
        when execute_keepa processes this,
        then it returns fail and restarts browser for retry.

        Production log: 'Page.evaluate: Target page, context or browser
        has been closed'."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        with (
            patch("services.scrape_queue.executors.keepa._lookup_item_title",
                  return_value=None),
            patch("services.browser.get_persistent_browser") as mock_bf,
            patch("services.keepa.scheduler.record_keepa_failure"),
            patch("services.keepa.scheduler.record_keepa_success"),
            patch("config.settings.KEEPA_CONFIG") as cfg,
        ):
            cfg.headless = True
            cfg.locale = "en-US"
            cfg.viewport_width = 1366
            cfg.viewport_height = 768
            browser = MagicMock()
            mock_bf.return_value = browser
            browser.run.return_value = KeepaScrapeResult(
                success=False,
                set_number="10996",
                error="Page.evaluate: Target page, context or browser has been closed",
            )
            result = execute_keepa(MagicMock(), "10996")

        assert result.success is False
        browser.restart.assert_called_once()

    def test_given_not_listed_still_treated_as_ok(self):
        """Given set where Keepa genuinely has no Amazon listing,
        when execute_keepa processes the 'Not listed' error,
        then it still returns ok (no retry needed -- item truly absent).

        This verifies we didn't break the intentional skip behavior
        while fixing the mismatch handling."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        with (
            patch("services.scrape_queue.executors.keepa._lookup_item_title",
                  return_value=None),
            patch("services.browser.get_persistent_browser") as mock_bf,
            patch("services.keepa.scheduler.record_keepa_failure"),
            patch("services.keepa.scheduler.record_keepa_success"),
            patch("config.settings.KEEPA_CONFIG") as cfg,
        ):
            cfg.headless = True
            cfg.locale = "en-US"
            cfg.viewport_width = 1366
            cfg.viewport_height = 768
            browser = MagicMock()
            mock_bf.return_value = browser
            browser.run.return_value = KeepaScrapeResult(
                success=False,
                set_number="10935",
                error="Not listed on Amazon (no LEGO product found for 10935)",
                not_found=True,
            )
            result = execute_keepa(MagicMock(), "10935")

        assert result.success is True, (
            "'Not listed' should still be ok -- item genuinely absent"
        )

    def test_given_chart_sweep_failed_when_executed_then_retried(self):
        """Given 'Chart tooltip sweep failed' error,
        when execute_keepa processes this,
        then it returns fail (browser issue, not data issue) for retry."""
        from services.keepa.types import KeepaScrapeResult
        from services.scrape_queue.executors.keepa import execute_keepa

        with (
            patch("services.scrape_queue.executors.keepa._lookup_item_title",
                  return_value=None),
            patch("services.browser.get_persistent_browser") as mock_bf,
            patch("services.keepa.scheduler.record_keepa_failure"),
            patch("services.keepa.scheduler.record_keepa_success"),
            patch("config.settings.KEEPA_CONFIG") as cfg,
        ):
            cfg.headless = True
            cfg.locale = "en-US"
            cfg.viewport_width = 1366
            cfg.viewport_height = 768
            browser = MagicMock()
            mock_bf.return_value = browser
            browser.run.return_value = KeepaScrapeResult(
                success=False,
                set_number="10787",
                error="Chart tooltip sweep failed",
            )
            result = execute_keepa(MagicMock(), "10787")

        assert result.success is False
        browser.restart.assert_called_once()
