"""
Simple standalone scraper for individual Bricklink items.
Given a Bricklink URL, extracts pricing information.
"""

import re
import urllib.parse
from typing import Optional

import requests
import bs4


def scrape_bricklink_item(url: str) -> dict:
    """
    Scrape pricing information from a Bricklink item URL.

    Args:
        url: Bricklink URL (e.g., https://www.bricklink.com/v2/catalog/catalogitem.page?S=31113-1)

    Returns:
        Dictionary with item info and pricing data:
        {
            'item_id': '31113-1',
            'item_type': 'S',  # S=set, P=part, M=minifig, etc.
            'title': 'Race Car Transporter',
            'weight': '469.3g',
            'six_month_new': {...},
            'six_month_used': {...},
            'current_new': {...},
            'current_used': {...}
        }
    """
    # Parse URL to extract item type and ID
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)

    item_type = None
    item_id = None

    # Detect item type (P, S, M, G, C, I, O, B)
    for key in ['P', 'S', 'M', 'G', 'C', 'I', 'O', 'B']:
        if key in params:
            item_type = key
            item_id = params[key][0]
            break

    if not item_type or not item_id:
        raise ValueError(f"Could not extract item type and ID from URL: {url}")

    # Fetch main item page for basic info
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    soup = bs4.BeautifulSoup(response.text, 'lxml')

    # Extract basic info
    title_elem = soup.select_one('h1#item-name-title')
    title = title_elem.text.strip() if title_elem else None

    weight_elem = soup.select_one('span#item-weight-info')
    weight = weight_elem.text.strip() if weight_elem else None

    # Fetch price guide page
    price_guide_url = f"https://www.bricklink.com/catalogPG.asp?{item_type}={item_id}"
    price_response = requests.get(price_guide_url, headers=headers, timeout=30)
    price_response.raise_for_status()

    price_soup = bs4.BeautifulSoup(price_response.text, 'lxml')

    # Extract pricing boxes (4 boxes: 6mo new, 6mo used, current new, current used)
    SELECTOR_PRICE_BOXES = "#id-main-legacy-table > tr table > tr:nth-of-type(3) > td > table > tr > td"
    price_boxes = price_soup.select(SELECTOR_PRICE_BOXES)

    # Regex patterns for extracting pricing data
    RE_TIMES_SOLD = re.compile(r"Times Sold:\s*(\d+)", re.IGNORECASE)
    RE_TOTAL_LOTS = re.compile(r"Total Lots:\s*(\d+)", re.IGNORECASE)
    RE_TOTAL_QTY = re.compile(r"Total Qty:\s*(\d+)", re.IGNORECASE)
    RE_MIN_PRICE = re.compile(r"Min Price:\s*([A-Z]+)\s+([\d,\.]+)", re.IGNORECASE)
    RE_AVG_PRICE = re.compile(r"Avg Price:\s*([A-Z]+)\s+([\d,\.]+)", re.IGNORECASE)
    RE_QTY_AVG_PRICE = re.compile(r"Qty Avg Price:\s*([A-Z]+)\s+([\d,\.]+)", re.IGNORECASE)
    RE_MAX_PRICE = re.compile(r"Max Price:\s*([A-Z]+)\s+([\d,\.]+)", re.IGNORECASE)

    def extract_price_box(box: bs4.element.Tag) -> Optional[dict]:
        """Extract pricing data from a single box."""
        text = box.get_text(separator='\n', strip=True)

        # Check if box has "(unavailable)" message
        if "(unavailable)" in text.lower():
            return None

        data = {}

        # Extract counts
        times_sold = RE_TIMES_SOLD.search(text)
        if times_sold:
            data['times_sold'] = int(times_sold.group(1))

        total_lots = RE_TOTAL_LOTS.search(text)
        if total_lots:
            data['total_lots'] = int(total_lots.group(1))

        total_qty = RE_TOTAL_QTY.search(text)
        if total_qty:
            data['total_qty'] = int(total_qty.group(1))

        # Extract prices
        min_price = RE_MIN_PRICE.search(text)
        if min_price:
            data['min_price'] = {
                'currency': min_price.group(1).upper(),
                'amount': float(min_price.group(2).replace(',', ''))
            }

        avg_price = RE_AVG_PRICE.search(text)
        if avg_price:
            data['avg_price'] = {
                'currency': avg_price.group(1).upper(),
                'amount': float(avg_price.group(2).replace(',', ''))
            }

        qty_avg_price = RE_QTY_AVG_PRICE.search(text)
        if qty_avg_price:
            data['qty_avg_price'] = {
                'currency': qty_avg_price.group(1).upper(),
                'amount': float(qty_avg_price.group(2).replace(',', ''))
            }

        max_price = RE_MAX_PRICE.search(text)
        if max_price:
            data['max_price'] = {
                'currency': max_price.group(1).upper(),
                'amount': float(max_price.group(2).replace(',', ''))
            }

        return data if data else None

    # Extract all 4 boxes
    pricing_data = {
        'six_month_new': None,
        'six_month_used': None,
        'current_new': None,
        'current_used': None,
    }

    if len(price_boxes) >= 4:
        pricing_data['six_month_new'] = extract_price_box(price_boxes[0])
        pricing_data['six_month_used'] = extract_price_box(price_boxes[1])
        pricing_data['current_new'] = extract_price_box(price_boxes[2])
        pricing_data['current_used'] = extract_price_box(price_boxes[3])

    return {
        'item_id': item_id,
        'item_type': item_type,
        'title': title,
        'weight': weight,
        **pricing_data
    }


if __name__ == '__main__':
    # Example usage
    import json

    url = "https://www.bricklink.com/v2/catalog/catalogitem.page?S=31113-1"
    result = scrape_bricklink_item(url)
    print(json.dumps(result, indent=2))
