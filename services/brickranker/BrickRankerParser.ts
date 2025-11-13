/**
 * BrickRankerParser - Pure functions for parsing BrickRanker retirement tracker HTML
 *
 * Responsibilities (Single Responsibility Principle):
 * - Parse HTML documents from BrickRanker retirement tracker
 * - Extract retirement data for LEGO sets
 * - Extract set information (name, number, year, retirement date, theme)
 * - URL parsing and validation
 *
 * This service follows SOLID principles:
 * - SRP: Only handles parsing logic
 * - OCP: Extensible through new parsing functions
 * - Pure functions: No side effects, easy to test
 */

import {
  DOMParser,
  type Element,
} from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";

/**
 * Retirement item data structure
 */
export interface RetirementItemData {
  setNumber: string;
  setName: string;
  yearReleased: number | null;
  retiringSoon: boolean;
  expectedRetirementDate: string | null;
  theme: string;
  imageUrl: string | null;
}

/**
 * Parse result containing all items from all themes
 */
export interface BrickRankerParseResult {
  items: RetirementItemData[];
  totalItems: number;
  themes: string[];
}

/**
 * Parse the main HTML document to extract retirement tracker data
 * Pure function - no side effects
 *
 * @param html - HTML content from BrickRanker retirement tracker page
 * @returns Parsed retirement item data
 */
export function parseRetirementTrackerPage(
  html: string,
): BrickRankerParseResult {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  if (!doc) {
    throw new Error("Failed to parse HTML document");
  }

  const items: RetirementItemData[] = [];
  const themes = new Set<string>();

  // Find all tables on the page (each theme has its own table)
  const tables = doc.querySelectorAll("table");

  for (const table of tables) {
    // Find the theme name - usually in a heading before the table
    const theme = findThemeForTable(table as Element);
    if (theme) {
      themes.add(theme);
    }

    // Parse all rows in the table (skip header row)
    const rows = (table as Element).querySelectorAll("tr");

    for (let i = 1; i < rows.length; i++) {
      const row = rows[i] as Element;
      const itemData = parseTableRow(row, theme || "Unknown");

      if (itemData) {
        items.push(itemData);
      }
      // Note: Rows without valid data (e.g., placeholder images) are silently skipped
    }
  }

  return {
    items,
    totalItems: items.length,
    themes: Array.from(themes),
  };
}

/**
 * Find the theme name associated with a table
 * Looks for headings (h2, h3) before the table
 *
 * @param table - The table element
 * @returns Theme name or null
 */
function findThemeForTable(table: Element): string | null {
  let currentElement = table.previousElementSibling;

  // Walk backwards through siblings to find a heading
  while (currentElement) {
    const tagName = currentElement.tagName.toLowerCase();

    if (tagName === "h2" || tagName === "h3" || tagName === "h4") {
      return currentElement.textContent?.trim() || null;
    }

    currentElement = currentElement.previousElementSibling;
  }

  return null;
}

/**
 * Parse a single table row to extract retirement item data
 * Pure function - no side effects
 *
 * @param row - Table row element
 * @param theme - Theme name for this row
 * @returns Parsed item data or null if invalid
 */
function parseTableRow(
  row: Element,
  theme: string,
): RetirementItemData | null {
  try {
    const cells = row.querySelectorAll("td");

    if (cells.length < 3) {
      return null; // Not enough data
    }

    // Extract data from cells
    // BrickRanker structure (4 columns):
    // Column 0: Product image/name (with link)
    // Column 1: Year released
    // Column 2: Expected retirement date
    // Column 3: Buy now button (optional)
    // Note: "Retiring soon!" tag may appear in various places

    const nameCell = cells[0] as Element;
    const yearCell = cells[1] as Element;
    const retirementDateCell = cells[2] as Element;

    // Extract set name from link or text
    const setName = extractSetName(nameCell);
    if (!setName) {
      return null;
    }

    // Extract LEGO set number from set name or link
    const setNumber = extractSetNumber(nameCell, setName);
    if (!setNumber) {
      return null;
    }

    // Extract year released
    const yearReleased = extractYear(yearCell);

    // Extract expected retirement date
    const expectedRetirementDate = extractRetirementDate(retirementDateCell);

    // Check for "Retiring Soon!" tag anywhere in the row
    const retiringSoon = checkRetiringSoonTag(row);

    // Extract image URL from name cell
    const imageUrl = extractImageUrl(nameCell);

    return {
      setNumber,
      setName,
      yearReleased,
      retiringSoon,
      expectedRetirementDate,
      theme,
      imageUrl,
    };
  } catch (error) {
    console.error("Error parsing table row:", error);
    return null;
  }
}

/**
 * Extract set name from name cell
 *
 * @param nameCell - Cell containing set name/link
 * @returns Set name or null
 */
function extractSetName(nameCell: Element): string | null {
  // Try to find all links in the cell
  const links = nameCell.querySelectorAll("a");

  for (const link of links) {
    const text = link.textContent?.trim();
    // Skip empty links and "Buy now" type links
    if (text && text.length > 0 && !text.toLowerCase().includes("buy")) {
      return text;
    }
  }

  // Fallback to cell text, but clean it up
  let text = nameCell.textContent?.trim() || "";

  // Remove common noise like "Buy now", "Retiring soon!", etc.
  text = text.replace(/Buy now/gi, "").replace(/Retiring soon!/gi, "").trim();

  return text.length > 0 ? text : null;
}

/**
 * Extract LEGO set number from name cell or set name
 * LEGO set numbers typically follow patterns like: 75192, 10294, 21325, etc.
 * On BrickRanker, set numbers are in URLs like: /75377-1/invisible-hand
 *
 * @param nameCell - Cell containing set info
 * @param setName - Set name text
 * @returns Set number or null
 */
function extractSetNumber(nameCell: Element, setName: string): string | null {
  // Try to extract from link href - BrickRanker uses pattern like /75377-1/invisible-hand
  const link = nameCell.querySelector("a");
  if (link?.getAttribute("href")) {
    const href = link.getAttribute("href") || "";

    // Pattern 1: /XXXXX-X/set-name (most common on BrickRanker)
    let match = href.match(/\/(\d{4,5})-\d+\//);
    if (match) {
      return match[1];
    }

    // Pattern 2: /sets/XXXXX
    match = href.match(/\/sets\/(\d{4,5})/);
    if (match) {
      return match[1];
    }

    // Pattern 3: Any 4-5 digit number in URL
    match = href.match(/(\d{4,5})/);
    if (match) {
      return match[1];
    }
  }

  // Try to extract from set name - LEGO set numbers are typically 4-5 digits
  // Pattern: word boundary + 4-5 digits + word boundary
  const numberMatch = setName.match(/\b(\d{4,5})\b/);
  if (numberMatch) {
    return numberMatch[1];
  }

  // Try to extract from any text in the cell
  const cellText = nameCell.textContent || "";
  const cellMatch = cellText.match(/\b(\d{4,5})\b/);
  if (cellMatch) {
    return cellMatch[1];
  }

  return null;
}

/**
 * Extract year from year cell
 *
 * @param yearCell - Cell containing year
 * @returns Year as number or null
 */
function extractYear(yearCell: Element): number | null {
  const text = yearCell.textContent?.trim();
  if (!text) {
    return null;
  }

  // Extract 4-digit year
  const match = text.match(/\b(20\d{2})\b/);
  if (match) {
    return parseInt(match[1], 10);
  }

  // Try direct parsing
  const year = parseInt(text, 10);
  if (!isNaN(year) && year >= 2000 && year <= 2030) {
    return year;
  }

  return null;
}

/**
 * Extract retirement date from retirement date cell
 *
 * @param retirementDateCell - Cell containing retirement date
 * @returns Retirement date string or null
 */
function extractRetirementDate(retirementDateCell: Element): string | null {
  const text = retirementDateCell.textContent?.trim();

  if (!text || text === "-" || text === "N/A" || text === "") {
    return null;
  }

  return text;
}

/**
 * Check if row has "Retiring Soon!" tag
 *
 * @param row - Table row element
 * @returns true if retiring soon tag is present
 */
function checkRetiringSoonTag(row: Element): boolean {
  const text = row.textContent || "";
  return text.toLowerCase().includes("retiring soon");
}

/**
 * Extract image URL from name cell
 * Pure function - no side effects
 *
 * @param nameCell - Cell containing product image and name
 * @returns Image URL or null
 */
function extractImageUrl(nameCell: Element): string | null {
  // Look for img tags in the name cell
  const imgElement = nameCell.querySelector("img");

  if (!imgElement) {
    return null;
  }

  // Try src attribute
  const src = imgElement.getAttribute("src");
  if (src) {
    return normalizeImageUrl(src);
  }

  // Try data-src (lazy loading)
  const dataSrc = imgElement.getAttribute("data-src");
  if (dataSrc) {
    return normalizeImageUrl(dataSrc);
  }

  return null;
}

/**
 * Normalize image URL to absolute URL
 * Pure function - no side effects
 *
 * @param url - Relative or absolute URL
 * @returns Absolute URL
 */
function normalizeImageUrl(url: string): string {
  // Already absolute
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }

  // Protocol-relative
  if (url.startsWith("//")) {
    return `https:${url}`;
  }

  // Relative to domain
  if (url.startsWith("/")) {
    return `https://brickranker.com${url}`;
  }

  // Relative to current path
  return `https://brickranker.com/${url}`;
}

/**
 * Validate BrickRanker retirement tracker URL
 * Pure function - no side effects
 *
 * @param url - URL to validate
 * @returns true if valid BrickRanker retirement tracker URL
 */
export function isValidBrickRankerUrl(url: string): boolean {
  try {
    const urlObj = new URL(url);
    return (
      urlObj.hostname === "brickranker.com" &&
      urlObj.pathname.includes("retirement-tracker")
    );
  } catch {
    return false;
  }
}

/**
 * Parse HTML document to DOM
 * Helper function for testing
 *
 * @param html - HTML string
 * @returns Parsed document or null
 */
export function parseHtmlDocument(html: string) {
  const parser = new DOMParser();
  return parser.parseFromString(html, "text/html");
}
