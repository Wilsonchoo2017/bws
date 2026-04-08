"""Parse BrickEconomy analysis pages (years, themes, subthemes).

Extracts aggregate annual growth tables from the analysis overview pages.
Each page has a simple 3-column table: name, (bar chart), annual growth %.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("bws.brickeconomy.analysis_parser")


@dataclass(frozen=True)
class YearGrowth:
    """Annual growth for a single release year."""

    year: int
    annual_growth_pct: float


@dataclass(frozen=True)
class ThemeGrowth:
    """Annual growth for a LEGO theme."""

    theme: str
    annual_growth_pct: float


@dataclass(frozen=True)
class SubthemeGrowth:
    """Annual growth for a LEGO subtheme."""

    theme: str
    subtheme: str
    annual_growth_pct: float


def _parse_pct(text: str) -> float | None:
    """Parse a percentage like '+12.3%' or '-5.6%'."""
    m = re.search(r"([+-]?\d+\.?\d*)%?", text.strip())
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _find_table(soup: BeautifulSoup) -> Tag | None:
    """Find the main data table on the page."""
    table = soup.find("table", class_="table")
    if table:
        return table
    return soup.find("table")


def parse_years_page(html: str) -> list[YearGrowth]:
    """Parse the analysis-years page.

    Table structure: [year, (bar chart), annual_growth_pct]
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table(soup)
    if not table:
        logger.warning("No table found on years analysis page")
        return []

    results: list[YearGrowth] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 3:
            continue

        # Column 0: year, Column 2: growth %
        year_text = cells[0].strip()
        growth_text = cells[2].strip()

        # Skip header row
        if not year_text or not year_text[0].isdigit():
            continue

        try:
            year = int(year_text)
        except ValueError:
            continue

        growth = _parse_pct(growth_text)
        if growth is None:
            continue

        results.append(YearGrowth(year=year, annual_growth_pct=growth))

    logger.info("Parsed %d year growth records", len(results))
    return results


def parse_themes_page(html: str) -> list[ThemeGrowth]:
    """Parse the analysis-themes page.

    Table structure: [theme, (bar chart), annual_growth_pct]
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table(soup)
    if not table:
        logger.warning("No table found on themes analysis page")
        return []

    results: list[ThemeGrowth] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 3:
            continue

        theme = cells[0].strip()
        growth_text = cells[2].strip()

        if not theme or theme == "Annual growth":
            continue

        growth = _parse_pct(growth_text)
        if growth is None:
            continue

        results.append(ThemeGrowth(theme=theme, annual_growth_pct=growth))

    logger.info("Parsed %d theme growth records", len(results))
    return results


def parse_subthemes_page(html: str) -> list[SubthemeGrowth]:
    """Parse the analysis-subthemes page.

    Table structure: [theme / subtheme, (bar chart), annual_growth_pct]
    The first column has format "Theme / Subtheme" or just "Subtheme".
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table(soup)
    if not table:
        logger.warning("No table found on subthemes analysis page")
        return []

    results: list[SubthemeGrowth] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 3:
            continue

        raw_name = cells[0].strip()
        growth_text = cells[2].strip()

        if not raw_name or raw_name == "Annual growth":
            continue

        growth = _parse_pct(growth_text)
        if growth is None:
            continue

        # Split "Theme / Subtheme" format
        if " / " in raw_name:
            parts = raw_name.split(" / ", 1)
            theme = parts[0].strip()
            subtheme = parts[1].strip()
        else:
            theme = ""
            subtheme = raw_name

        results.append(SubthemeGrowth(
            theme=theme,
            subtheme=subtheme,
            annual_growth_pct=growth,
        ))

    logger.info("Parsed %d subtheme growth records", len(results))
    return results
