"""Tests for BrickLink parser parts_count and theme extraction.

Covers GWT #1-17: parser-level extraction of parts_count and theme
from BrickLink catalog HTML.
"""

import pytest

from services.bricklink.parser import (
    parse_full_item,
    parse_item_info,
)


def _wrap_html(body: str) -> str:
    """Wrap body content in minimal valid HTML."""
    return f"<html><head></head><body>{body}</body></html>"


def _make_item_html(
    *,
    title: str | None = None,
    parts_text: str | None = None,
    theme_js: str | None = None,
    breadcrumbs: list[str] | None = None,
    weight: str | None = None,
    year_released: int | None = None,
) -> str:
    """Build a minimal BrickLink catalog HTML page with specified fields."""
    parts = []

    if title:
        parts.append(f'<h1 id="item-name-title">{title}</h1>')

    if weight:
        parts.append(f'<span id="item-weight-info">{weight}</span>')

    if year_released:
        parts.append(f"<span>Year Released: {year_released}</span>")

    if parts_text:
        parts.append(f"<span>{parts_text}</span>")

    if theme_js:
        parts.append(f"<script>{theme_js}</script>")

    if breadcrumbs:
        # Mimic real BrickLink breadcrumb structure with catString in theme hrefs
        links = []
        cat_idx = 0
        for b in breadcrumbs:
            if b in ("Catalog", "Sets"):
                links.append(f'<a href="//www.bricklink.com/{b.lower()}.asp">{b}</a>')
            elif b and not b[0].isdigit():
                # Theme link with catString parameter
                cat_idx += 1
                links.append(
                    f'<a href="//www.bricklink.com/catalogList.asp?catType=S&catString={cat_idx}">{b}</a>'
                )
            else:
                links.append(f"<span>{b}</span>")
        parts.append("".join(links))

    return _wrap_html("\n".join(parts))


class TestExtractPartsCount:
    """GWT #1-7: _extract_parts_count via parse_item_info."""

    def test_standard_parts_count(self):
        """#1: Given HTML with '305 Parts', returns 305."""
        html = _make_item_html(parts_text="305 Parts")
        result = parse_item_info(html)
        assert result["parts_count"] == 305

    def test_comma_separated_parts_count(self):
        """#2: Given HTML with '1,192 Parts', returns 1192."""
        html = _make_item_html(parts_text="1,192 Parts")
        result = parse_item_info(html)
        assert result["parts_count"] == 1192

    def test_singular_part(self):
        """#3: Given HTML with '1 Part', returns 1."""
        html = _make_item_html(parts_text="1 Part")
        result = parse_item_info(html)
        assert result["parts_count"] == 1

    def test_no_parts_text(self):
        """#4: Given HTML with no parts text, returns None."""
        html = _make_item_html(title="Some Set")
        result = parse_item_info(html)
        assert result["parts_count"] is None

    def test_zero_parts_rejected(self):
        """#5: Given '0 Parts', returns None (below valid range)."""
        html = _make_item_html(parts_text="0 Parts")
        result = parse_item_info(html)
        assert result["parts_count"] is None

    def test_exceeds_max_parts_rejected(self):
        """#6: Given '25000 Parts', returns None (above 20k cap)."""
        html = _make_item_html(parts_text="25000 Parts")
        result = parse_item_info(html)
        assert result["parts_count"] is None

    def test_minifigures_not_confused_with_parts(self):
        """#7: Given '3 Minifigures' but no Parts, returns None."""
        html = _make_item_html(parts_text="3 Minifigures")
        result = parse_item_info(html)
        assert result["parts_count"] is None


class TestExtractTheme:
    """GWT #8-13: _extract_theme via parse_item_info."""

    def test_catstring_js_variable(self):
        """#8: Given JS variable catString='Disney', returns 'Disney'."""
        html = _make_item_html(theme_js="var catString = 'Disney';")
        result = parse_item_info(html)
        assert result["theme"] == "Disney"

    def test_itemcatname_js_variable(self):
        """#9: Given JS variable itemCatName: 'Star Wars', returns 'Star Wars'."""
        html = _make_item_html(theme_js="var itemCatName = 'Star Wars';")
        result = parse_item_info(html)
        assert result["theme"] == "Star Wars"

    def test_breadcrumb_fallback(self):
        """#10: Given breadcrumbs with 'Sets' then 'Technic', returns 'Technic'."""
        html = _make_item_html(breadcrumbs=["Catalog", "Sets", "Technic", "42151-1"])
        result = parse_item_info(html)
        assert result["theme"] == "Technic"

    def test_no_theme_data(self):
        """#11: Given no JS variables and no breadcrumbs, returns None."""
        html = _make_item_html(title="Some Set")
        result = parse_item_info(html)
        assert result["theme"] is None

    def test_empty_catstring_returns_none(self):
        """#12: Given catString='', returns None."""
        html = _make_item_html(theme_js="var catString = '';")
        result = parse_item_info(html)
        assert result["theme"] is None

    def test_breadcrumb_subtheme_returns_top_level(self):
        """#10b: Given breadcrumbs with sub-theme, returns top-level theme."""
        html = _make_item_html(
            breadcrumbs=["Catalog", "Sets", "Jurassic World", "Jurassic Park", "76960-1"]
        )
        result = parse_item_info(html)
        assert result["theme"] == "Jurassic World"

    def test_finds_catstring_in_correct_script(self):
        """#13: Given multiple script tags, only one has catString."""
        html = _wrap_html(
            "<script>var foo = 'bar';</script>"
            "<script>var catString = 'Icons';</script>"
            "<script>var baz = 123;</script>"
        )
        result = parse_item_info(html)
        assert result["theme"] == "Icons"


class TestParseItemInfoIntegration:
    """GWT #14-15: parse_item_info returns all expected keys."""

    def test_full_catalog_html(self):
        """#14: Given full BrickLink-like HTML, all 6 keys present with values."""
        html = _make_item_html(
            title="Princess Enchanted Journey",
            parts_text="305 Parts",
            theme_js="var catString = 'Disney';",
            weight="482g",
            year_released=2023,
        )
        result = parse_item_info(html)
        assert result["title"] == "Princess Enchanted Journey"
        assert result["parts_count"] == 305
        assert result["theme"] == "Disney"
        assert result["weight"] == "482g"
        assert result["year_released"] == 2023

    def test_minimal_html_all_keys_present(self):
        """#15: Given empty HTML, all 9 keys present with None values."""
        result = parse_item_info("<html><body></body></html>")
        expected_keys = {
            "title", "weight", "year_released", "image_url", "parts_count", "theme",
            "minifig_count", "dimensions", "has_instructions",
        }
        assert set(result.keys()) == expected_keys
        assert result["parts_count"] is None
        assert result["theme"] is None
        assert result["minifig_count"] is None
        assert result["dimensions"] is None
        assert result["has_instructions"] is None


class TestParseFullItem:
    """GWT #16-17: parse_full_item builds BricklinkData with new fields."""

    def _make_price_guide_html(self) -> str:
        """Minimal valid price guide HTML with one pricing box."""
        return _wrap_html(
            '<title>Price Guide</title>'
            '<table><tr bgcolor="#C0C0C0">'
            "<td>Times Sold: 10 Total Lots: 5 Total Qty: 15 "
            "Min Price: USD 100.00 Avg Price: USD 150.00 "
            "Qty Avg Price: USD 140.00 Max Price: USD 200.00</td>"
            "<td>(unavailable)</td>"
            "<td>(unavailable)</td>"
            "<td>(unavailable)</td>"
            "</tr></table>"
        )

    def test_parts_count_and_theme_populated(self):
        """#16: Given item HTML with parts and theme, BricklinkData has them."""
        item_html = _make_item_html(
            title="Bugatti Chiron",
            parts_text="3,599 Parts",
            theme_js="var catString = 'Technic';",
        )
        data = parse_full_item(item_html, self._make_price_guide_html(), "S", "42083-1")
        assert data.parts_count == 3599
        assert data.theme == "Technic"

    def test_parts_count_and_theme_none(self):
        """#17: Given item HTML without parts/theme, BricklinkData has None."""
        item_html = _make_item_html(title="Mystery Set")
        data = parse_full_item(item_html, self._make_price_guide_html(), "S", "99999-1")
        assert data.parts_count is None
        assert data.theme is None
