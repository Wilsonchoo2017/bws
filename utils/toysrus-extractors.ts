/**
 * Toys"R"Us HTML Extractors
 *
 * Following SOLID principles, each function has a single responsibility
 * for extracting specific data from Toys"R"Us product HTML
 */

import {
  type Document,
  DOMParser,
  type Element,
} from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";
import { extractLegoSetNumber, parsePriceToCents } from "../db/utils.ts";

export interface ToysRUsProduct {
  productId: string;
  name: string;
  brand: string | null;
  price: number | null; // in cents
  priceBeforeDiscount: number | null; // in cents
  image: string | null;
  sku: string | null;
  categoryNumber: string | null;
  categoryName: string | null;
  ageRange: string | null;
  legoSetNumber: string | null;
  productUrl: string | null;
  rawData: Record<string, unknown>;
}

/**
 * Parse HTML string into a DOM document
 */
export function parseHtmlDocument(html: string): Document {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  if (!doc) {
    throw new Error("Failed to parse HTML document");
  }
  return doc;
}

/**
 * Extract product data from data-metadata JSON attribute
 * This is the primary extraction method for Toys"R"Us products
 */
export function extractProductFromMetadata(
  element: Element,
): Partial<ToysRUsProduct> | null {
  try {
    const metadataAttr = element.getAttribute("data-metadata");
    if (!metadataAttr) return null;

    // Unescape HTML entities and parse JSON
    const unescaped = metadataAttr
      .replace(/&quot;/g, '"')
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">");

    const metadata = JSON.parse(unescaped);

    return {
      sku: metadata.sku || null,
      name: metadata.name || metadata.name_local || null,
      brand: metadata.brand || null,
      price: metadata.price
        ? parsePriceToCents(metadata.price.toString())
        : null,
      categoryNumber: Array.isArray(metadata.akeneo_categoryNumber)
        ? metadata.akeneo_categoryNumber.join(",")
        : metadata.akeneo_catAndSubCatNumber || null,
      categoryName: metadata.category || null,
      ageRange: metadata.akeneo_ageRangeYears || null,
      rawData: metadata,
    };
  } catch (error) {
    console.warn("Failed to parse data-metadata:", error);
    return null;
  }
}

/**
 * Extract product ID from data-pid attribute
 */
export function extractProductId(element: Element): string | null {
  return element.getAttribute("data-pid");
}

/**
 * Extract product name from element (fallback method)
 */
export function extractProductName(element: Element): string | null {
  const nameSelectors = [
    ".card-title",
    ".product-name",
    ".product-title",
    "[itemprop='name']",
    "a.card-link",
  ];

  for (const selector of nameSelectors) {
    const nameEl = element.querySelector(selector);
    if (nameEl?.textContent?.trim()) {
      return nameEl.textContent.trim();
    }
  }

  return null;
}

/**
 * Extract price from element (fallback method)
 */
export function extractPrice(element: Element): number | null {
  const priceSelectors = [
    ".price .sales",
    "[itemprop='price']",
    ".sales-price",
    ".price-sales",
  ];

  for (const selector of priceSelectors) {
    const priceEl = element.querySelector(selector);
    if (priceEl?.textContent?.trim()) {
      try {
        const priceText = priceEl.textContent.trim();
        return parsePriceToCents(priceText);
      } catch {
        continue;
      }
    }
  }

  return null;
}

/**
 * Extract before discount price
 */
export function extractPriceBeforeDiscount(element: Element): number | null {
  const selectors = [
    ".price-standard",
    ".list-price",
    ".strike-through",
    ".price .strike-through",
  ];

  for (const selector of selectors) {
    const priceEl = element.querySelector(selector);
    if (priceEl?.textContent?.trim()) {
      try {
        const priceText = priceEl.textContent.trim();
        return parsePriceToCents(priceText);
      } catch {
        continue;
      }
    }
  }

  return null;
}

/**
 * Extract product image URL
 */
export function extractImage(element: Element): string | null {
  // Try data-src first (lazy loading), then src
  const imgSelectors = [
    ".card-image-container img",
    ".product-image img",
    ".tile-image img",
    "img.tile-image",
  ];

  for (const selector of imgSelectors) {
    const imgEl = element.querySelector(selector);
    if (imgEl) {
      const dataSrc = imgEl.getAttribute("data-src");
      const src = imgEl.getAttribute("src");
      const imageUrl = dataSrc || src;

      if (imageUrl && !imageUrl.includes("placeholder")) {
        // Handle relative URLs
        if (imageUrl.startsWith("//")) {
          return "https:" + imageUrl;
        } else if (imageUrl.startsWith("/")) {
          return "https://www.toysrus.com.my" + imageUrl;
        }
        return imageUrl;
      }
    }
  }

  return null;
}

/**
 * Extract product URL
 */
export function extractProductUrl(element: Element): string | null {
  const linkSelectors = [
    "a.card-link",
    "a.card-image-container",
    ".product-link",
    "a[href*='.html']",
  ];

  for (const selector of linkSelectors) {
    const linkEl = element.querySelector(selector);
    if (linkEl) {
      const href = linkEl.getAttribute("href");
      if (href) {
        // Handle relative URLs
        if (href.startsWith("//")) {
          return "https:" + href;
        } else if (href.startsWith("/")) {
          return "https://www.toysrus.com.my" + href;
        } else if (href.startsWith("http")) {
          return href;
        }
      }
    }
  }

  return null;
}

/**
 * Generate a unique product ID using UUID
 */
export function generateProductId(
  _sku: string | null,
  _pid: string | null,
  _name: string | null,
): string {
  return crypto.randomUUID();
}

/**
 * Parse a single product item element
 * Orchestrates all extraction functions with hybrid approach
 */
export function parseProductItem(element: Element): ToysRUsProduct | null {
  try {
    // Try JSON extraction first (faster and more reliable)
    const metadataProduct = extractProductFromMetadata(element);
    const pid = extractProductId(element);

    // Fallback to HTML parsing for missing fields
    const name = metadataProduct?.name || extractProductName(element);
    const brand = metadataProduct?.brand || null;
    const price = metadataProduct?.price ?? extractPrice(element);
    const priceBeforeDiscount = extractPriceBeforeDiscount(element) || null;
    const image = extractImage(element);
    const productUrl = extractProductUrl(element);
    const legoSetNumber = name ? extractLegoSetNumber(name) : null;

    // Generate product ID
    const productId = generateProductId(
      metadataProduct?.sku || null,
      pid,
      name,
    );

    const product: ToysRUsProduct = {
      productId,
      name: name || "Unknown Product",
      brand,
      price,
      priceBeforeDiscount,
      image,
      sku: metadataProduct?.sku || pid,
      categoryNumber: metadataProduct?.categoryNumber || null,
      categoryName: metadataProduct?.categoryName || null,
      ageRange: metadataProduct?.ageRange || null,
      legoSetNumber,
      productUrl,
      rawData: metadataProduct?.rawData || {},
    };

    return product;
  } catch (error) {
    console.error("Error parsing product item:", error);
    return null;
  }
}

/**
 * Main entry point: Parse Toys"R"Us HTML and extract all products
 */
export function parseToysRUsHtml(html: string): ToysRUsProduct[] {
  const doc = parseHtmlDocument(html);
  const products: ToysRUsProduct[] = [];

  // Find all product tiles
  const productElements = doc.querySelectorAll(
    ".product-tile.product-data",
  );

  console.log(`Found ${productElements.length} product elements`);

  for (const element of productElements) {
    // querySelectorAll returns Elements, safe to cast
    const product = parseProductItem(element as unknown as Element);
    if (product) {
      products.push(product);
    }
  }

  return products;
}
