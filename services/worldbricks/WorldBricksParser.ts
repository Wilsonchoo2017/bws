/**
 * WorldBricksParser - Pure functions for parsing WorldBricks.com HTML
 *
 * Responsibilities (Single Responsibility Principle):
 * - Parse HTML documents from WorldBricks.com
 * - Extract LEGO set information
 * - Extract year released and retired (HIGH PRIORITY)
 * - Extract secondary data (designer, parts, dimensions)
 * - Parse JSON-LD structured data
 *
 * This service follows SOLID principles:
 * - SRP: Only handles parsing logic
 * - OCP: Extensible through new parsing functions
 * - Pure functions: No side effects, easy to test
 */

import {
  DOMParser,
  Element,
  HTMLDocument,
} from "https://deno.land/x/deno_dom@v0.1.38/deno-dom-wasm.ts";

/**
 * Complete WorldBricks LEGO set data
 */
export interface WorldBricksData {
  set_number: string;
  set_name: string | null;
  description: string | null;
  year_released: number | null;
  year_retired: number | null;
  designer: string | null;
  parts_count: number | null;
  dimensions: string | null;
  image_url: string | null;
}

/**
 * Dimensions structure from JSON-LD
 */
interface DimensionValue {
  "@type": string;
  value: string;
  unitCode: string;
}

/**
 * JSON-LD Product schema
 */
interface ProductSchema {
  "@type": string;
  name?: string;
  description?: string;
  productID?: string;
  image?: string;
  depth?: DimensionValue;
  width?: DimensionValue;
  height?: DimensionValue;
}

/**
 * Parse WorldBricks HTML to extract LEGO set data
 * Pure function - no side effects
 *
 * @param html - Raw HTML string from WorldBricks page
 * @param sourceUrl - Original URL (for debugging)
 * @returns Parsed LEGO set data
 */
export function parseWorldBricksHtml(
  html: string,
  sourceUrl: string,
): WorldBricksData {
  const doc = new DOMParser().parseFromString(html, "text/html");

  if (!doc) {
    throw new Error("Failed to parse HTML document");
  }

  // Extract set number from URL or meta tags
  const setNumber = extractSetNumber(doc, sourceUrl);

  if (!setNumber) {
    throw new Error("Could not extract LEGO set number from page");
  }

  return {
    set_number: setNumber,
    set_name: extractSetName(doc),
    description: extractDescription(doc),
    year_released: extractYearReleased(doc),
    year_retired: extractYearRetired(doc),
    designer: extractDesigner(doc),
    parts_count: extractPartsCount(doc),
    dimensions: extractDimensions(doc),
    image_url: extractImageUrl(doc),
  };
}

/**
 * Extract LEGO set number from page
 * Checks: JSON-LD, meta tags, URL pattern
 */
function extractSetNumber(doc: HTMLDocument, sourceUrl: string): string | null {
  // Try JSON-LD structured data first
  const jsonLd = extractJsonLdProduct(doc);
  if (jsonLd?.productID) {
    return jsonLd.productID;
  }

  // Try meta tags
  const twitterTitle = doc.querySelector('meta[name="twitter:title"]')
    ?.getAttribute("content");
  if (twitterTitle) {
    const match = twitterTitle.match(/\b(\d{4,5})\b/);
    if (match) {
      return match[1];
    }
  }

  // Try URL pattern: /31009-Small-Cottage.html
  const urlMatch = sourceUrl.match(/\/(\d{4,5})-[^/]+\.html$/);
  if (urlMatch) {
    return urlMatch[1];
  }

  return null;
}

/**
 * Extract set name from page
 * Checks: Meta tags, title, JSON-LD
 */
function extractSetName(doc: HTMLDocument): string | null {
  // Try meta description
  const metaDesc = doc.querySelector('meta[name="twitter:description"]')
    ?.getAttribute("content");
  if (metaDesc) {
    // Format: "Download 31009 Small Cottage, Creator"
    const match = metaDesc.match(/\d+\s+([^,]+)/);
    if (match) {
      return match[1].trim();
    }
  }

  // Try page title
  const title = doc.querySelector("title")?.textContent;
  if (title) {
    // Format: "View LEGO® instruction 31009 Small Cottage - ..."
    const match = title.match(/\d+\s+([^-]+)/);
    if (match) {
      return match[1].trim();
    }
  }

  return null;
}

/**
 * Extract product description
 * Looks for .tab-value div containing description text
 */
function extractDescription(doc: HTMLDocument): string | null {
  // Look for description in tab content
  const descDiv = doc.querySelector(".tab-value");
  if (descDiv) {
    return descDiv.textContent?.trim() || null;
  }

  // Fallback to meta description
  const metaDesc = doc.querySelector('meta[name="description"]')?.getAttribute(
    "content",
  );
  return metaDesc?.trim() || null;
}

/**
 * Extract LEGO year field which contains release and/or retirement year
 * Located in: <h3>LEGO year:</h3> followed by <div class="tab-value">
 */
function extractLegoYearField(doc: HTMLDocument): string | null {
  // Find all h3 elements with "LEGO year:" text
  const headings = doc.querySelectorAll("h3.body_title");

  for (const heading of headings) {
    const text = heading.textContent?.trim();
    if (text && text.toLowerCase().includes("lego year")) {
      // Get the next sibling with class tab-value
      let sibling = (heading as Element).nextElementSibling;
      while (sibling) {
        if (sibling.classList && sibling.classList.contains("tab-value")) {
          return sibling.textContent?.trim() || null;
        }
        sibling = sibling.nextElementSibling;
      }
    }
  }

  return null;
}

/**
 * Extract year released (HIGH PRIORITY)
 * Checks multiple sources:
 * 1. LEGO year field: "YYYY - Retired YYYY" (extracts first year)
 * 2. LEGO year field: "YYYY" (single year)
 * 3. Description: "Released in YYYY"
 */
function extractYearReleased(doc: HTMLDocument): number | null {
  // First check LEGO year field
  const legoYear = extractLegoYearField(doc);
  if (legoYear) {
    // Look for "YYYY - Retired YYYY" pattern (e.g., "1980 - Retired 1982")
    const retiredMatch = legoYear.match(/(\d{4})\s*-\s*Retired\s*(\d{4})/i);
    if (retiredMatch) {
      return parseInt(retiredMatch[1], 10);
    }

    // Look for single year
    const yearMatch = legoYear.match(/(\d{4})/);
    if (yearMatch) {
      return parseInt(yearMatch[1], 10);
    }
  }

  // Fallback to description
  const description = extractDescription(doc);
  if (description) {
    // Look for "Released in 2013" pattern
    const releasedMatch = description.match(/Released in (\d{4})/i);
    if (releasedMatch) {
      return parseInt(releasedMatch[1], 10);
    }
  }

  return null;
}

/**
 * Extract year retired (HIGH PRIORITY)
 * Checks LEGO year field for "YYYY - Retired YYYY" pattern
 * Returns null if not found (many sets don't have retirement year)
 */
function extractYearRetired(doc: HTMLDocument): number | null {
  // Check LEGO year field
  const legoYear = extractLegoYearField(doc);
  if (legoYear) {
    // Look for "YYYY - Retired YYYY" pattern (e.g., "1980 - Retired 1982")
    const match = legoYear.match(/(\d{4})\s*-\s*Retired\s*(\d{4})/i);
    if (match) {
      return parseInt(match[2], 10); // Return the second year (retirement year)
    }
  }

  return null;
}

/**
 * Extract designer/creator information
 * Currently not available on WorldBricks - returns null
 */
function extractDesigner(_doc: HTMLDocument): string | null {
  // WorldBricks doesn't appear to have designer information
  // This would need to come from Brickset or official LEGO data
  return null;
}

/**
 * Extract parts count
 * Parses description for "XXX pieces" pattern
 */
function extractPartsCount(doc: HTMLDocument): number | null {
  const description = extractDescription(doc);

  if (description) {
    // Look for "271 pieces" pattern
    const match = description.match(/(\d+)\s+pieces/i);
    if (match) {
      return parseInt(match[1], 10);
    }
  }

  return null;
}

/**
 * Extract dimensions from JSON-LD Product schema
 * Returns formatted string: "WxDxH cm"
 */
function extractDimensions(doc: HTMLDocument): string | null {
  const jsonLd = extractJsonLdProduct(doc);

  if (jsonLd && jsonLd.width && jsonLd.height && jsonLd.depth) {
    const width = jsonLd.width.value;
    const depth = jsonLd.depth.value;
    const height = jsonLd.height.value;
    const unit = jsonLd.width.unitCode === "CMT" ? "cm" : jsonLd.width.unitCode;

    return `${width}×${depth}×${height} ${unit}`;
  }

  return null;
}

/**
 * Extract image URL
 * Checks: Meta tags (Open Graph), JSON-LD
 */
function extractImageUrl(doc: HTMLDocument): string | null {
  // Try Open Graph secure URL first
  const ogImage = doc.querySelector('meta[property="og:image:secure_url"]')
    ?.getAttribute("content");
  if (ogImage) {
    return ogImage;
  }

  // Try Twitter image
  const twitterImage = doc.querySelector('meta[name="twitter:image"]')
    ?.getAttribute("content");
  if (twitterImage) {
    return twitterImage;
  }

  // Try JSON-LD
  const jsonLd = extractJsonLdProduct(doc);
  if (jsonLd?.image) {
    // Add https: if protocol-relative
    const imageUrl = jsonLd.image.startsWith("//")
      ? `https:${jsonLd.image}`
      : jsonLd.image;
    return imageUrl;
  }

  return null;
}

/**
 * Extract and parse JSON-LD Product schema
 * Returns parsed Product schema or null
 */
function extractJsonLdProduct(doc: HTMLDocument): ProductSchema | null {
  try {
    const scripts = doc.querySelectorAll('script[type="application/ld+json"]');

    for (const script of scripts) {
      const content = script.textContent;
      if (!content) continue;

      try {
        const data = JSON.parse(content);

        // Check if it's a Product schema
        if (data["@type"] === "Product") {
          return data as ProductSchema;
        }
      } catch {
        // Skip invalid JSON blocks
        continue;
      }
    }
  } catch (error) {
    console.error("Error extracting JSON-LD:", error);
  }

  return null;
}

/**
 * Parse WorldBricks URL to extract set number
 * Pure function - no side effects
 *
 * URL pattern: https://www.worldbricks.com/en/instructions-number/30000/31000-31099/lego-set/31009-Small-Cottage.html
 *
 * @param url - WorldBricks URL
 * @returns Set number or null
 */
export function parseWorldBricksUrl(url: string): string | null {
  try {
    const match = url.match(/\/(\d{4,5})-[^/]+\.html$/);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

/**
 * Construct WorldBricks search URL from set number
 * This is the preferred method since direct URLs require knowing the set name
 *
 * @param setNumber - LEGO set number (e.g., "7834")
 * @returns Search URL
 */
export function constructSearchUrl(setNumber: string): string {
  return `https://www.worldbricks.com/en/all.html?search=${setNumber}`;
}

/**
 * Parse search results page to extract product URL
 * Looks for links matching the set number in search results
 *
 * @param html - Raw HTML from search results page
 * @param setNumber - LEGO set number being searched for
 * @returns Product page URL or null if not found
 */
export function parseSearchResults(
  html: string,
  setNumber: string,
): string | null {
  const doc = new DOMParser().parseFromString(html, "text/html");

  if (!doc) {
    return null;
  }

  // Look for links to product pages that match the set number
  // Pattern: href="/en/lego-instructions-year/.../lego-set/7834-Level-Crossing.html"
  const links = doc.querySelectorAll('a[href*="lego-set"]');

  for (const link of links) {
    const href = (link as Element).getAttribute("href");
    if (!href) continue;

    // Check if the link contains the set number
    const regex = new RegExp(`/${setNumber}-[^/]+\\.html`, "i");
    if (regex.test(href)) {
      // Convert relative URL to absolute
      if (href.startsWith("/")) {
        return `https://www.worldbricks.com${href}`;
      }
      return href;
    }
  }

  return null;
}

/**
 * Construct WorldBricks URL from set number and name
 * Note: This requires knowing the range grouping (e.g., 31000-31099)
 * which may require trial-and-error or additional data
 *
 * DEPRECATED: Use constructSearchUrl() + parseSearchResults() instead
 *
 * @param setNumber - LEGO set number (e.g., "31009")
 * @param setName - LEGO set name (e.g., "Small Cottage")
 * @returns Constructed URL or null if cannot determine range
 */
export function constructWorldBricksUrl(
  setNumber: string,
  setName?: string,
): string | null {
  try {
    const num = parseInt(setNumber, 10);

    // Determine range group (e.g., 31000-31099)
    const rangeStart = Math.floor(num / 100) * 100;
    const rangeEnd = rangeStart + 99;
    const majorRange = Math.floor(num / 10000) * 10000;

    // Format name for URL (kebab-case)
    const urlName = setName
      ? setName.replace(/\s+/g, "-").replace(/[^a-zA-Z0-9-]/g, "")
      : "Unknown";

    // Construct URL
    return `https://www.worldbricks.com/en/instructions-number/${majorRange}/${rangeStart}-${rangeEnd}/lego-set/${setNumber}-${urlName}.html`;
  } catch {
    return null;
  }
}

/**
 * Validate if HTML appears to be a valid WorldBricks product page
 * Checks for presence of key elements
 *
 * @param html - Raw HTML string
 * @returns true if appears to be valid product page
 */
export function isValidWorldBricksPage(html: string): boolean {
  // Check for key indicators
  return (
    html.includes("worldbricks.com") &&
    html.includes("LEGO") &&
    (html.includes("djcatalog2") || html.includes("Instructions"))
  );
}

/**
 * Extract theme from description
 * Parses for "part of the X theme" pattern
 *
 * @param description - Product description text
 * @returns Theme name or null
 */
export function extractThemeFromDescription(
  description: string,
): string | null {
  // Look for "part of the Creator theme" pattern
  const match = description.match(/part of the ([^,]+) theme/i);
  return match ? match[1].trim() : null;
}
