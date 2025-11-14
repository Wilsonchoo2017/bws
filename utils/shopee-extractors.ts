/**
 * Shopee HTML extraction utilities.
 * Contains focused functions for extracting specific data from Shopee HTML elements.
 * Follows Single Responsibility Principle - each function has one clear purpose.
 */

import {
  DOMParser,
  type Element,
} from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";
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
  price_before_discount: number | null;
  discount_percentage: number | null;
  promotional_badges: string[];
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
 * Helper: Removes image elements and extracts clean text
 */
function cleanTextFromElement(element: Element): string | null {
  const clonedDiv = element.cloneNode(true) as Element;
  const images = clonedDiv.querySelectorAll("img");
  Array.from(images).forEach((img) => (img as Element).remove());
  return clonedDiv.textContent?.trim() || null;
}

/**
 * Helper: Checks if text is a valid product name
 */
function isValidProductName(text: string | null): boolean {
  if (!text || text.length < 10) return false;
  // Exclude price/sold/percentage patterns
  return !text.match(/^(RM|sold|\d+%)/i);
}

/**
 * Strategy: Extract name from common class patterns
 */
function extractNameFromClassPatterns(item: Element): string | null {
  const patterns = [
    'div[class*="title"]',
    'div[class*="line-clamp-2"]',
    'div[class*="product-name"]',
    'div[class*="item-name"]',
  ];

  for (const pattern of patterns) {
    const element = item.querySelector(pattern);
    if (element && element.textContent) {
      const name = cleanTextFromElement(element);
      if (name && name.length > 0) return name;
    }
  }
  return null;
}

/**
 * Strategy: Extract name from image alt text
 */
function extractNameFromImageAlt(item: Element): string | null {
  const linkElement = item.querySelector("a");
  if (!linkElement) return null;

  const imgElement = linkElement.querySelector("img[alt]");
  const altText = imgElement?.getAttribute("alt");

  if (altText && altText.length > 0 && !altText.includes("image")) {
    return altText;
  }
  return null;
}

/**
 * Strategy: Extract name from divs with substantial text
 */
function extractNameFromSubstantialText(item: Element): string | null {
  const textDivs = item.querySelectorAll('div[class*="min-h"]');

  for (const div of Array.from(textDivs)) {
    if (!(div as Element).textContent) continue;

    const text = cleanTextFromElement(div as Element);
    if (isValidProductName(text)) {
      return text;
    }
  }
  return null;
}

/**
 * Extracts product name using multiple fallback strategies
 */
export function extractProductName(item: Element): string | null {
  return extractNameFromClassPatterns(item) ||
    extractNameFromImageAlt(item) ||
    extractNameFromSubstantialText(item);
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
 * Helper: Checks if text looks like a price
 */
function looksLikePrice(text: string): boolean {
  return text.includes("RM") || /^\d+\.?\d*$/.test(text);
}

/**
 * Strategy: Extract price from class patterns
 */
function extractPriceFromPatterns(item: Element): {
  price: number | null;
  priceString: string;
} | null {
  const patterns = [
    'span[class*="price"]',
    'div[class*="price"]',
    'span[class*="truncate"][class*="text-base"]',
  ];

  for (const pattern of patterns) {
    const element = item.querySelector(pattern);
    if (element && element.textContent) {
      const priceText = element.textContent.trim();
      if (looksLikePrice(priceText)) {
        const price = parsePriceToCents(priceText);
        if (price !== null) {
          return { price, priceString: priceText };
        }
      }
    }
  }
  return null;
}

/**
 * Strategy: Extract price by scanning for RM currency
 */
function extractPriceFromCurrency(item: Element): {
  price: number | null;
  priceString: string;
} | null {
  const allSpans = item.querySelectorAll("span");

  for (const span of Array.from(allSpans)) {
    const text = (span as Element).textContent?.trim();
    if (!text || !(text.startsWith("RM") || text.match(/^\d+\.\d{2}$/))) {
      continue;
    }

    let priceText = text;
    const parent = (span as Element).parentElement;
    if (parent && parent.textContent) {
      const parentText = parent.textContent.trim();
      if (parentText.includes("RM") && parentText.length < 20) {
        priceText = parentText;
      }
    }

    const price = parsePriceToCents(priceText);
    if (price !== null) {
      return { price, priceString: priceText };
    }
  }
  return null;
}

/**
 * Extracts price using multiple fallback strategies
 */
export function extractPrice(
  item: Element,
): { price: number | null; priceString: string } {
  return extractPriceFromPatterns(item) ||
    extractPriceFromCurrency(item) ||
    { price: null, priceString: "" };
}

/**
 * Helper: Checks if text contains "sold" keyword
 */
function containsSoldKeyword(text: string): boolean {
  return text.toLowerCase().includes("sold");
}

/**
 * Strategy: Extract sold units from class patterns
 */
function extractSoldFromPatterns(item: Element): {
  units_sold: number | null;
  units_sold_string: string;
} | null {
  const patterns = [
    'div[class*="sold"]',
    'span[class*="sold"]',
    'div[class*="truncate"][class*="text-shopee-black87"]', // Common Shopee pattern
  ];

  for (const pattern of patterns) {
    const element = item.querySelector(pattern);
    if (element && element.textContent) {
      const soldText = element.textContent.trim();
      if (containsSoldKeyword(soldText)) {
        const units_sold = normalizeSoldUnits(soldText);
        if (units_sold !== null && units_sold > 0) {
          return { units_sold, units_sold_string: soldText };
        }
      }
    }
  }
  return null;
}

/**
 * Strategy: Extract sold units by scanning for "sold" keyword
 */
function extractSoldFromKeyword(item: Element): {
  units_sold: number | null;
  units_sold_string: string;
} | null {
  const allDivs = item.querySelectorAll("div");

  for (const div of Array.from(allDivs)) {
    const text = (div as Element).textContent?.trim();
    if (!text || !containsSoldKeyword(text)) continue;

    // Must be short and actually contain sold keyword
    if (text.length < 30 && text.length > 3) {
      const units_sold = normalizeSoldUnits(text);
      if (units_sold !== null && units_sold > 0) {
        return { units_sold, units_sold_string: text };
      }
    }
  }
  return null;
}

/**
 * Strategy: Extract "k+" pattern followed by "sold"
 */
function extractSoldFromPattern(item: Element): {
  units_sold: number | null;
  units_sold_string: string;
} | null {
  const textContent = item.textContent || "";

  // Look specifically for patterns like "1k+ sold" or "666 sold"
  const soldMatch = textContent.match(/(\d+\.?\d*k?\+?\s*sold)/i);
  if (soldMatch) {
    const soldText = soldMatch[1].trim();
    const units_sold = normalizeSoldUnits(soldText);
    if (units_sold !== null && units_sold > 0) {
      return { units_sold, units_sold_string: soldText };
    }
  }

  return null;
}

/**
 * Extracts sold units using multiple fallback strategies
 */
export function extractSoldUnits(
  item: Element,
): { units_sold: number | null; units_sold_string: string } {
  return extractSoldFromPatterns(item) ||
    extractSoldFromPattern(item) ||
    extractSoldFromKeyword(item) ||
    { units_sold: null, units_sold_string: "N/A" };
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
 * Normalizes badge text to simple tag format
 * Converts to lowercase and removes all non-alphanumeric characters
 * @param badge - Raw badge text
 * @returns Normalized tag string
 */
export function normalizeBadgeToTag(badge: string): string {
  return badge.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/**
 * Extracts promotional badges from a Shopee item element
 * Looks for text badges like "Shopee Lagi Murah", "COD", "Sea Shipping"
 * Also checks for flag label images indicating verified products
 * @param item - DOM element for the product
 * @returns Array of normalized badge tags
 */
export function extractPromotionalBadges(item: Element): string[] {
  const badges: string[] = [];

  // Extract text badges (Shopee Lagi Murah, COD, etc.)
  // Target: small badges with h-4 class and truncate spans
  const badgeElements = item.querySelectorAll(
    'div[class*="flex items-center"][class*="h-4"] span.truncate',
  );

  for (const badge of Array.from(badgeElements)) {
    const text = (badge as Element).textContent?.trim();
    // Exclude numeric-only text (prices, percentages)
    if (text && !text.match(/^[\d\.,RM%\-\s]+$/)) {
      const normalized = normalizeBadgeToTag(text);
      if (normalized && !badges.includes(normalized)) {
        badges.push(normalized);
      }
    }
  }

  // Check for flag label (verified products)
  const flagLabel = item.querySelector('img[alt="flag-label"]');
  if (flagLabel && !badges.includes("verified")) {
    badges.push("verified");
  }

  return badges;
}

/**
 * Extracts discount percentage from a Shopee item element
 * Looks for discount badges like "-3%", "-6%", "-12%"
 * @param item - DOM element for the product
 * @returns Discount percentage as number (e.g., 3 for "-3%") or null
 */
export function extractDiscountPercentage(item: Element): number | null {
  // Target: discount badges with pink background
  const discountBadges = item.querySelectorAll(
    'div[class*="bg-shopee-pink"]',
  );

  for (const badge of Array.from(discountBadges)) {
    const text = (badge as Element).textContent?.trim();
    // Match patterns like "-3%", "-12%"
    const match = text?.match(/^-?(\d+(?:\.\d+)?)%$/);
    if (match) {
      return parseFloat(match[1]);
    }
  }

  return null;
}

/**
 * Calculates original price before discount
 * @param currentPrice - Current price in cents
 * @param discountPercentage - Discount percentage (e.g., 3 for 3%)
 * @returns Original price in cents or null
 */
export function calculatePriceBeforeDiscount(
  currentPrice: number | null,
  discountPercentage: number | null,
): number | null {
  if (
    currentPrice === null || discountPercentage === null ||
    discountPercentage <= 0
  ) {
    return null;
  }

  // Formula: original = current / (1 - discount/100)
  const original = currentPrice / (1 - discountPercentage / 100);
  return Math.round(original);
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
    const promotionalBadges = extractPromotionalBadges(item);
    const discountPercentage = extractDiscountPercentage(item);
    const priceBeforeDiscount = calculatePriceBeforeDiscount(
      price,
      discountPercentage,
    );

    return {
      product_id: productId,
      product_name: productName,
      brand,
      price,
      price_string: priceString,
      price_before_discount: priceBeforeDiscount,
      discount_percentage: discountPercentage,
      promotional_badges: promotionalBadges,
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

  Array.from(items).forEach((item, index) => {
    // Filter out non-Element nodes
    if (item.nodeType !== 1) return; // 1 = Element node
    const product = parseProductItem(
      item as Element,
      index,
      shopUsername,
    );
    if (product) {
      products.push(product);
    }
  });

  return products;
}
