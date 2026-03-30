"""GWT tests for Shopee saturation scorer.

Covers: relevance filtering, listing score, seller score, price competition
score, level classification, and end-to-end saturation computation.
"""

import pytest

from services.shopee.parser import ShopeeProduct
from services.shopee.saturation_scorer import (
    _classify,
    _is_relevant,
    _listing_score,
    _price_competition_score,
    _seller_score,
    compute_saturation,
    filter_relevant_products,
)
from services.shopee.saturation_types import SaturationLevel


def _p(
    set_number: str = "75192",
    price: str = "RM599.00",
    shop: str | None = "shop_a",
    product_url: str | None = None,
    title: str | None = None,
) -> ShopeeProduct:
    """Create a product with the set number in the title."""
    t = title or f"LEGO {set_number} Set"
    url = product_url or f"https://shopee.com.my/{t}-i.123.456"
    return ShopeeProduct(
        title=t,
        price_display=price,
        sold_count=None,
        rating=None,
        shop_name=shop,
        product_url=url,
        image_url=None,
    )


# ---------------------------------------------------------------------------
# Relevance filter -- ensures only listings for the target set are counted
# ---------------------------------------------------------------------------


class TestRelevanceFilter:
    def test_given_title_with_set_number_when_checked_then_relevant(self):
        p = _p(title="LEGO 10281 Bonsai Tree")
        assert _is_relevant(p, "10281") is True

    def test_given_title_without_set_number_when_checked_then_not_relevant(self):
        p = _p(title="Bonsai Building Blocks Compatible")
        assert _is_relevant(p, "10281") is False

    def test_given_set_number_anywhere_in_title_when_checked_then_relevant(self):
        p = _p(title="Creator Expert 10281 Bonsai")
        assert _is_relevant(p, "10281") is True

    def test_given_lowercase_title_when_checked_then_still_matches(self):
        p = _p(title="lego 10281 bonsai tree")
        assert _is_relevant(p, "10281") is True

    def test_given_mixed_products_when_filtered_then_only_relevant_kept(self):
        products = (
            _p(title="LEGO 10281 Bonsai Tree"),
            _p(title="Random Plant Toy"),
            _p(title="10281 LEGO Creator Expert"),
        )
        filtered = filter_relevant_products(products, "10281")
        assert len(filtered) == 2

    def test_given_irrelevant_products_when_computed_then_excluded_from_score(self):
        """Irrelevant listings should not affect saturation score."""
        products = (
            _p(title="LEGO 10281 Bonsai Tree", price="RM219.90", shop="a"),
            _p(title="Compatible Bonsai Blocks", price="RM50.00", shop="b"),
            _p(title="LEGO 10281 Creator Expert", price="RM199.00", shop="c"),
            _p(title="Random Plant Toy", price="RM30.00", shop="d"),
        )
        snapshot = compute_saturation("10281", "LEGO 10281", products)
        assert snapshot.listings_count == 2  # Only 2 have "10281"
        assert snapshot.unique_sellers == 2


# ---------------------------------------------------------------------------
# Listing score (0-60 points based on number of listings)
# ---------------------------------------------------------------------------


class TestListingScore:
    def test_given_zero_listings_when_scored_then_zero_points(self):
        assert _listing_score(0) == 0.0

    def test_given_cap_listings_when_scored_then_max_points(self):
        assert _listing_score(50) == 60.0

    def test_given_above_cap_when_scored_then_capped_at_max(self):
        assert _listing_score(100) == 60.0

    def test_given_half_cap_when_scored_then_proportional(self):
        assert _listing_score(25) == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Seller score (0-25 points based on unique sellers)
# ---------------------------------------------------------------------------


class TestSellerScore:
    def test_given_zero_sellers_when_scored_then_zero_points(self):
        assert _seller_score(0) == 0.0

    def test_given_cap_sellers_when_scored_then_max_points(self):
        assert _seller_score(20) == 25.0

    def test_given_above_cap_when_scored_then_capped_at_max(self):
        assert _seller_score(50) == 25.0


# ---------------------------------------------------------------------------
# Price competition score (0-15 points based on price spread)
# ---------------------------------------------------------------------------


class TestPriceCompetitionScore:
    def test_given_no_prices_when_scored_then_zero_points(self):
        assert _price_competition_score([]) == 0.0

    def test_given_single_price_when_scored_then_zero_points(self):
        assert _price_competition_score([10000]) == 0.0

    def test_given_identical_prices_when_scored_then_max_points(self):
        """Identical prices = 0% spread = price war = max competition."""
        score = _price_competition_score([10000, 10000, 10000])
        assert score == 15.0

    def test_given_wide_spread_when_scored_then_zero_points(self):
        """100% spread exceeds 80% threshold = 0 competition points."""
        score = _price_competition_score([5000, 15000])
        assert score == 0.0

    def test_given_moderate_spread_when_scored_then_partial_points(self):
        """50% spread is between 20% and 80% = interpolated score."""
        score = _price_competition_score([7500, 12500])
        assert 0 < score < 15


# ---------------------------------------------------------------------------
# Level classification
# ---------------------------------------------------------------------------


class TestClassify:
    def test_given_score_below_25_when_classified_then_very_low(self):
        assert _classify(10) == SaturationLevel.VERY_LOW

    def test_given_score_25_to_49_when_classified_then_low(self):
        assert _classify(30) == SaturationLevel.LOW

    def test_given_score_50_to_74_when_classified_then_moderate(self):
        assert _classify(60) == SaturationLevel.MODERATE

    def test_given_score_75_plus_when_classified_then_high(self):
        assert _classify(80) == SaturationLevel.HIGH

    def test_given_boundary_25_when_classified_then_low(self):
        assert _classify(25) == SaturationLevel.LOW

    def test_given_boundary_50_when_classified_then_moderate(self):
        assert _classify(50) == SaturationLevel.MODERATE

    def test_given_boundary_75_when_classified_then_high(self):
        assert _classify(75) == SaturationLevel.HIGH


# ---------------------------------------------------------------------------
# End-to-end saturation computation
# ---------------------------------------------------------------------------


class TestComputeSaturation:
    def test_given_no_products_when_computed_then_zero_saturation(self):
        snapshot = compute_saturation("75192", "LEGO 75192", ())
        assert snapshot.listings_count == 0
        assert snapshot.unique_sellers == 0
        assert snapshot.saturation_score == 0.0
        assert snapshot.saturation_level == SaturationLevel.VERY_LOW
        assert snapshot.min_price_cents is None

    def test_given_few_products_when_computed_then_low_saturation(self):
        products = tuple(
            _p(set_number="75192", shop=f"shop_{i}", price="RM599.00")
            for i in range(5)
        )
        snapshot = compute_saturation("75192", "LEGO 75192", products)
        assert snapshot.listings_count == 5
        assert snapshot.unique_sellers == 5
        assert snapshot.saturation_level == SaturationLevel.LOW
        assert snapshot.avg_price_cents == 59900
        assert snapshot.set_number == "75192"
        assert snapshot.search_query == "LEGO 75192"

    def test_given_full_page_when_computed_then_high_saturation(self):
        """50 listings from 50 sellers with same price = highly saturated."""
        products = tuple(
            _p(
                set_number="42151",
                shop=f"shop_{i}",
                price="RM299.00",
                product_url=f"https://shopee.com.my/item-i.{i}.456",
            )
            for i in range(50)
        )
        snapshot = compute_saturation("42151", "LEGO 42151", products)
        assert snapshot.listings_count == 50
        assert snapshot.unique_sellers == 50
        assert snapshot.saturation_level == SaturationLevel.HIGH
        assert snapshot.saturation_score >= 75

    def test_given_same_seller_when_computed_then_one_unique(self):
        """Multiple listings from same seller counted as 1 unique seller."""
        products = tuple(
            _p(
                set_number="10312",
                shop="same_shop",
                price="RM100.00",
                product_url=f"https://shopee.com.my/item-i.{i}.456",
            )
            for i in range(10)
        )
        snapshot = compute_saturation("10312", "LEGO 10312", products)
        assert snapshot.unique_sellers == 1

    def test_given_none_shop_names_when_computed_then_excluded_from_count(self):
        products = (
            _p(set_number="10312", shop=None, product_url="https://shopee.com.my/a-i.1.1"),
            _p(set_number="10312", shop="real_shop", product_url="https://shopee.com.my/b-i.2.2"),
        )
        snapshot = compute_saturation("10312", "LEGO 10312", products)
        assert snapshot.unique_sellers == 1

    def test_given_varied_prices_when_computed_then_correct_statistics(self):
        products = (
            _p(set_number="10312", price="RM100.00", shop="a", product_url="https://shopee.com.my/a-i.1.1"),
            _p(set_number="10312", price="RM200.00", shop="b", product_url="https://shopee.com.my/b-i.2.2"),
            _p(set_number="10312", price="RM300.00", shop="c", product_url="https://shopee.com.my/c-i.3.3"),
        )
        snapshot = compute_saturation("10312", "LEGO 10312", products)
        assert snapshot.min_price_cents == 10000
        assert snapshot.max_price_cents == 30000
        assert snapshot.avg_price_cents == 20000
        assert snapshot.median_price_cents == 20000
        assert snapshot.price_spread_pct is not None
        assert snapshot.price_spread_pct > 0

    def test_given_extreme_listings_when_computed_then_score_capped_at_100(self):
        products = tuple(
            _p(
                set_number="99999",
                shop=f"shop_{i}",
                price="RM100.00",
                product_url=f"https://shopee.com.my/item-i.{i}.456",
            )
            for i in range(200)
        )
        snapshot = compute_saturation("99999", "LEGO 99999", products)
        assert snapshot.saturation_score <= 100.0

    def test_given_products_when_computed_then_snapshot_is_frozen(self):
        snapshot = compute_saturation("75192", "LEGO 75192", ())
        with pytest.raises(AttributeError):
            snapshot.saturation_score = 99.0  # type: ignore[misc]

    def test_given_unparseable_prices_when_computed_then_no_price_stats(self):
        products = (
            _p(set_number="75192", title="LEGO 75192 A", price="FREE", shop="a"),
            _p(set_number="75192", title="LEGO 75192 B", price="", shop="b"),
        )
        snapshot = compute_saturation("75192", "LEGO 75192", products)
        assert snapshot.listings_count == 2
        assert snapshot.min_price_cents is None
        assert snapshot.avg_price_cents is None
