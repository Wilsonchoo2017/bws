"""GWT tests for excluded packaging detection and item deletion."""

import pytest

from services.brickeconomy.parser import (
    EXCLUDED_PACKAGING,
    is_excluded_packaging,
)


class TestIsExcludedPackaging:
    """Given various packaging values, verify exclusion logic."""

    @pytest.mark.parametrize("packaging", sorted(EXCLUDED_PACKAGING))
    def test_given_excluded_type_when_checked_then_returns_true(self, packaging: str):
        """Given a known excluded packaging type,
        when is_excluded_packaging is called,
        then it returns True."""
        assert is_excluded_packaging(packaging) is True

    def test_given_box_when_checked_then_returns_false(self):
        """Given standard 'Box' packaging,
        when is_excluded_packaging is called,
        then it returns False."""
        assert is_excluded_packaging("Box") is False

    def test_given_none_when_checked_then_returns_false(self):
        """Given None packaging (most standard sets),
        when is_excluded_packaging is called,
        then it returns False."""
        assert is_excluded_packaging(None) is False

    def test_given_empty_string_when_checked_then_returns_false(self):
        """Given empty string packaging,
        when is_excluded_packaging is called,
        then it returns False."""
        assert is_excluded_packaging("") is False

    def test_given_whitespace_padded_excluded_type_when_checked_then_returns_true(self):
        """Given excluded type with leading/trailing whitespace,
        when is_excluded_packaging is called,
        then it still returns True (stripped)."""
        assert is_excluded_packaging("  Foil Pack  ") is True

    def test_given_unknown_packaging_when_checked_then_returns_false(self):
        """Given an unknown packaging type,
        when is_excluded_packaging is called,
        then it returns False."""
        assert is_excluded_packaging("Carton") is False
