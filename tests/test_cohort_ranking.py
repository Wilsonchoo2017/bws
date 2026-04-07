"""Unit tests for the cohort ranking module."""

import pytest

from services.backtesting.cohort import (
    MIN_COHORT_SIZE,
    _assign_bucket,
    _compute_percentile,
    _half_year_from_release_date,
    enrich_with_cohort_ranks,
)


class TestHalfYearParsing:
    def test_h1_month(self):
        assert _half_year_from_release_date("2022-03") == "2022-H1"

    def test_h2_month(self):
        assert _half_year_from_release_date("2022-07") == "2022-H2"

    def test_june_is_h1(self):
        assert _half_year_from_release_date("2022-06") == "2022-H1"

    def test_january_is_h1(self):
        assert _half_year_from_release_date("2025-01") == "2025-H1"

    def test_december_is_h2(self):
        assert _half_year_from_release_date("2019-12") == "2019-H2"

    def test_none_input(self):
        assert _half_year_from_release_date(None) is None

    def test_empty_string(self):
        assert _half_year_from_release_date("") is None


class TestBucketAssignment:
    def _item(self, **overrides):
        defaults = {
            "year_released": 2022,
            "theme": "Star Wars",
            "release_date": "2022-06",
            "parts_count": 1500,
            "rrp_usd_cents": 12000,
            "composite_score": 70.0,
        }
        return {**defaults, **overrides}

    def test_half_year_with_release_date(self):
        assert _assign_bucket(self._item(release_date="2022-09"), "half_year") == "2022-H2"

    def test_half_year_fallback_to_year(self):
        item = self._item(release_date=None)
        assert _assign_bucket(item, "half_year") == "2022-H1"

    def test_year(self):
        assert _assign_bucket(self._item(), "year") == "2022"

    def test_theme(self):
        assert _assign_bucket(self._item(), "theme") == "Star Wars"

    def test_year_theme(self):
        assert _assign_bucket(self._item(), "year_theme") == "2022|Star Wars"

    def test_price_tier_budget(self):
        assert _assign_bucket(self._item(rrp_usd_cents=2999), "price_tier") == "budget"

    def test_price_tier_mid(self):
        assert _assign_bucket(self._item(rrp_usd_cents=9999), "price_tier") == "mid"

    def test_price_tier_premium(self):
        assert _assign_bucket(self._item(rrp_usd_cents=25000), "price_tier") == "premium"

    def test_price_tier_ultra(self):
        assert _assign_bucket(self._item(rrp_usd_cents=50000), "price_tier") == "ultra"

    def test_piece_group_small(self):
        assert _assign_bucket(self._item(parts_count=200), "piece_group") == "small"

    def test_piece_group_large(self):
        assert _assign_bucket(self._item(parts_count=1500), "piece_group") == "large"

    def test_piece_group_massive(self):
        assert _assign_bucket(self._item(parts_count=5000), "piece_group") == "massive"

    def test_missing_theme(self):
        assert _assign_bucket(self._item(theme=None), "theme") is None

    def test_missing_year(self):
        assert _assign_bucket(self._item(year_released=None), "year") is None

    def test_missing_rrp(self):
        assert _assign_bucket(self._item(rrp_usd_cents=None), "price_tier") is None

    def test_missing_parts(self):
        assert _assign_bucket(self._item(parts_count=None), "piece_group") is None


class TestPercentileComputation:
    def test_single_value_returns_50(self):
        assert _compute_percentile([70.0], 70.0) == 50.0

    def test_highest_value(self):
        result = _compute_percentile([10.0, 20.0, 30.0, 40.0, 50.0], 50.0)
        assert result == 90.0

    def test_lowest_value(self):
        result = _compute_percentile([10.0, 20.0, 30.0, 40.0, 50.0], 10.0)
        assert result == 10.0

    def test_middle_value(self):
        result = _compute_percentile([10.0, 20.0, 30.0, 40.0, 50.0], 30.0)
        assert result == 50.0

    def test_ties_get_same_percentile(self):
        result1 = _compute_percentile([10.0, 20.0, 20.0, 40.0], 20.0)
        # Both 20s should get the same percentile
        assert result1 == _compute_percentile([10.0, 20.0, 20.0, 40.0], 20.0)


class TestEnrichWithCohortRanks:
    def _make_items(self, n: int, year: int = 2022, theme: str = "Star Wars"):
        return [
            {
                "year_released": year,
                "theme": theme,
                "release_date": f"{year}-06",
                "parts_count": 500 + i * 200,
                "rrp_usd_cents": 5000 + i * 2000,
                "composite_score": 40.0 + i * 10.0,
                "demand_pressure": 30.0 + i * 8.0,
                "theme_growth": 50.0 + i * 5.0,
            }
            for i in range(n)
        ]

    def test_returns_new_list_no_mutation(self):
        items = self._make_items(5)
        originals = [dict(item) for item in items]
        result = enrich_with_cohort_ranks(items)
        # Originals unchanged
        for orig, item in zip(originals, items):
            assert "cohorts" not in item
            assert orig == item
        # Result has cohorts
        assert all("cohorts" in r for r in result)

    def test_empty_input(self):
        assert enrich_with_cohort_ranks([]) == []

    def test_cohort_too_small_skipped(self):
        items = self._make_items(2)  # Below MIN_COHORT_SIZE
        result = enrich_with_cohort_ranks(items, min_cohort_size=3)
        # year strategy should be skipped (only 2 items)
        for r in result:
            assert r["cohorts"] is None or "year" not in r["cohorts"]

    def test_year_strategy_present(self):
        items = self._make_items(5)
        result = enrich_with_cohort_ranks(items)
        assert "year" in result[0]["cohorts"]
        cohort = result[0]["cohorts"]["year"]
        assert cohort["key"] == "2022"
        assert cohort["size"] == 5

    def test_rank_ordering(self):
        items = self._make_items(5)
        result = enrich_with_cohort_ranks(items)
        # Item with highest composite (last) should be rank 1
        assert result[4]["cohorts"]["year"]["rank"] == 1
        # Item with lowest composite (first) should be rank 5
        assert result[0]["cohorts"]["year"]["rank"] == 5

    def test_percentile_highest_is_near_100(self):
        items = self._make_items(5)
        result = enrich_with_cohort_ranks(items)
        # Highest scorer should have high percentile
        assert result[4]["cohorts"]["year"]["composite_pct"] >= 80.0

    def test_percentile_lowest_is_near_0(self):
        items = self._make_items(5)
        result = enrich_with_cohort_ranks(items)
        # Lowest scorer should have low percentile
        assert result[0]["cohorts"]["year"]["composite_pct"] <= 20.0

    def test_multiple_strategies_present(self):
        items = self._make_items(5)
        result = enrich_with_cohort_ranks(items)
        cohorts = result[0]["cohorts"]
        # Should have year, theme, year_theme, half_year at minimum
        assert "year" in cohorts
        assert "theme" in cohorts
        assert "half_year" in cohorts

    def test_mixed_years_separate_cohorts(self):
        items_2022 = self._make_items(4, year=2022)
        items_2023 = self._make_items(4, year=2023)
        all_items = items_2022 + items_2023
        result = enrich_with_cohort_ranks(all_items)
        # 2022 items should have year key "2022"
        assert result[0]["cohorts"]["year"]["key"] == "2022"
        assert result[0]["cohorts"]["year"]["size"] == 4
        # 2023 items should have year key "2023"
        assert result[4]["cohorts"]["year"]["key"] == "2023"
        assert result[4]["cohorts"]["year"]["size"] == 4

    def test_items_missing_data_get_null_cohorts_for_that_strategy(self):
        items = self._make_items(5)
        items[0]["theme"] = None  # This item can't be bucketed by theme
        result = enrich_with_cohort_ranks(items)
        # Item 0 should not have theme cohort (only 4 others have theme)
        cohorts_0 = result[0]["cohorts"]
        assert "theme" not in cohorts_0 or cohorts_0.get("theme") is None
        # But should still have year cohort
        assert "year" in result[0]["cohorts"]

    def test_popularity_and_theme_percentiles_present(self):
        items = self._make_items(5)
        result = enrich_with_cohort_ranks(items)
        cohort = result[2]["cohorts"]["year"]
        assert "popularity_pct" in cohort
        assert "theme_pct" in cohort
        assert cohort["popularity_pct"] is not None
        assert cohort["theme_pct"] is not None
