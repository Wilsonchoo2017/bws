/**
 * BricklinkParser - Pure functions for parsing Bricklink HTML
 *
 * Responsibilities (Single Responsibility Principle):
 * - Parse HTML documents
 * - Extract pricing data
 * - Extract item information
 * - URL parsing and validation
 *
 * This service follows SOLID principles:
 * - SRP: Only handles parsing logic
 * - OCP: Extensible through new parsing functions
 * - Pure functions: No side effects, easy to test
 */

import {
  DOMParser,
  type HTMLDocument,
} from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";

/**
 * Price data structure
 */
export interface PriceData {
  currency: string;
  amount: number;
}

/**
 * Pricing box structure (one of the 4 boxes on price guide page)
 */
export interface PricingBox {
  times_sold?: number;
  total_lots?: number;
  total_qty?: number;
  min_price?: PriceData;
  avg_price?: PriceData;
  qty_avg_price?: PriceData;
  max_price?: PriceData;
}

/**
 * Complete Bricklink item data
 */
export interface BricklinkData {
  item_id: string;
  item_type: string;
  title: string | null;
  weight: string | null;
  image_url: string | null;
  six_month_new: PricingBox | null;
  six_month_used: PricingBox | null;
  current_new: PricingBox | null;
  current_used: PricingBox | null;
}

/**
 * Parsed URL information
 */
export interface BricklinkUrlInfo {
  itemType: string;
  itemId: string;
}

// Regular expressions for price extraction
const RE_TIMES_SOLD = /Times Sold:\s*(\d+)/i;
const RE_TOTAL_LOTS = /Total Lots:\s*(\d+)/i;
const RE_TOTAL_QTY = /Total Qty:\s*(\d+)/i;
const RE_MIN_PRICE = /Min Price:\s*([A-Z]+)\s+([\d,\.]+)/i;
const RE_AVG_PRICE = /Avg Price:\s*([A-Z]+)\s+([\d,\.]+)/i;
const RE_QTY_AVG_PRICE = /Qty Avg Price:\s*([A-Z]+)\s+([\d,\.]+)/i;
const RE_MAX_PRICE = /Max Price:\s*([A-Z]+)\s+([\d,\.]+)/i;

/**
 * Valid Bricklink item types
 */
const VALID_ITEM_TYPES = ["P", "S", "M", "G", "C", "I", "O", "B"] as const;
export type BricklinkItemType = typeof VALID_ITEM_TYPES[number];

/**
 * Parse Bricklink URL to extract item type and ID
 * Pure function - no side effects
 */
export function parseBricklinkUrl(url: string): BricklinkUrlInfo {
  try {
    const urlObj = new URL(url);
    const params = new URLSearchParams(urlObj.search);

    // Detect item type (P, S, M, G, C, I, O, B)
    for (const key of VALID_ITEM_TYPES) {
      if (params.has(key)) {
        const itemId = params.get(key);
        if (itemId) {
          return {
            itemType: key,
            itemId,
          };
        }
      }
    }

    throw new Error(
      `Could not extract item type and ID from URL. Expected one of: ${
        VALID_ITEM_TYPES.join(", ")
      }`,
    );
  } catch (error) {
    throw new Error(`Invalid Bricklink URL: ${error.message}`);
  }
}

/**
 * Extract pricing box data from a box element
 * Pure function - no side effects
 */
export function extractPriceBox(boxText: string): PricingBox | null {
  // Check if box has "(unavailable)" message
  if (boxText.toLowerCase().includes("(unavailable)")) {
    return null;
  }

  const data: PricingBox = {};

  // Extract counts
  const timesSold = boxText.match(RE_TIMES_SOLD);
  if (timesSold) data.times_sold = parseInt(timesSold[1]);

  const totalLots = boxText.match(RE_TOTAL_LOTS);
  if (totalLots) data.total_lots = parseInt(totalLots[1]);

  const totalQty = boxText.match(RE_TOTAL_QTY);
  if (totalQty) data.total_qty = parseInt(totalQty[1]);

  // Extract prices
  const minPrice = boxText.match(RE_MIN_PRICE);
  if (minPrice) {
    data.min_price = {
      currency: minPrice[1].toUpperCase(),
      amount: parseFloat(minPrice[2].replace(/,/g, "")),
    };
  }

  const avgPrice = boxText.match(RE_AVG_PRICE);
  if (avgPrice) {
    data.avg_price = {
      currency: avgPrice[1].toUpperCase(),
      amount: parseFloat(avgPrice[2].replace(/,/g, "")),
    };
  }

  const qtyAvgPrice = boxText.match(RE_QTY_AVG_PRICE);
  if (qtyAvgPrice) {
    data.qty_avg_price = {
      currency: qtyAvgPrice[1].toUpperCase(),
      amount: parseFloat(qtyAvgPrice[2].replace(/,/g, "")),
    };
  }

  const maxPrice = boxText.match(RE_MAX_PRICE);
  if (maxPrice) {
    data.max_price = {
      currency: maxPrice[1].toUpperCase(),
      amount: parseFloat(maxPrice[2].replace(/,/g, "")),
    };
  }

  return Object.keys(data).length > 0 ? data : null;
}

/**
 * Parse item information from HTML
 * Pure function - no side effects
 */
export function parseItemInfo(html: string): {
  title: string | null;
  weight: string | null;
  image_url: string | null;
} {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  if (!doc) {
    throw new Error("Failed to parse item HTML");
  }

  // Extract basic info
  const titleElem = doc.querySelector("h1#item-name-title");
  const title = titleElem?.textContent?.trim() || null;

  const weightElem = doc.querySelector("span#item-weight-info");
  const weight = weightElem?.textContent?.trim() || null;

  // Extract image URL
  const image_url = extractImageUrl(doc);

  return { title, weight, image_url };
}

/**
 * Extract image URL from Bricklink item page
 * Pure function - no side effects
 */
export function extractImageUrl(doc: HTMLDocument): string | null {
  // Try to find the main product image
  // Bricklink typically shows the image in an <img> tag with id "ItemEditForm:largeImg" or similar

  // First try: large image in item edit form
  let imgElem = doc.querySelector("img#ItemEditForm\\:largeImg");
  if (imgElem) {
    const src = imgElem.getAttribute("src");
    if (src) return normalizeImageUrl(src);
  }

  // Second try: image in the main catalog display
  imgElem = doc.querySelector("img[id*='largeImg']");
  if (imgElem) {
    const src = imgElem.getAttribute("src");
    if (src) return normalizeImageUrl(src);
  }

  // Third try: any img in the item image container
  imgElem = doc.querySelector("div#item-image-block img, div.item-image img");
  if (imgElem) {
    const src = imgElem.getAttribute("src");
    if (src) return normalizeImageUrl(src);
  }

  // Fourth try: look for images in the page that contain "img.bricklink.com"
  const allImages = doc.querySelectorAll("img");
  for (const img of allImages) {
    const src = (img as unknown as Element).getAttribute("src");
    if (src && (src.includes("img.bricklink.com") || src.includes("brickimg"))) {
      // Avoid small icons and thumbnails
      if (!src.includes("/icon/") && !src.includes("_thumb") && !src.includes("small")) {
        return normalizeImageUrl(src);
      }
    }
  }

  return null;
}

/**
 * Normalize Bricklink image URL to get the highest quality version
 * Pure function - no side effects
 */
function normalizeImageUrl(url: string): string {
  // Ensure absolute URL
  if (url.startsWith("//")) {
    return `https:${url}`;
  }
  if (url.startsWith("/")) {
    return `https://www.bricklink.com${url}`;
  }
  return url;
}

/**
 * Parse price guide from HTML
 * Pure function - no side effects
 */
export function parsePriceGuide(html: string): {
  six_month_new: PricingBox | null;
  six_month_used: PricingBox | null;
  current_new: PricingBox | null;
  current_used: PricingBox | null;
} {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  if (!doc) {
    throw new Error("Failed to parse price guide HTML");
  }

  // Extract pricing boxes (4 boxes: 6mo new, 6mo used, current new, current used)
  // The boxes are in the row with bgcolor="#C0C0C0" which contains the summary statistics
  const priceBoxes = doc.querySelectorAll(
    'tr[bgcolor="#C0C0C0"] > td',
  );

  const pricingData = {
    six_month_new: null as PricingBox | null,
    six_month_used: null as PricingBox | null,
    current_new: null as PricingBox | null,
    current_used: null as PricingBox | null,
  };

  if (priceBoxes.length >= 4) {
    pricingData.six_month_new = extractPriceBox(
      priceBoxes[0]?.textContent || "",
    );
    pricingData.six_month_used = extractPriceBox(
      priceBoxes[1]?.textContent || "",
    );
    pricingData.current_new = extractPriceBox(
      priceBoxes[2]?.textContent || "",
    );
    pricingData.current_used = extractPriceBox(
      priceBoxes[3]?.textContent || "",
    );
  }

  return pricingData;
}

/**
 * Build price guide URL from item info
 * Pure function - no side effects
 */
export function buildPriceGuideUrl(
  itemType: string,
  itemId: string,
): string {
  return `https://www.bricklink.com/catalogPG.asp?${itemType}=${itemId}`;
}

/**
 * Compare two pricing boxes to check if data has changed
 * Pure function - no side effects
 */
export function hasDataChanged(
  oldData: PricingBox | null,
  newData: PricingBox | null,
): boolean {
  // If one is null and the other isn't, it's a change
  if ((oldData === null) !== (newData === null)) return true;
  if (oldData === null && newData === null) return false;

  // Deep comparison of pricing data
  return JSON.stringify(oldData) !== JSON.stringify(newData);
}

/**
 * Check if any pricing data has changed between old and new data
 * Pure function - no side effects
 */
export function hasAnyPricingChanged(
  oldData: {
    six_month_new: PricingBox | null;
    six_month_used: PricingBox | null;
    current_new: PricingBox | null;
    current_used: PricingBox | null;
  },
  newData: {
    six_month_new: PricingBox | null;
    six_month_used: PricingBox | null;
    current_new: PricingBox | null;
    current_used: PricingBox | null;
  },
): boolean {
  return (
    hasDataChanged(oldData.six_month_new, newData.six_month_new) ||
    hasDataChanged(oldData.six_month_used, newData.six_month_used) ||
    hasDataChanged(oldData.current_new, newData.current_new) ||
    hasDataChanged(oldData.current_used, newData.current_used)
  );
}

/**
 * Validate Bricklink URL
 * Pure function - no side effects
 */
export function isValidBricklinkUrl(url: string): boolean {
  try {
    parseBricklinkUrl(url);
    return true;
  } catch {
    return false;
  }
}
