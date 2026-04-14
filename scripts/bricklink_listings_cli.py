"""Manual BrickLink store-listings extraction test.

Usage:
    python -m scripts.bricklink_listings_cli 10857-1
    python -m scripts.bricklink_listings_cli 75192-1 --headless
    python -m scripts.bricklink_listings_cli 10857-1 --json-out /tmp/listings.json

Requires a prior ``python -m scripts.bricklink_login`` run so the
Camoufox profile has BrickLink cookies.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bws_types.models import Condition
from bws_types.price import cents_to_dollars
from services.bricklink.listings_parser import BricklinkListing
from services.bricklink.listings_scraper import (
    ListingsProfileMissing,
    fetch_listings_sync,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s  %(message)s",
)
logger = logging.getLogger("bws.bricklink_listings_cli")


def _listing_to_json(listing: BricklinkListing) -> dict:
    """Convert a listing to a JSON-friendly dict."""
    data = asdict(listing)
    # Enum -> string
    if isinstance(listing.condition, Condition):
        data["condition"] = listing.condition.value
    # PriceData -> (currency, cents, dollars)
    if listing.price is not None:
        data["price"] = {
            "currency": listing.price.currency,
            "amount_cents": int(listing.price.amount),
            "amount": round(cents_to_dollars(listing.price.amount), 2),
        }
    # tuple -> list for JSON
    data["row_class_names"] = list(listing.row_class_names)
    return data


def _summarize(listings: list[BricklinkListing]) -> str:
    if not listings:
        return "0 listings"
    countries = Counter(l.seller_country_code or "??" for l in listings)
    country_str = ", ".join(f"{c}x{n}" for c, n in countries.most_common())
    ships = sum(1 for l in listings if l.ships_to_my)
    conditions = Counter(l.condition.value if l.condition else "?" for l in listings)
    cond_str = ", ".join(f"{c}x{n}" for c, n in conditions.most_common())
    return (
        f"{len(listings)} listings | ships_to_my={ships}/{len(listings)} | "
        f"conditions: {cond_str} | countries: {country_str}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("set_number", help="Set number, e.g. 10857-1 or 75192-1")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser headlessly (default: headed so you can watch).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full JSON dump to this path (default: stdout).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Timeout in seconds for the browser run (default: 120).",
    )
    args = parser.parse_args()

    try:
        listings = fetch_listings_sync(
            args.set_number,
            headless=args.headless,
            timeout=args.timeout,
        )
    except ListingsProfileMissing as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        logger.error("Fetch failed: %s", exc, exc_info=True)
        return 1

    payload = {
        "set_number": args.set_number,
        "summary": _summarize(listings),
        "count": len(listings),
        "listings": [_listing_to_json(l) for l in listings],
    }

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {len(listings)} listings to {args.json_out}")
    else:
        print(json.dumps(payload, indent=2))

    print()
    print("Summary:", payload["summary"])
    return 0 if listings else 3


if __name__ == "__main__":
    sys.exit(main())
