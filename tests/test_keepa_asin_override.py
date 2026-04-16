"""Verify the Keepa scraper's manual ASIN override path.

Context: for sets where Keepa's search ranks the real product below the
top-5 candidate cap, or where the Amazon title doesn't contain the bare
set number (so the title validator rejects the match), a manual
override lets us pin the correct ASIN. The scraper should then navigate
directly to the product page and skip both search and title validation.
"""

from __future__ import annotations

from services.keepa.scraper import _KEEPA_ASIN_OVERRIDES, _bare_set_number


class TestAsinOverrideRegistry:
    """The override map is a small curated dict."""

    def test_71808_has_known_override(self):
        """Given 71808 (Ninjago Kai's Elemental Fire Mech),
        when looking up the override,
        then it resolves to the known-correct ASIN."""
        assert _KEEPA_ASIN_OVERRIDES.get("71808") == "B0CGY44HYD"

    def test_bare_set_number_strips_variant_suffix(self):
        """Override lookup is keyed by bare set number; the scraper
        strips -1 / -2 variants via _bare_set_number before lookup."""
        assert _bare_set_number("71808") == "71808"
        assert _bare_set_number("71808-1") == "71808"
        assert _bare_set_number("71808-2") == "71808"

    def test_non_overridden_sets_return_none(self):
        """Given a random set number with no override,
        when looking up,
        then dict returns None (scraper falls through to search)."""
        assert _KEEPA_ASIN_OVERRIDES.get("99999999") is None


class TestOverrideProductUrl:
    """Override paths build a direct product URL, not a search URL."""

    def test_product_url_shape_for_71808(self):
        """Given the override ASIN for 71808,
        when the scraper builds the nav URL,
        then it points at Keepa's product page (domain=1 for Amazon US)."""
        from services.keepa.scraper import KEEPA_BASE
        asin = _KEEPA_ASIN_OVERRIDES["71808"]
        url = f"{KEEPA_BASE}/#!product/1-{asin}"
        assert url == "https://keepa.com/#!product/1-B0CGY44HYD"
