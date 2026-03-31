"""Pure transformation functions for converting scraper output to item dicts.

All functions in this module are pure -- no side effects, no I/O, no imports
of services or DB modules. They take raw data in and return transformed data out.
"""

from __future__ import annotations

from typing import Any


def shopee_item_to_dict(item: Any) -> dict:
    """Transform a Shopee scraper item into a normalized item dict."""
    return {
        "title": item.title,
        "price_display": item.price_display,
        "sold_count": item.sold_count,
        "rating": item.rating,
        "shop_name": item.shop_name,
        "product_url": item.product_url,
        "image_url": item.image_url,
    }


def toysrus_product_to_dict(product: Any) -> dict:
    """Transform a ToysRUs product into a normalized item dict."""
    return {
        "title": product.name,
        "price_display": f"RM {product.price_myr}",
        "sold_count": None,
        "rating": None,
        "shop_name": 'Toys"R"Us Malaysia',
        "product_url": product.url,
        "image_url": product.image_url,
    }


def mightyutan_product_to_dict(product: Any) -> dict:
    """Transform a Mighty Utan product into a normalized item dict."""
    return {
        "title": product.name,
        "price_display": f"RM {product.price_myr}",
        "sold_count": product.total_sold,
        "rating": product.rating,
        "shop_name": "Mighty Utan Malaysia",
        "product_url": product.url,
        "image_url": product.image_url,
    }


def catalog_item_to_dict(item: Any) -> dict:
    """Transform a BrickLink catalog item into a normalized item dict."""
    return {
        "title": item.title or item.item_id,
        "price_display": "N/A",
        "product_url": (
            f"https://www.bricklink.com/v2/catalog/catalogitem.page"
            f"?{item.item_type}={item.item_id}"
        ),
        "image_url": item.image_url,
    }


def extract_set_numbers_from_catalog(items: list[Any]) -> list[str]:
    """Extract LEGO set numbers from BrickLink catalog items.

    Filters to type 'S' items and strips the variant suffix (e.g. '75192-1' -> '75192').
    """
    return [
        item.item_id.rsplit("-", 1)[0]
        for item in items
        if item.item_type == "S" and "-" in item.item_id
    ]


def saturation_result_to_summary(result: Any) -> dict:
    """Transform a saturation batch result into a summary dict."""
    return {
        "successful": result.successful,
        "failed": result.failed,
        "skipped": result.skipped,
        "total": result.total_items,
    }


EMPTY_SATURATION_SUMMARY: dict = {
    "successful": 0,
    "failed": 0,
    "skipped": 0,
    "total": 0,
}


def carousell_listing_to_dict(listing: Any) -> dict:
    """Transform a Carousell listing into a normalized item dict."""
    return {
        "title": listing.title,
        "price_display": listing.price,
        "sold_count": None,
        "rating": None,
        "shop_name": listing.seller_name or "Carousell",
        "product_url": listing.listing_url,
        "image_url": listing.image_url,
        "condition": listing.condition,
        "time_ago": listing.time_ago,
    }


def brickeconomy_snapshot_to_dict(snapshot: Any) -> dict:
    """Transform a BrickEconomy snapshot into a normalized item dict."""
    value_display = (
        f"${snapshot.value_new_cents / 100:.2f}"
        if snapshot.value_new_cents
        else "N/A"
    )
    return {
        "title": snapshot.title,
        "set_number": snapshot.set_number,
        "price_display": value_display,
        "theme": snapshot.theme,
        "subtheme": snapshot.subtheme,
        "year_released": snapshot.year_released,
        "pieces": snapshot.pieces,
        "minifigs": snapshot.minifigs,
        "availability": snapshot.availability,
        "image_url": snapshot.image_url,
        "product_url": snapshot.brickeconomy_url,
        "rrp_usd_cents": snapshot.rrp_usd_cents,
        "value_new_cents": snapshot.value_new_cents,
        "annual_growth_pct": snapshot.annual_growth_pct,
        "rating_value": snapshot.rating_value,
        "review_count": snapshot.review_count,
        "chart_points": len(snapshot.value_chart),
        "sales_months": len(snapshot.sales_trend),
    }


def keepa_product_to_dict(data: Any) -> dict:
    """Transform Keepa product data into a normalized item dict."""
    buy_box_display = (
        f"${data.current_buy_box_cents / 100:.2f}"
        if data.current_buy_box_cents
        else "N/A"
    )
    return {
        "title": data.title,
        "set_number": data.set_number,
        "asin": data.asin,
        "price_display": buy_box_display,
        "product_url": data.keepa_url,
        "current_buy_box_cents": data.current_buy_box_cents,
        "current_amazon_cents": data.current_amazon_cents,
        "current_new_cents": data.current_new_cents,
        "lowest_ever_cents": data.lowest_ever_cents,
        "highest_ever_cents": data.highest_ever_cents,
        "amazon_points": len(data.amazon_price),
        "new_points": len(data.new_price),
        "buy_box_points": len(data.buy_box),
        "sales_rank_points": len(data.sales_rank),
    }


def enrichment_log_summary(field_details: list[dict]) -> str:
    """Build a log summary string from enrichment field details.

    Pure function -- no I/O.
    """
    found = [d["field"] for d in field_details if d["status"] == "found"]
    missing = [d["field"] for d in field_details if d["status"] in ("not_found", "failed")]
    found_str = ", ".join(found) if found else "none"
    missing_str = ", ".join(missing) if missing else "none"
    fields_found = len(found)
    fields_total = len(field_details)
    return (
        f"{fields_found}/{fields_total} fields found "
        f"[found: {found_str}] [missing: {missing_str}]"
    )
