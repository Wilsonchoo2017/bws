"""Shared fixtures for BWS tests."""

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def make_item():
    """Factory fixture to create lego_items dict with optional overrides."""

    def _make(set_number: str = "75192", **overrides) -> dict:
        defaults = {
            "set_number": set_number,
            "title": None,
            "theme": None,
            "year_released": None,
            "year_retired": None,
            "parts_count": None,
            "image_url": None,
            "weight": None,
            "retiring_soon": None,
        }
        return {**defaults, **overrides}

    return _make
