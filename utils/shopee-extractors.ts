/**
 * Shopee HTML extraction utilities.
 * Contains focused functions for extracting specific data from Shopee HTML elements.
 * Follows Single Responsibility Principle - each function has one clear purpose.
 */

import { DOMParser } from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";
import {
  extractLegoSetNumber,
  normalizeSoldUnits,
  parsePriceToCents,
} from "../db/utils.ts";

/**
 * Parsed Shopee product structure
 */
export interface ParsedShopeeProduct {
  product_id: string;
  product_name: string;
  brand: string | null;
  price: number | null;
  price_string: string;
  units_sold: number | null;
  units_sold_string: string;
  lego_set_number: string | null;
  image: string | null;
  shop_id: number | null;
  shop_name: string | null;
  product_url: string | null;
}

/**
 * Parses HTML document
 * @param htmlContent - Raw HTML string
 * @returns Parsed Document object
 */
export function parseHtmlDocument(htmlContent: string) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlContent, "text/html");
  if (!doc) {
    throw new Error("Failed to parse HTML content");
  }
  return doc;
}

/**
 * Extracts product name from a Shopee item element
 * @param item - DOM element for the product
 * @returns Product name or null if not found
 */
export function extractProductName(item: Element): string | null {
  const nameDiv = item.querySelector('div[class*="title"]');
  if (!nameDiv || !nameDiv.textContent) return null;

  const nameElement = nameDiv.querySelector("span");
  const name = nameElement?.textContent?.trim() || nameDiv.textContent.trim();

  return name || null;
}

/**
 * Extracts product URL from a Shopee item element
 * @param item - DOM element for the product
 * @returns Product URL or null if not found
 */
export function extractProductUrl(item: Element): string | null {
  const linkElement = item.querySelector("a");
  if (!linkElement) return null;

  const href = linkElement.getAttribute("href");
  if (!href) return null;

  // Convert relative URLs to absolute URLs
  if (href.startsWith("/")) {
    return `https://shopee.com.my${href}`;
  }

  return href;
}

/**
 * Generates product ID from URL, query params, or product name
 * @param item - DOM element for the product
 * @param productUrl - Product URL
 * @param productName - Product name
 * @param shopUsername - Shop username from source URL
 * @returns Product ID
 */
export function generateProductId(
  _item: Element,
  _productUrl: string | null,
  _productName: string,
  _shopUsername: string,
): string {
  // Return a UUID for product identification
  return crypto.randomUUID();
}

/**
 * Extracts price information from a Shopee item element
 * @param item - DOM element for the product
 * @returns Object with price in cents and price string
 */
export function extractPrice(
  item: Element,
): { price: number | null; priceString: string } {
  const priceSpan = item.querySelector(
    'span[class*="price"]',
  );

  if (!priceSpan || !priceSpan.textContent) {
    return { price: null, priceString: "" };
  }

  const priceText = priceSpan.textContent.trim();
  const price = parsePriceToCents(priceText);

  return { price, priceString: priceText };
}

/**
 * Extracts sold units from a Shopee item element
 * @param item - DOM element for the product
 * @returns Object with normalized units sold and original string
 */
export function extractSoldUnits(
  item: Element,
): { units_sold: number | null; units_sold_string: string } {
  const soldSpan = item.querySelector(
    'div[class*="sold"]',
  );

  if (!soldSpan || !soldSpan.textContent) {
    return { units_sold: null, units_sold_string: "N/A" };
  }

  const soldText = soldSpan.textContent.trim();
  const units_sold = normalizeSoldUnits(soldText);

  return { units_sold, units_sold_string: soldText || "N/A" };
}

/**
 * Extracts product image URL from a Shopee item element
 * @param item - DOM element for the product
 * @returns Image URL or null if not found
 */
export function extractImage(item: Element): string | null {
  const imgElement = item.querySelector("img");
  if (!imgElement) return null;

  // Try srcset first (higher quality), then src
  const srcset = imgElement.getAttribute("srcset");
  if (srcset) {
    // Parse srcset to get the first URL
    const firstUrl = srcset.split(",")[0].trim().split(" ")[0];
    return firstUrl || null;
  }

  const src = imgElement.getAttribute("src");
  return src || null;
}

/**
 * Extracts brand information from product name
 * @param productName - Product name
 * @returns Brand name or null
 */
export function extractBrand(productName: string): string | null {
  // Simple brand extraction - could be enhanced based on patterns
  const lowerName = productName.toLowerCase();

  if (lowerName.includes("lego")) return "LEGO";
  if (lowerName.includes("mega")) return "Mega Bloks";
  if (lowerName.includes("duplo")) return "LEGO Duplo";

  return null;
}

/**
 * Extracts shop information from a Shopee item element
 * @param item - DOM element for the product
 * @param shopUsername - Fallback shop username
 * @returns Object with shop ID and shop name
 */
export function extractShopInfo(
  item: Element,
  shopUsername: string,
): { shopId: number | null; shopName: string | null } {
  let shopName: string | null = null;
  const shopId: number | null = null;

  // Try to find shop name element
  const shopNameElement = item.querySelector(
    'div[class*="shop-name"]',
  );

  if (shopNameElement && shopNameElement.textContent) {
    shopName = shopNameElement.textContent.trim() || null;
  }

  // Fallback to shop username from URL if no shop name in HTML
  if (!shopName) {
    shopName = shopUsername;
  }

  return { shopId, shopName };
}

/**
 * Parses a single Shopee product item element
 * @param item - DOM element for the product
 * @param index - Index of the item in the list
 * @param shopUsername - Shop username from source URL
 * @returns Parsed product object or null if parsing fails
 */
export function parseProductItem(
  item: Element,
  index: number,
  shopUsername: string,
): ParsedShopeeProduct | null {
  try {
    const productName = extractProductName(item);
    if (!productName) {
      console.warn(`Product ${index + 1}: No product name found`);
      return null;
    }

    const productUrl = extractProductUrl(item);
    const productId = generateProductId(
      item,
      productUrl,
      productName,
      shopUsername,
    );
    const { price, priceString } = extractPrice(item);
    const { units_sold, units_sold_string } = extractSoldUnits(item);
    const legoSetNumber = extractLegoSetNumber(productName);
    const image = extractImage(item);
    const brand = extractBrand(productName);
    const { shopId, shopName } = extractShopInfo(item, shopUsername);

    return {
      product_id: productId,
      product_name: productName,
      brand,
      price,
      price_string: priceString,
      units_sold,
      units_sold_string,
      lego_set_number: legoSetNumber,
      image,
      shop_id: shopId,
      shop_name: shopName,
      product_url: productUrl,
    };
  } catch (error) {
    console.error(`Error parsing product ${index + 1}:`, error);
    return null;
  }
}

/**
 * Parses Shopee HTML to extract product information
 * @param htmlContent - Raw HTML string
 * @param shopUsername - Shop username from source URL
 * @returns Array of parsed products
 */
export function parseShopeeHtml(
  htmlContent: string,
  shopUsername: string,
): ParsedShopeeProduct[] {
  const doc = parseHtmlDocument(htmlContent);
  const items = doc.querySelectorAll(".shop-search-result-view__item");

  if (items.length === 0) {
    console.warn("No product items found in HTML");
    return [];
  }

  const products: ParsedShopeeProduct[] = [];

  items.forEach((item, index) => {
    // Filter out non-Element nodes
    if (item.nodeType !== 1) return; // 1 = Element node
    const product = parseProductItem(
      item as unknown as Element,
      index,
      shopUsername,
    );
    if (product) {
      products.push(product);
    }
  });

  return products;
}
