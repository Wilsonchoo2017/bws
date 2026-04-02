"""GWT tests for Keepa set number matching helpers."""

import pytest

from services.keepa.scraper import _bare_set_number, _title_contains_set_number


class TestBareSetNumber:
    """Given set numbers with various formats, verify suffix stripping."""

    def test_given_suffixed_number_when_stripped_then_bare_returned(self):
        """Given '60305-1',
        when _bare_set_number is called,
        then returns '60305'."""
        assert _bare_set_number("60305-1") == "60305"

    def test_given_bare_number_when_stripped_then_unchanged(self):
        """Given '60305' (no suffix),
        when _bare_set_number is called,
        then returns '60305'."""
        assert _bare_set_number("60305") == "60305"

    def test_given_multi_suffix_when_stripped_then_first_part_returned(self):
        """Given '10300-2-1' (unusual format),
        when _bare_set_number is called,
        then returns '10300'."""
        assert _bare_set_number("10300-2-1") == "10300"


class TestTitleContainsSetNumber:
    """Given product titles and set numbers, verify matching logic."""

    def test_given_title_with_set_number_when_checked_then_true(self):
        """Given title 'LEGO 60305 Car Transporter' and set '60305-1',
        when _title_contains_set_number is called,
        then returns True."""
        assert _title_contains_set_number(
            "LEGO 60305 Car Transporter", "60305-1"
        ) is True

    def test_given_title_without_set_number_when_checked_then_false(self):
        """Given title 'LEGO 76244 Batman Batmobile' and set '122222-1',
        when _title_contains_set_number is called,
        then returns False (wrong product)."""
        assert _title_contains_set_number(
            "LEGO 76244 Batman Batmobile", "122222-1"
        ) is False

    def test_given_none_title_when_checked_then_false(self):
        """Given None title,
        when _title_contains_set_number is called,
        then returns False."""
        assert _title_contains_set_number(None, "60305-1") is False

    def test_given_empty_title_when_checked_then_false(self):
        """Given empty string title,
        when _title_contains_set_number is called,
        then returns False."""
        assert _title_contains_set_number("", "60305-1") is False

    def test_given_case_insensitive_title_when_checked_then_true(self):
        """Given title with mixed case containing the number,
        when _title_contains_set_number is called,
        then returns True (case insensitive)."""
        assert _title_contains_set_number(
            "lego 60305 car transporter", "60305-1"
        ) is True

    def test_given_bare_set_number_when_checked_then_matches(self):
        """Given set number without suffix '60305',
        when _title_contains_set_number is called,
        then still matches correctly."""
        assert _title_contains_set_number(
            "LEGO 60305 Car Transporter", "60305"
        ) is True

    def test_given_high_number_foil_pack_when_checked_against_wrong_product_then_false(self):
        """Given a high set number like 122222 and a random Amazon product title,
        when _title_contains_set_number is called,
        then returns False."""
        assert _title_contains_set_number(
            "LEGO Jurassic World Velociraptor Chase 75932", "122222-1"
        ) is False
