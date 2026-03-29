"""Unit tests for Brickset HTML parser."""

import pytest

from services.brickset.parser import (
    BricksetData,
    _extract_all_fields,
    _parse_currency_amount,
    _parse_exit_year,
    _parse_int,
    _parse_year,
    parse_brickset_page,
)

# Minimal HTML fixture matching Brickset's actual structure
SAMPLE_HTML = """
<html>
<head>
<meta property="og:image" content="https://images.brickset.com/sets/images/10270-1.jpg">
</head>
<body>
<section class="featurebox "><h2>Details</h2><div class="text">
<dl>
    <dt>Number</dt>
    <dd>10270-1</dd>
    <dt>Name</dt>
    <dd>Bookshop</dd>
    <dt>Theme</dt>
    <dd><a href="/sets/theme-Creator-Expert">Creator Expert</a></dd>
    <dt>Subtheme</dt>
    <dd><a href="/sets/subtheme-Modular">Modular Buildings Collection</a></dd>
    <dt>Year released</dt>
    <dd><a href="/sets/year-2020">2020</a></dd>
    <dt>Launch/exit</dt>
    <dd>01 Jan 20 - 31 Dec 23</dd>
    <dt>Pieces</dt>
    <dd>2504</dd>
    <dt>Minifigs</dt>
    <dd>5, all unique to this set</dd>
    <dt>RRP</dt>
    <dd>&pound;169.99, $199.99, &euro;199.99</dd>
    <dt>Availability</dt>
    <dd>LEGO exclusive</dd>
</dl>
</div></section>
</body></html>
"""

ACTIVE_SET_HTML = """
<html>
<head>
<meta property="og:image" content="https://images.brickset.com/sets/images/75192-1.jpg">
</head>
<body>
<section class="featurebox "><h2>Details</h2><div class="text">
<dl>
    <dt>Name</dt>
    <dd>Millennium Falcon</dd>
    <dt>Theme</dt>
    <dd><a href="/sets/theme-Star-Wars">Star Wars</a></dd>
    <dt>Year released</dt>
    <dd><a href="/sets/year-2017">2017</a></dd>
    <dt>Launch/exit</dt>
    <dd>01 Oct 17 - {t.b.a}</dd>
    <dt>Pieces</dt>
    <dd>7,541</dd>
    <dt>RRP</dt>
    <dd>&pound;734.99, $849.99, &euro;849.99</dd>
</dl>
</div></section>
</body></html>
"""


class TestParseFullPage:
    def test_retired_set(self) -> None:
        data = parse_brickset_page(SAMPLE_HTML, "10270")
        assert data.title == "Bookshop"
        assert data.theme == "Creator Expert"
        assert data.subtheme == "Modular Buildings Collection"
        assert data.year_released == 2020
        assert data.year_retired == 2023
        assert data.pieces == 2504
        assert data.minifigs == 5
        assert data.rrp_usd_cents == 19999
        assert data.rrp_gbp_cents == 16999
        assert data.rrp_eur_cents == 19999
        assert data.image_url == "https://images.brickset.com/sets/images/10270-1.jpg"

    def test_active_set(self) -> None:
        data = parse_brickset_page(ACTIVE_SET_HTML, "75192")
        assert data.title == "Millennium Falcon"
        assert data.theme == "Star Wars"
        assert data.year_released == 2017
        assert data.year_retired is None  # Not retired
        assert data.pieces == 7541
        assert data.rrp_usd_cents == 84999

    def test_empty_html(self) -> None:
        data = parse_brickset_page("<html><body></body></html>", "99999")
        assert data.set_number == "99999"
        assert data.title is None
        assert data.theme is None
        assert data.year_retired is None


class TestExtractAllFields:
    def test_extracts_all_dt_dd_pairs(self) -> None:
        fields = _extract_all_fields(SAMPLE_HTML)
        assert fields["Name"] == "Bookshop"
        assert fields["Theme"] == "Creator Expert"
        assert "2020" in fields["Year released"]
        assert "01 Jan 20 - 31 Dec 23" in fields["Launch/exit"]

    def test_strips_html_tags(self) -> None:
        fields = _extract_all_fields(SAMPLE_HTML)
        assert "<" not in fields["Theme"]


class TestParseYear:
    def test_four_digit_year(self) -> None:
        assert _parse_year("2020") == 2020

    def test_year_in_text(self) -> None:
        assert _parse_year("Released in 2017") == 2017

    def test_none(self) -> None:
        assert _parse_year(None) is None

    def test_no_year(self) -> None:
        assert _parse_year("unknown") is None


class TestParseInt:
    def test_simple(self) -> None:
        assert _parse_int("2504") == 2504

    def test_with_comma(self) -> None:
        assert _parse_int("7,541") == 7541

    def test_with_trailing_text(self) -> None:
        assert _parse_int("5, all unique to this set") == 5

    def test_none(self) -> None:
        assert _parse_int(None) is None


class TestParseCurrencyAmount:
    def test_usd(self) -> None:
        assert _parse_currency_amount("$199.99", "$") == 19999

    def test_gbp(self) -> None:
        assert _parse_currency_amount("\u00a3169.99, $199.99", "\u00a3") == 16999

    def test_eur(self) -> None:
        assert _parse_currency_amount("$199.99, \u20ac199.99", "\u20ac") == 19999

    def test_multi_currency(self) -> None:
        rrp = "\u00a3169.99, $199.99, \u20ac199.99"
        assert _parse_currency_amount(rrp, "$") == 19999
        assert _parse_currency_amount(rrp, "\u00a3") == 16999
        assert _parse_currency_amount(rrp, "\u20ac") == 19999

    def test_no_match(self) -> None:
        assert _parse_currency_amount("no price here", "$") is None

    def test_large_amount(self) -> None:
        assert _parse_currency_amount("$1,299.99", "$") == 129999


class TestParseExitYear:
    def test_standard_format(self) -> None:
        assert _parse_exit_year("01 Jan 20 - 31 Dec 23") == 2023

    def test_not_retired(self) -> None:
        assert _parse_exit_year("01 Oct 17 - {t.b.a}") is None

    def test_year_only(self) -> None:
        assert _parse_exit_year("2020 - 2023") == 2023

    def test_none(self) -> None:
        assert _parse_exit_year(None) is None

    def test_empty(self) -> None:
        assert _parse_exit_year("") is None
