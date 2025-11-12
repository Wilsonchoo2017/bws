#!/usr/bin/env python3
from bs4 import BeautifulSoup
import re
import glob
import csv

def parse_shopee_html(html_content):
    """Parse Shopee HTML and extract product information"""
    soup = BeautifulSoup(html_content, 'html.parser')
    products = []

    # Find all product items
    items = soup.find_all('div', class_='shop-search-result-view__item')

    print(f"Found {len(items)} product items")

    for idx, item in enumerate(items, 1):
        try:
            # Extract product name - look for LEGO and 5-digit code
            product_name = None
            text_elements = item.find_all(string=re.compile(r'LEGO.*\d{5}', re.IGNORECASE))
            if text_elements:
                product_name = text_elements[0].strip()

            if not product_name:
                name_div = item.find('div', class_=re.compile(r'line-clamp-2'))
                if name_div:
                    product_name = name_div.get_text(strip=True)

            # Extract price
            price = None
            price_span = item.find('span', class_=re.compile(r'text-base/5.*font-medium'))
            if price_span:
                price = price_span.get_text(strip=True).replace(',', '')

            if not price:
                price_match = re.search(r'RM\s*([0-9,.]+)', item.get_text())
                if price_match:
                    price = price_match.group(1).replace(',', '')

            # Extract sold units
            sold_units = None
            sold_div = item.find('div', class_=re.compile(r'text-shopee-black87.*text-xs'))
            if sold_div:
                sold_match = re.search(r'([0-9kK.+,]+)\s*sold', sold_div.get_text())
                if sold_match:
                    sold_units = sold_match.group(1).strip()

            if not sold_units:
                sold_match = re.search(r'([0-9kK.+,]+)\s*sold', item.get_text())
                if sold_match:
                    sold_units = sold_match.group(1).strip()

            if product_name:
                products.append({
                    'Product Name': product_name,
                    'Price (RM)': price if price else 'N/A',
                    'Units Sold': sold_units if sold_units else 'N/A'
                })

                print(f"Product {idx}: {product_name} | RM{price} | {sold_units} sold")

        except Exception as e:
            print(f"Error parsing item {idx}: {e}")

    return products

def main():
    # Parse all shop-listing-*.txt files
    files = sorted(glob.glob('shop-listing-*.txt'))
    print(f"Found {len(files)} shop listing files\n")

    all_products = []
    for file in files:
        print(f"\nParsing {file}...")
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
            products = parse_shopee_html(content)
            all_products.extend(products)

    # Export to CSV
    if all_products:
        with open('shopee-products.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Product Name', 'Price (RM)', 'Units Sold'])
            writer.writeheader()
            writer.writerows(all_products)

        print(f"\n✓ Exported {len(all_products)} products to shopee-products.csv")

if __name__ == '__main__':
    main()
