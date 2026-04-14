"""BrickLink store-listings parser.

Extracts per-store listings from the v2 catalog page (``catalogitem.page``)
including seller country, store name, condition, quantity, and price.

The v2 page renders listings client-side from a JS template, so the raw
HTML our anonymous HTTP scraper sees contains only the template skeleton
(``[%strSellerCountryCode%]`` etc.).  This module is meant to run against
a logged-in Camoufox page via ``page.evaluate`` -- the JS walks the
hydrated DOM and returns plain dicts that Python then coerces into
``BricklinkListing`` dataclasses.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from bws_types.models import Condition, PriceData
from bws_types.price import parse_price_string

logger = logging.getLogger("bws.bricklink.listings_parser")


V2_BASE = "https://www.bricklink.com/v2/catalog/catalogitem.page"


def build_listings_url(set_number: str) -> str:
    """Build the v2 catalog page URL with the price/sales tab fragment."""
    return f"{V2_BASE}?S={set_number}#T=P"


@dataclass(frozen=True)
class BricklinkListing:
    """A single store listing on a BrickLink catalog price/sales tab."""

    set_number: str
    store_id: str | None
    store_name: str | None
    seller_country_code: str | None
    seller_country_name: str | None
    feedback_score: int | None
    condition: Condition | None
    quantity: int | None
    price: PriceData | None
    min_buy_text: str | None
    ships_to_my: bool
    row_class_names: tuple[str, ...] = ()


EXTRACT_JS = r"""
() => {
  // The logged-in catalog page embeds the legacy catalogPG structure:
  // <table class="pcipgInnerTable"> tables arranged in 4 columns
  // (Past Sales New, Past Sales Used, Currently Available New, Currently
  // Available Used).  Each "Currently Available" row contains a flag
  // image, a store link, a ships-to-viewer indicator (box16Y vs box16N),
  // a quantity, and a price.
  const tables = Array.from(document.querySelectorAll('table.pcipgInnerTable'));
  const out = [];

  for (const t of tables) {
    const sub = t.querySelector('.pcipgSubHeader');
    const subText = sub ? (sub.textContent || '').trim() : '';
    if (!/Currently Available/i.test(subText)) continue;

    // Condition is determined by the parent column class:
    //   pcipgOddColumn  -> New
    //   pcipgEvenColumn -> Used
    const parentTd = t.closest('td');
    let condition = null;
    if (parentTd) {
      const cls = parentTd.className || '';
      if (/pcipgOddColumn/i.test(cls)) condition = 'new';
      else if (/pcipgEvenColumn/i.test(cls)) condition = 'used';
    }

    const rows = Array.from(t.querySelectorAll('tr'));
    for (const row of rows) {
      const flag = row.querySelector('img[src*="/flagsS/"]');
      if (!flag) continue;  // skip header / summary rows

      const srcM = (flag.getAttribute('src') || '').match(/flagsS\/([A-Za-z]{2})\.gif/);
      const seller_country_code = srcM ? srcM[1].toUpperCase() : null;
      const seller_country_name =
        flag.getAttribute('alt') || flag.getAttribute('title') || null;

      const storeLink = row.querySelector('a[href*="sID="]');
      let store_id = null;
      if (storeLink) {
        const m = (storeLink.getAttribute('href') || '').match(/sID=(\d+)/);
        if (m) store_id = m[1];
      }

      const boxImg = row.querySelector('img[src*="/clone/img/box16"]');
      let store_name = null;
      let ships_to_my = null;
      if (boxImg) {
        const alt = (boxImg.getAttribute('alt') || boxImg.getAttribute('title') || '').trim();
        const m = alt.match(/^Store:\s*(.+)$/i);
        if (m) store_name = m[1].trim();
        const src = boxImg.getAttribute('src') || '';
        if (/box16Y/i.test(src)) ships_to_my = true;
        else if (/box16N/i.test(src)) ships_to_my = false;
      }

      // Walk the TD children: index 0 is flag+store, then qty, empty, price.
      const cells = Array.from(row.children).filter((c) => c.tagName === 'TD');
      let quantity = null;
      let price_text = null;
      for (let i = 1; i < cells.length; i++) {
        const txt = (cells[i].textContent || '').replace(/\s+/g, ' ').trim();
        if (!txt) continue;
        if (quantity === null && /^\d+$/.test(txt)) {
          quantity = parseInt(txt, 10);
          continue;
        }
        if (price_text === null && /[A-Z]{2,3}\s*~?\s*[\d.,]+/.test(txt)) {
          price_text = txt;
        }
      }

      out.push({
        store_id: store_id,
        store_name: store_name,
        seller_country_code: seller_country_code,
        seller_country_name: seller_country_name,
        feedback_score: null,
        condition: condition,
        quantity: quantity,
        price_text: price_text,
        min_buy_text: null,
        ships_to_my: ships_to_my === null ? true : ships_to_my,
        row_class_names: Array.from(row.classList),
      });
    }
  }
  return out;
}
"""


_PRICE_FALLBACK_RE = re.compile(r"([A-Z]{2,3})\s*~?\s*([\d,\.]+)")


def _coerce_price(price_text: str | None) -> PriceData | None:
    if not price_text:
        return None
    cleaned = price_text.replace("~", "").strip()
    parsed = parse_price_string(cleaned)
    if parsed is None:
        match = _PRICE_FALLBACK_RE.search(cleaned)
        if not match:
            return None
        parsed = parse_price_string(f"{match.group(1)} {match.group(2)}")
    if parsed is None:
        return None
    currency, cents = parsed
    return PriceData(currency=currency, amount=cents)


def _coerce_condition(raw: str | None) -> Condition | None:
    if not raw:
        return None
    lowered = raw.strip().lower()
    if lowered == "new":
        return Condition.NEW
    if lowered == "used":
        return Condition.USED
    return None


def parse_listings(set_number: str, raw_rows: list[dict]) -> list[BricklinkListing]:
    """Coerce raw dicts returned by ``EXTRACT_JS`` into dataclasses."""
    listings: list[BricklinkListing] = []
    for row in raw_rows:
        try:
            listing = BricklinkListing(
                set_number=set_number,
                store_id=row.get("store_id"),
                store_name=row.get("store_name"),
                seller_country_code=row.get("seller_country_code"),
                seller_country_name=row.get("seller_country_name"),
                feedback_score=row.get("feedback_score"),
                condition=_coerce_condition(row.get("condition")),
                quantity=row.get("quantity"),
                price=_coerce_price(row.get("price_text")),
                min_buy_text=row.get("min_buy_text"),
                ships_to_my=bool(row.get("ships_to_my", True)),
                row_class_names=tuple(row.get("row_class_names") or ()),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Failed to coerce listing row %r: %s", row, exc)
            continue
        listings.append(listing)
    return listings
