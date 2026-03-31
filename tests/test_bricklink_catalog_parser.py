"""Tests for BrickLink catalog list parser functions."""

import pytest

from services.bricklink.parser import (
    build_catalog_list_url,
    parse_catalog_list_page,
    parse_catalog_list_pagination,
)


def _wrap_html(body: str) -> str:
    return f"<html><body>{body}</body></html>"


def _make_catalog_row(
    item_type: str,
    item_id: str,
    title: str,
    year: int = 2020,
    image_url: str | None = None,
) -> str:
    img_src = image_url or f"https://img.bricklink.com/ItemImage/SN/0/{item_id}.png"
    return (
        f'<tr>'
        f'<td><img src="{img_src}"></td>'
        f'<td><a href="/v2/catalog/catalogitem.page?{item_type}={item_id}">'
        f'{title}</a></td>'
        f'<td>{year}</td>'
        f'</tr>'
    )


def _make_catalog_table(*rows: str) -> str:
    return f'<table>{"".join(rows)}</table>'


def _make_pagination(current: int, total: int) -> str:
    links = []
    for i in range(1, total + 1):
        if i == current:
            links.append(f"<b>{i}</b>")
        else:
            links.append(
                f'<a href="/catalogList.asp?pg={i}&itemYear=2020&catType=S&v=1">[{i}]</a>'
            )
    return (
        f'<div>{" ".join(links)}'
        f' <b>{total * 50}</b> Items Found. '
        f'Page <b>{current}</b> of <b>{total}</b></div>'
    )


class TestParseCatalogListPage:
    def test_parses_single_item(self):
        row = _make_catalog_row("S", "75192-1", "Millennium Falcon", 2017)
        html = _wrap_html(_make_catalog_table(row))

        items = parse_catalog_list_page(html)

        assert len(items) == 1
        assert items[0].item_id == "75192-1"
        assert items[0].item_type == "S"
        assert items[0].title == "Millennium Falcon"
        assert items[0].year_released == 2017

    def test_parses_multiple_items(self):
        rows = [
            _make_catalog_row("S", "75192-1", "Millennium Falcon", 2017),
            _make_catalog_row("S", "10276-1", "Colosseum", 2020),
            _make_catalog_row("S", "42115-1", "Lamborghini", 2020),
        ]
        html = _wrap_html(_make_catalog_table(*rows))

        items = parse_catalog_list_page(html)

        assert len(items) == 3
        assert items[0].item_id == "75192-1"
        assert items[1].item_id == "10276-1"
        assert items[2].item_id == "42115-1"

    def test_deduplicates_items(self):
        rows = [
            _make_catalog_row("S", "75192-1", "Millennium Falcon"),
            _make_catalog_row("S", "75192-1", "Millennium Falcon"),
        ]
        html = _wrap_html(_make_catalog_table(*rows))

        items = parse_catalog_list_page(html)

        assert len(items) == 1

    def test_extracts_image_url(self):
        row = _make_catalog_row(
            "S", "75192-1", "Millennium Falcon",
            image_url="https://img.bricklink.com/ItemImage/ST/0/75192-1.t1.png",
        )
        html = _wrap_html(_make_catalog_table(row))

        items = parse_catalog_list_page(html)

        assert items[0].image_url is not None
        assert "75192-1" in items[0].image_url

    def test_handles_minifig_type(self):
        row = _make_catalog_row("M", "sw0001", "Battle Droid")
        html = _wrap_html(_make_catalog_table(row))

        items = parse_catalog_list_page(html)

        assert len(items) == 1
        assert items[0].item_type == "M"
        assert items[0].item_id == "sw0001"

    def test_empty_page_returns_empty(self):
        html = _wrap_html("<table></table>")

        items = parse_catalog_list_page(html)

        assert items == []

    def test_no_table_returns_empty(self):
        html = _wrap_html("<div>No results</div>")

        items = parse_catalog_list_page(html)

        assert items == []

    def test_skips_item_id_only_links(self):
        """Links where text is just the item_id should be skipped (we want name links)."""
        html = _wrap_html(
            '<table><tr><td>'
            '<a href="/v2/catalog/catalogitem.page?S=75192-1">75192-1</a>'
            '</td></tr></table>'
        )

        items = parse_catalog_list_page(html)

        assert items == []


class TestParseCatalogListPagination:
    def test_parses_page_of_total(self):
        html = _wrap_html(_make_pagination(1, 16))

        total = parse_catalog_list_pagination(html)

        assert total == 16

    def test_single_page(self):
        html = _wrap_html(
            '<div>50 Items Found. Page <b>1</b> of <b>1</b></div>'
        )

        total = parse_catalog_list_pagination(html)

        assert total == 1

    def test_fallback_to_link_parsing(self):
        html = _wrap_html(
            '<div>'
            '<a href="catalogList.asp?pg=1&v=1">[1]</a> '
            '<a href="catalogList.asp?pg=2&v=1">[2]</a> '
            '<a href="catalogList.asp?pg=5&v=1">[5]</a>'
            '</div>'
        )

        total = parse_catalog_list_pagination(html)

        assert total == 5

    def test_no_pagination_returns_one(self):
        html = _wrap_html("<div>Some content</div>")

        total = parse_catalog_list_pagination(html)

        assert total == 1


class TestBuildCatalogListUrl:
    def test_sets_page_number(self):
        base = "https://www.bricklink.com/catalogList.asp?pg=1&itemYear=2020&catType=S&v=1"

        result = build_catalog_list_url(base, page=3)

        assert "pg=3" in result
        assert "itemYear=2020" in result
        assert "catType=S" in result

    def test_replaces_existing_page(self):
        base = "https://www.bricklink.com/catalogList.asp?pg=5&itemYear=2020&catType=S&v=1"

        result = build_catalog_list_url(base, page=1)

        assert "pg=1" in result
        # Should not contain the old pg=5
        assert "pg=5" not in result

    def test_preserves_other_params(self):
        base = "https://www.bricklink.com/catalogList.asp?pg=1&itemYear=2020&catType=S&v=1"

        result = build_catalog_list_url(base, page=2)

        assert "itemYear=2020" in result
        assert "catType=S" in result
        assert "v=1" in result
