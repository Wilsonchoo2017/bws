"""GWT tests for BrickEconomy packaging field parsing from sidebar."""

from datetime import datetime, timezone

from services.brickeconomy.parser import parse_brickeconomy_page


def _make_be_page(sidebar_html: str) -> str:
    """Build a minimal BrickEconomy HTML page with the given sidebar content."""
    return f"""
    <html>
    <head>
        <script type="application/ld+json">
        {{"@type": "Product", "name": "Test Set"}}
        </script>
    </head>
    <body>
        <div class="col-md-4">
            <h3>Set Details</h3>
            {sidebar_html}
        </div>
    </body>
    </html>
    """


class TestPackagingParsing:
    """Given BrickEconomy HTML with various packaging fields, verify extraction."""

    def test_given_foil_pack_when_parsed_then_packaging_is_foil_pack(self):
        """Given a BE page with 'Packaging' -> 'Foil Pack' in sidebar,
        when parsed,
        then snapshot.packaging is 'Foil Pack'."""
        html = _make_be_page("""
            <div>Set number</div><div>122222-1</div>
            <div>Theme</div><div>Jurassic World</div>
            <div>Packaging</div><div>Foil Pack</div>
            <div>Pieces</div><div>48</div>
        """)
        snapshot = parse_brickeconomy_page(html, "122222-1")
        assert snapshot.packaging == "Foil Pack"

    def test_given_polybag_when_parsed_then_packaging_is_polybag(self):
        """Given a BE page with 'Packaging' -> 'Polybag' in sidebar,
        when parsed,
        then snapshot.packaging is 'Polybag'."""
        html = _make_be_page("""
            <div>Set number</div><div>30432-1</div>
            <div>Theme</div><div>City</div>
            <div>Packaging</div><div>Polybag</div>
            <div>Pieces</div><div>35</div>
        """)
        snapshot = parse_brickeconomy_page(html, "30432-1")
        assert snapshot.packaging == "Polybag"

    def test_given_box_when_parsed_then_packaging_is_box(self):
        """Given a BE page with 'Packaging' -> 'Box' in sidebar,
        when parsed,
        then snapshot.packaging is 'Box'."""
        html = _make_be_page("""
            <div>Set number</div><div>60305-1</div>
            <div>Theme</div><div>City</div>
            <div>Packaging</div><div>Box</div>
            <div>Pieces</div><div>342</div>
        """)
        snapshot = parse_brickeconomy_page(html, "60305-1")
        assert snapshot.packaging == "Box"

    def test_given_no_packaging_field_when_parsed_then_packaging_is_none(self):
        """Given a BE page without a 'Packaging' field in sidebar,
        when parsed,
        then snapshot.packaging is None."""
        html = _make_be_page("""
            <div>Set number</div><div>75192-1</div>
            <div>Theme</div><div>Star Wars</div>
            <div>Pieces</div><div>7541</div>
        """)
        snapshot = parse_brickeconomy_page(html, "75192-1")
        assert snapshot.packaging is None

    def test_given_foil_pack_when_checked_then_is_excluded(self):
        """Given a snapshot parsed from a foil pack page,
        when is_excluded_packaging is called with its packaging,
        then returns True (end-to-end integration)."""
        from services.brickeconomy.parser import is_excluded_packaging

        html = _make_be_page("""
            <div>Set number</div><div>122222-1</div>
            <div>Packaging</div><div>Foil Pack</div>
        """)
        snapshot = parse_brickeconomy_page(html, "122222-1")
        assert is_excluded_packaging(snapshot.packaging) is True

    def test_given_box_when_checked_then_not_excluded(self):
        """Given a snapshot parsed from a box-packaged set,
        when is_excluded_packaging is called with its packaging,
        then returns False (end-to-end integration)."""
        from services.brickeconomy.parser import is_excluded_packaging

        html = _make_be_page("""
            <div>Set number</div><div>60305-1</div>
            <div>Packaging</div><div>Box</div>
        """)
        snapshot = parse_brickeconomy_page(html, "60305-1")
        assert is_excluded_packaging(snapshot.packaging) is False
