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
  type Element,
  type HTMLDocument,
  type NodeList,
} from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";
import { scraperLogger as logger } from "../../utils/logger.ts";

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
 * Past sale transaction data
 */
export interface PastSaleTransaction {
  date_sold: Date;
  condition: "new" | "used";
  price: PriceData;
  seller_location?: string;
  quantity?: number;
}

/**
 * Monthly sales summary data
 */
export interface MonthlySalesSummary {
  month: string; // YYYY-MM format
  condition: "new" | "used";
  times_sold: number;
  total_quantity: number;
  min_price?: PriceData;
  max_price?: PriceData;
  avg_price?: PriceData;
}

/**
 * Complete Bricklink item data
 */
export interface BricklinkData {
  item_id: string;
  item_type: string;
  title: string | null;
  weight: string | null;
  year_released: number | null;
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
  // Check if box has "(unavailable)" message - this means no sales, not missing data
  if (boxText.toLowerCase().includes("(unavailable)")) {
    return {
      times_sold: 0,
      total_lots: 0,
      total_qty: 0,
    };
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
  year_released: number | null;
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

  // Extract year released
  const year_released = extractYearReleased(html);

  // Extract image URL
  const image_url = extractImageUrl(doc);

  return { title, weight, year_released, image_url };
}

/**
 * Extract year released from Bricklink item page HTML
 * Pure function - no side effects
 *
 * Pattern: Year Released: <a ...>2023</a>
 */
export function extractYearReleased(html: string): number | null {
  try {
    // Pattern: Year Released: <a ...>2023</a>
    const yearMatch = html.match(/Year Released:.*?(\d{4})/i);
    if (yearMatch && yearMatch[1]) {
      const year = parseInt(yearMatch[1], 10);
      // Validate year is reasonable (between 1949 and current year + 2)
      const currentYear = new Date().getFullYear();
      if (year >= 1949 && year <= currentYear + 2) {
        return year;
      }
    }
    return null;
  } catch (error) {
    logger.error("Failed to extract year released", {
      error: (error as Error).message,
    });
    return null;
  }
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
    // @ts-ignore - deno_dom types don't include getAttribute
    const src = img.getAttribute("src");
    if (
      src && (src.includes("img.bricklink.com") || src.includes("brickimg"))
    ) {
      // Avoid small icons and thumbnails
      if (
        !src.includes("/icon/") && !src.includes("_thumb") &&
        !src.includes("small")
      ) {
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

  // Check if this is an error page
  const pageTitle = doc.querySelector("title")?.textContent || "";
  if (
    pageTitle.toLowerCase().includes("not found") ||
    html.includes("notFound.asp")
  ) {
    throw new Error(
      "Price guide page not found - item may not exist on Bricklink",
    );
  }

  // Extract pricing boxes (4 boxes: 6mo new, 6mo used, current new, current used)
  // The boxes are in the row with bgcolor="#C0C0C0" which contains the summary statistics
  const priceBoxes = doc.querySelectorAll(
    'tr[bgcolor="#C0C0C0"] > td',
  );

  // Validate that we found the expected price table structure
  if (priceBoxes.length === 0) {
    throw new Error(
      "Price guide table structure not found. " +
        "Page may have been redirected or Bricklink's HTML structure has changed.",
    );
  }

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
 * Check if a pricing box has any price field (min, avg, qty_avg, or max price)
 * Pure function - no side effects
 */
export function hasAnyPriceField(box: PricingBox | null): boolean {
  if (!box) return false;
  return !!(box.min_price || box.avg_price || box.qty_avg_price ||
    box.max_price);
}

/**
 * Validate that pricing data contains at least one price field
 * Throws error if no price information is found
 * Pure function - no side effects (other than throwing)
 */
export function validatePricingData(data: {
  six_month_new: PricingBox | null;
  six_month_used: PricingBox | null;
  current_new: PricingBox | null;
  current_used: PricingBox | null;
}): void {
  const hasAnyPrice = hasAnyPriceField(data.six_month_new) ||
    hasAnyPriceField(data.six_month_used) ||
    hasAnyPriceField(data.current_new) ||
    hasAnyPriceField(data.current_used);

  if (!hasAnyPrice) {
    throw new Error(
      "No price information found in any pricing box (6-month new/used, current new/used)",
    );
  }
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

/**
 * Parse Past Sales transactions from the catalog item page
 * Pure function - no side effects
 *
 * The Past Sales section typically appears in a table with columns:
 * - Date Sold
 * - Condition (New/Used)
 * - Unit Price
 * - Seller Location (sometimes)
 *
 * @param html - HTML content from the catalog item page
 * @returns Array of past sale transactions
 */
export function parsePastSales(html: string): PastSaleTransaction[] {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  if (!doc) {
    throw new Error("Failed to parse Past Sales HTML");
  }

  logger.info("Parsing past sales from HTML", {
    htmlSize: html.length,
  });

  // Check for "(Unavailable)" indicator in HTML
  if (html.includes("(Unavailable)") || html.includes("Unavailable")) {
    logger.info("Past sales data marked as unavailable by BrickLink", {
      status: "UNAVAILABLE",
    });
  }

  const transactions: PastSaleTransaction[] = [];

  // Look for the "Past Sales" section
  // Bricklink uses various table structures, but typically has a table with sales data
  // The table is often inside a div or under a heading containing "Past Sales" or "Sold Listings"

  // Strategy: Find all tables and look for one that contains sale dates and prices
  const tables = doc.querySelectorAll("table");

  logger.info("Scanning HTML for sales tables", {
    tablesFound: tables.length,
  });

  let tableIndex = 0;
  for (const table of tables) {
    tableIndex++;

    // @ts-ignore - deno_dom types issue with Node vs Element
    const rows = table.querySelectorAll("tr");

    // Check if this looks like a sales table (has date and price columns)
    const headerRow = rows[0];
    const headerText = headerRow?.textContent?.toLowerCase() || "";

    // Look for indicators this is a sales table
    const isSalesTable = headerText.includes("date") ||
      headerText.includes("sold") ||
      headerText.includes("price");

    if (!isSalesTable) {
      logger.debug(`Table ${tableIndex}: No match`, {
        reason: "headers don't contain 'date', 'sold', or 'price'",
        headerText: headerText.substring(0, 100),
      });
      continue;
    }

    logger.info(`Table ${tableIndex}: Matched sales table`, {
      headerText: headerText.substring(0, 100),
      rowCount: rows.length - 1, // excluding header
    });

    // Parse data rows (skip header)
    let rowsParsed = 0;
    let rowsSkipped = 0;
    let rowsAdded = 0;

    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      // @ts-ignore - deno_dom types issue with Node vs Element
      const cells = row.querySelectorAll("td");

      if (cells.length < 2) {
        rowsSkipped++;
        logger.debug(`  Row ${i}: SKIPPED - insufficient cells`, {
          cellCount: cells.length,
        });
        continue;
      }

      rowsParsed++;

      try {
        // Extract data from cells
        // Format varies, but typically: Date | Condition | Price | Location
        let dateText = "";
        let conditionText = "";
        let priceText = "";
        let locationText = "";
        let quantityText = "";

        // Collect all cell texts for logging
        const cellTexts: string[] = [];

        // Try to identify columns by content patterns
        for (const cell of cells) {
          const text = cell.textContent?.trim() || "";
          cellTexts.push(text);

          // Date pattern: MM/DD/YYYY or similar
          if (/\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}/.test(text) && !dateText) {
            dateText = text;
          } // Condition: "New" or "Used"
          else if (
            /^(new|used)$/i.test(text.toLowerCase()) && !conditionText
          ) {
            conditionText = text.toLowerCase();
          } // Price: Currency + number (USD 12.34, US $12.34, etc.)
          else if (
            /[A-Z]{2,3}\s*\$?\s*[\d,\.]+/.test(text) && !priceText
          ) {
            priceText = text;
          } // Quantity: Just a number
          else if (/^\d+$/.test(text) && !quantityText) {
            quantityText = text;
          } // Location: Country code or name
          else if (
            /^[A-Z]{2}$/.test(text) || text.length > 2 && !locationText
          ) {
            locationText = text;
          }
        }

        // Check for "(Unavailable)" in row
        const rowText = cellTexts.join(" ");
        if (
          rowText.includes("(Unavailable)") || rowText.includes("Unavailable")
        ) {
          rowsSkipped++;
          logger.debug(`  Row ${i}: SKIPPED - "(Unavailable)" detected`, {
            rowText: rowText.substring(0, 100),
          });
          continue;
        }

        // Skip if we don't have minimum required data
        if (!dateText || !priceText) {
          rowsSkipped++;
          logger.debug(`  Row ${i}: SKIPPED - missing required data`, {
            dateExtracted: dateText || null,
            conditionExtracted: conditionText || null,
            priceExtracted: priceText || null,
            locationExtracted: locationText || null,
            quantityExtracted: quantityText || null,
            cellTexts: cellTexts.join(" | "),
          });
          continue;
        }

        // Parse date
        const dateParts = dateText.match(
          /(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})/,
        );
        if (!dateParts) {
          rowsSkipped++;
          logger.debug(`  Row ${i}: SKIPPED - date parsing failed`, {
            dateText,
          });
          continue;
        }

        let month = parseInt(dateParts[1]);
        let day = parseInt(dateParts[2]);
        let year = parseInt(dateParts[3]);

        // Handle 2-digit years
        if (year < 100) {
          year += year < 50 ? 2000 : 1900;
        }

        // Check if format is DD/MM/YYYY or MM/DD/YYYY
        // If month > 12, it must be DD/MM/YYYY
        if (month > 12) {
          [month, day] = [day, month];
        }

        const dateSold = new Date(year, month - 1, day);

        // Parse price
        const priceMatch = priceText.match(/([A-Z]{2,3})\s*\$?\s*([\d,\.]+)/);
        if (!priceMatch) {
          rowsSkipped++;
          logger.debug(`  Row ${i}: SKIPPED - price parsing failed`, {
            priceText,
          });
          continue;
        }

        const currency = priceMatch[1].toUpperCase();
        const amount = parseFloat(priceMatch[2].replace(/,/g, ""));

        // Parse condition (default to "used" if not specified)
        const condition = (conditionText === "new" ? "new" : "used") as
          | "new"
          | "used";

        // Parse quantity if available
        const quantity = quantityText ? parseInt(quantityText) : undefined;

        // Create transaction object
        const transaction: PastSaleTransaction = {
          date_sold: dateSold,
          condition,
          price: {
            currency,
            amount,
          },
        };

        if (locationText) {
          transaction.seller_location = locationText;
        }

        if (quantity) {
          transaction.quantity = quantity;
        }

        transactions.push(transaction);
        rowsAdded++;

        logger.debug(`  Row ${i}: ✓ ADDED`, {
          date: dateText,
          condition: conditionText || "(default: used)",
          price: priceText,
          location: locationText || null,
          quantity: quantityText || null,
        });
      } catch (error) {
        // Skip malformed rows
        rowsSkipped++;
        logger.warn(`  Row ${i}: SKIPPED - parsing error`, {
          error: error.message,
        });
        continue;
      }
    }

    logger.info(`Table ${tableIndex} parsing complete`, {
      rowsParsed,
      rowsSkipped,
      rowsAdded,
      transactionsFound: transactions.length,
    });

    // If we found transactions, we've found the right table
    if (transactions.length > 0) break;
  }

  logger.info("Past sales parsing complete", {
    totalTransactionsFound: transactions.length,
  });

  return transactions;
}

/**
 * Parse monthly sales summaries from BrickLink HTML
 * Handles the monthly aggregate format where sales are grouped by month
 *
 * Example structure:
 *   November 2025
 *   Qty  Each
 *    1   ~MYR 224.14
 *    1   ~MYR 289.29
 *
 * @param html Raw HTML from BrickLink price guide page
 * @returns Array of monthly sales summaries
 */
export function parseMonthlySales(html: string): MonthlySalesSummary[] {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  if (!doc) {
    throw new Error("Failed to parse monthly sales HTML");
  }

  logger.info("Parsing monthly sales from HTML", {
    htmlSize: html.length,
  });

  const monthlySummaries: MonthlySalesSummary[] = [];

  // Find all tables
  const tables = doc.querySelectorAll("table");

  logger.info("Scanning HTML for monthly sales tables", {
    tablesFound: tables.length,
  });

  // Track current month and condition as we scan through tables
  let currentMonth: string | null = null;
  let currentCondition: "new" | "used" | null = null;

  for (let tableIndex = 0; tableIndex < tables.length; tableIndex++) {
    const table = tables[tableIndex];
    // @ts-ignore - deno_dom types issue
    const rows = table.querySelectorAll("tr");

    if (rows.length === 0) continue;

    // Check if this table contains a month header
    const firstRowText = rows[0]?.textContent?.trim() || "";

    // Check for "Currently Available" and skip it
    if (firstRowText.includes("Currently Available")) {
      currentMonth = null; // Reset month context
      logger.debug("Skipping 'Currently Available' section", { tableIndex });
      continue;
    }

    // Month pattern: "November 2025", "October 2025", etc.
    // Use \s+ to match any whitespace (including non-breaking spaces)
    const monthMatch = firstRowText.match(/(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})/);

    if (monthMatch) {
      // This is a month header table
      const monthName = monthMatch[1];
      const year = monthMatch[2];

      // Convert month name to number (January = 01, etc.)
      const monthMap: { [key: string]: string } = {
        "January": "01", "February": "02", "March": "03", "April": "04",
        "May": "05", "June": "06", "July": "07", "August": "08",
        "September": "09", "October": "10", "November": "11", "December": "12"
      };

      currentMonth = `${year}-${monthMap[monthName]}`;

      logger.debug(`Found month header: ${monthName} ${year}`, {
        formattedMonth: currentMonth,
        tableIndex
      });

      continue;
    }

    // Check if this table is a sales data table (has "Qty" and "Each" headers)
    const headerText = firstRowText.toLowerCase();
    if (headerText.includes("qty") && headerText.includes("each")) {
      if (!currentMonth) {
        logger.debug("Found sales table but no month context (skipping)", { tableIndex });
        continue;
      }

      // Determine condition based on context
      // Look backwards in the HTML to find "New" or "Used" heading
      // For now, we'll extract from the broader context
      currentCondition = determineConditionFromContext(
        table as Element,
        tables,
        tableIndex,
      );

      if (!currentCondition) {
        logger.warn("Could not determine condition for sales table", {
          tableIndex,
          month: currentMonth
        });
        continue;
      }

      logger.info(`Parsing sales data table`, {
        month: currentMonth,
        condition: currentCondition,
        tableIndex,
        rowCount: rows.length
      });

      // Parse the sales data rows
      const prices: number[] = [];
      const quantities: number[] = [];
      let rowsProcessed = 0;
      let rowsSkippedDueToCellCount = 0;
      let rowsSkippedSummary = 0;
      let rowsSkippedEmpty = 0;
      let rowsSkippedQtyParse = 0;
      let rowsSkippedPriceParse = 0;
      let currency: string | null = null;

      for (let i = 1; i < rows.length; i++) {
        rowsProcessed++;
        const row = rows[i];
        // @ts-ignore: deno-dom type inference issue with querySelectorAll
        const cells = row.querySelectorAll("td");

        if (cells.length < 2) {
          rowsSkippedDueToCellCount++;
          continue;
        }

        const cellTexts = Array.from(cells).map((c) =>
          (c as Element).textContent?.trim() || ""
        );

        // Skip summary rows (e.g., "Times Sold:", "Qty Avg:", etc.)
        const rowText = cellTexts.join(" ");
        if (
          rowText.includes("Times Sold:") ||
          rowText.includes("Total Lots:") ||
          rowText.includes("Total Qty:") ||
          rowText.includes("Avg:") ||
          rowText.includes("Min:") ||
          rowText.includes("Max:")
        ) {
          rowsSkippedSummary++;
          continue;
        }

        // Skip horizontal rule rows
        if (rowText.trim() === "") {
          rowsSkippedEmpty++;
          continue;
        }

        // Try to parse quantity and price
        // Note: First cell is often empty/blank, so Qty is usually in cellTexts[1] and Price in cellTexts[2]
        // But we need to find the actual Qty and Price columns dynamically
        let qtyText = "";
        let priceText = "";

        // Find quantity (should be a number) and price (should have currency code)
        for (let j = 0; j < cellTexts.length; j++) {
          const text = cellTexts[j];
          if (!qtyText && /^\d+$/.test(text)) {
            qtyText = text;
          } else if (!priceText && /([A-Z]{2,3})\s+([\d,\.]+)/.test(text)) {
            priceText = text;
          }
        }

        // Quantity should be a simple number
        const qtyMatch = qtyText.match(/^(\d+)$/);
        if (!qtyMatch) {
          rowsSkippedQtyParse++;
          continue;
        }

        const quantity = parseInt(qtyMatch[1]);

        // Price pattern: ~MYR 224.14 or MYR 224.14 or ~USD 50.00
        // Need to handle non-breaking spaces and extra whitespace
        const priceMatch = priceText.match(/~?\s*([A-Z]{2,3})\s+([\d,\.]+)/);
        if (!priceMatch) {
          rowsSkippedPriceParse++;
          continue;
        }

        const priceCurrency = priceMatch[1].toUpperCase();
        const priceAmount = parseFloat(priceMatch[2].replace(/,/g, ""));

        if (!currency) {
          currency = priceCurrency;
        } else if (currency !== priceCurrency) {
          logger.warn(`Currency mismatch in table`, {
            expected: currency,
            found: priceCurrency,
            month: currentMonth
          });
        }

        prices.push(priceAmount);
        quantities.push(quantity);
      }

      // Log parsing statistics
      logger.info(`Table parsing complete`, {
        month: currentMonth,
        condition: currentCondition,
        rowsProcessed,
        rowsSkippedDueToCellCount,
        rowsSkippedSummary,
        rowsSkippedEmpty,
        rowsSkippedQtyParse,
        rowsSkippedPriceParse,
        salesFound: prices.length
      });

      // Create summary if we found sales data
      if (prices.length > 0 && currency) {
        const totalQuantity = quantities.reduce((sum, q) => sum + q, 0);
        const minPrice = Math.min(...prices);
        const maxPrice = Math.max(...prices);
        const avgPrice = prices.reduce((sum, p) => sum + p, 0) / prices.length;

        const summary: MonthlySalesSummary = {
          month: currentMonth,
          condition: currentCondition,
          times_sold: prices.length,
          total_quantity: totalQuantity,
          min_price: { currency, amount: minPrice },
          max_price: { currency, amount: maxPrice },
          avg_price: { currency, amount: avgPrice }
        };

        monthlySummaries.push(summary);

        logger.info(`Added monthly summary`, {
          month: currentMonth,
          condition: currentCondition,
          timesSold: prices.length,
          totalQty: totalQuantity,
          avgPrice: avgPrice.toFixed(2)
        });
      }
    }
  }

  logger.info("Monthly sales parsing complete", {
    totalSummariesFound: monthlySummaries.length
  });

  // Deduplicate summaries by month+condition
  // Multiple tables for same month/condition may exist due to HTML structure
  const deduped = new Map<string, MonthlySalesSummary>();
  for (const summary of monthlySummaries) {
    const key = `${summary.month}-${summary.condition}`;
    deduped.set(key, summary); // Last one wins (they should all be identical)
  }

  const finalSummaries = Array.from(deduped.values());

  logger.info("After deduplication", {
    originalCount: monthlySummaries.length,
    finalCount: finalSummaries.length
  });

  return finalSummaries;
}

/**
 * Determine condition (new/used) from the table's context
 * BrickLink shows New and Used sales in separate columns with different bgcolor values:
 * - New: bgcolor="EEEEEE" (light gray)
 * - Used: bgcolor="DDDDDD" (dark gray)
 */
function determineConditionFromContext(
  currentTable: Element,
  allTables: NodeList,
  currentIndex: number,
): "new" | "used" | null {
  // Walk up the DOM tree to find the parent <td> element
  let parent = currentTable.parentElement;
  while (parent && parent.tagName !== "TD") {
    parent = parent.parentElement;
  }

  if (parent) {
    // Check the bgcolor attribute
    const bgcolor = parent.getAttribute("bgcolor")?.toLowerCase();
    if (bgcolor === "eeeeee") {
      return "new";
    } else if (bgcolor === "dddddd") {
      return "used";
    }
  }

  // Fallback: look for explicit "New" or "Used" text in nearby elements
  const precedingTables = Array.from(allTables).slice(
    Math.max(0, currentIndex - 10),
    currentIndex,
  );
  for (const table of precedingTables.reverse()) {
    const boldElements = (table as Element).querySelectorAll("b, strong");
    for (const el of boldElements) {
      const text = (el as Element).textContent?.trim().toLowerCase() || "";
      if (text === "new") return "new";
      if (text === "used") return "used";
    }
  }

  // Default to "new" if unable to determine
  return "new";
}
