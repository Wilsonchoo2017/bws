"""Tests for BrickLink minifigure parser functions.

GWT coverage for minifig_count, dimensions, has_instructions extraction,
and minifigure inventory page parsing.
"""

import pytest

from services.bricklink.parser import (
    build_minifig_inventory_url,
    parse_item_info,
    parse_minifig_inventory,
)


def _wrap_html(body: str) -> str:
    """Wrap body content in minimal valid HTML."""
    return f"<html><head></head><body>{body}</body></html>"


def _make_item_html(
    *,
    parts_text: str | None = None,
    minifig_text: str | None = None,
    dimensions_text: str | None = None,
    instructions_text: str | None = None,
    year_released: int | None = None,
) -> str:
    """Build a minimal BrickLink catalog HTML page."""
    parts = []
    if year_released:
        parts.append(f"<span>Year Released: {year_released}</span>")
    if parts_text:
        parts.append(f"<span>{parts_text}</span>")
    if minifig_text:
        parts.append(f"<span>{minifig_text}</span>")
    if dimensions_text:
        parts.append(f"<span>{dimensions_text}</span>")
    if instructions_text:
        parts.append(f"<span>{instructions_text}</span>")
    return _wrap_html("\n".join(parts))


class TestExtractMinifigCount:
    """GWT: _extract_minifig_count via parse_item_info."""

    def test_standard_minifig_count(self):
        """Given HTML with '2 Minifigures', returns 2."""
        html = _make_item_html(minifig_text="2 Minifigures")
        result = parse_item_info(html)
        assert result["minifig_count"] == 2

    def test_single_minifigure(self):
        """Given HTML with '1 Minifigure' (singular), returns 1."""
        html = _make_item_html(minifig_text="1 Minifigure")
        result = parse_item_info(html)
        assert result["minifig_count"] == 1

    def test_large_minifig_count(self):
        """Given HTML with '12 Minifigures', returns 12."""
        html = _make_item_html(minifig_text="12 Minifigures")
        result = parse_item_info(html)
        assert result["minifig_count"] == 12

    def test_no_minifigs(self):
        """Given HTML without minifig text, returns None."""
        html = _make_item_html(parts_text="305 Parts")
        result = parse_item_info(html)
        assert result["minifig_count"] is None

    def test_minifigs_not_confused_with_parts(self):
        """Given both '305 Parts' and '3 Minifigures', returns correct counts."""
        html = _make_item_html(parts_text="305 Parts", minifig_text="3 Minifigures")
        result = parse_item_info(html)
        assert result["parts_count"] == 305
        assert result["minifig_count"] == 3

    def test_excessive_minifig_count_rejected(self):
        """Given count > 100, returns None."""
        html = _make_item_html(minifig_text="150 Minifigures")
        result = parse_item_info(html)
        assert result["minifig_count"] is None


class TestExtractDimensions:
    """GWT: _extract_dimensions via parse_item_info."""

    def test_standard_dimensions(self):
        """Given 'Item Dim.: 26.2 x 14 x 7.2 cm', extracts correctly."""
        html = _make_item_html(dimensions_text="Item Dim.: 26.2 x 14 x 7.2 cm")
        result = parse_item_info(html)
        assert result["dimensions"] == "26.2 x 14 x 7.2 cm"

    def test_integer_dimensions(self):
        """Given dimensions with whole numbers, extracts correctly."""
        html = _make_item_html(dimensions_text="Item Dim.: 48 x 28 x 6 cm")
        result = parse_item_info(html)
        assert result["dimensions"] == "48 x 28 x 6 cm"

    def test_no_dimensions(self):
        """Given HTML without dimension text, returns None."""
        html = _make_item_html(parts_text="305 Parts")
        result = parse_item_info(html)
        assert result["dimensions"] is None


class TestExtractHasInstructions:
    """GWT: _extract_has_instructions via parse_item_info."""

    def test_instructions_yes(self):
        """Given 'Instructions: Yes', returns True."""
        html = _make_item_html(instructions_text="Instructions: Yes")
        result = parse_item_info(html)
        assert result["has_instructions"] is True

    def test_instructions_no(self):
        """Given 'Instructions: No', returns False."""
        html = _make_item_html(instructions_text="Instructions: No")
        result = parse_item_info(html)
        assert result["has_instructions"] is False

    def test_no_instructions_field(self):
        """Given HTML without instructions text, returns None."""
        html = _make_item_html(parts_text="305 Parts")
        result = parse_item_info(html)
        assert result["has_instructions"] is None


class TestBuildMinifigInventoryUrl:
    """GWT: build_minifig_inventory_url."""

    def test_builds_correct_url(self):
        """Given item_id '77256-1', returns correct inventory URL."""
        url = build_minifig_inventory_url("77256-1")
        assert url == "https://www.bricklink.com/catalogItemInv.asp?S=77256-1&viewItemType=M"

    def test_different_item_id(self):
        """Given item_id '75192-1', returns correct URL."""
        url = build_minifig_inventory_url("75192-1")
        assert url == "https://www.bricklink.com/catalogItemInv.asp?S=75192-1&viewItemType=M"


class TestParseMinifigInventory:
    """GWT: parse_minifig_inventory."""

    def test_parses_minifig_links(self):
        """Given inventory page with minifig links, extracts minifig IDs."""
        html = _wrap_html("""
        <table>
            <tr>
                <td><img src="https://img.bricklink.com/ItemImage/MN/0/sc139.png" /></td>
                <td><a href="/v2/catalog/catalogitem.page?M=sc139">Spider-Man</a></td>
                <td>1</td>
            </tr>
            <tr>
                <td><img src="https://img.bricklink.com/ItemImage/MN/0/sc140.png" /></td>
                <td><a href="/v2/catalog/catalogitem.page?M=sc140">Green Goblin</a></td>
                <td>1</td>
            </tr>
        </table>
        """)
        result = parse_minifig_inventory(html)
        assert len(result) == 2
        assert result[0].minifig_id == "sc139"
        assert result[0].name == "Spider-Man"
        assert result[0].quantity == 1
        assert result[1].minifig_id == "sc140"
        assert result[1].name == "Green Goblin"

    def test_empty_inventory(self):
        """Given page with no minifig links, returns empty list."""
        html = _wrap_html("<p>No minifigures in this set.</p>")
        result = parse_minifig_inventory(html)
        assert result == []

    def test_extracts_quantity(self):
        """Given minifig with quantity > 1, extracts correct quantity."""
        html = _wrap_html("""
        <table>
            <tr>
                <td><img src="https://img.bricklink.com/ItemImage/MN/0/sw0001.png" /></td>
                <td><a href="/v2/catalog/catalogitem.page?M=sw0001">Stormtrooper</a></td>
                <td>3</td>
            </tr>
        </table>
        """)
        result = parse_minifig_inventory(html)
        assert len(result) == 1
        assert result[0].quantity == 3

    def test_deduplicates_minifig_ids(self):
        """Given duplicate minifig links, keeps only the first occurrence."""
        html = _wrap_html("""
        <table>
            <tr>
                <td><a href="/v2/catalog/catalogitem.page?M=sc139">Spider-Man</a></td>
                <td>1</td>
            </tr>
            <tr>
                <td><a href="/v2/catalog/catalogitem.page?M=sc139">Spider-Man (dup)</a></td>
                <td>1</td>
            </tr>
        </table>
        """)
        result = parse_minifig_inventory(html)
        assert len(result) == 1
        assert result[0].minifig_id == "sc139"

    def test_extracts_image_url(self):
        """Given minifig with BrickLink image, extracts and normalizes URL."""
        html = _wrap_html("""
        <table>
            <tr>
                <td><img src="//img.bricklink.com/ItemImage/MN/0/sc139.png" /></td>
                <td><a href="/v2/catalog/catalogitem.page?M=sc139">Spider-Man</a></td>
                <td>1</td>
            </tr>
        </table>
        """)
        result = parse_minifig_inventory(html)
        assert len(result) == 1
        assert result[0].image_url == "https://img.bricklink.com/ItemImage/MN/0/sc139.png"
