/**
 * BrickEconomy HTML extraction utilities.
 * Contains focused functions for extracting specific data from BrickEconomy product detail pages.
 * Follows Single Responsibility Principle - each function has one clear purpose.
 */

import { DOMParser } from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";
import {
  extractLegoSetNumber,
  parsePriceToCents,
} from "../db/utils.ts";

/**
 * Parsed BrickEconomy product structure
 */
export interface ParsedBrickEconomyProduct {
  product_id: string;
  product_name: string;
  lego_set_number: string | null;
  brand: string;

  // Pricing
  retail_price: number | null; // MSRP in cents
  market_value: number | null; // Current new/sealed value in cents
  used_value: number | null; // Used value in cents

  // Investment metrics
  growth_percent: string | null;
  annual_growth_percent: string | null;
  growth_90day_percent: string | null;

  // Predictions
  forecast_1year: number | null; // In cents
  forecast_5year: number | null; // In cents

  // Metadata
  pieces: number | null;
  minifigs: number | null;
  minifigs_value: number | null; // In cents
  ppp: number | null; // Price per piece in cents
  theme: string | null;
  subtheme: string | null;
  year: string | null;
  released: string | null;
  retired: string | null;
  availability: string | null;

  // Quick buy prices (in cents)
  ebay_lowest: number | null;
  ebay_highest: number | null;
  amazon_average: number | null;
  stockx_price: number | null;
  bricklink_lowest: number | null;
  bricklink_highest: number | null;

  // Additional
  image: string | null;
  upc: string | null;
  ean: string | null;

  // Raw data for complete storage
  raw_data: Record<string, any>;
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
 * Extracts set number and name from page header
 * @param doc - Parsed document
 * @returns Object with set number and name
 */
export function extractSetInfo(doc: Document): { setNumber: string | null; name: string | null } {
  const header = doc.querySelector("h1.setheader");
  if (!header || !header.textContent) {
    return { setNumber: null, name: null };
  }

  const fullText = header.textContent.trim();

  // Extract set number (supports formats like 76917, 76917-1, etc.)
  const setNumber = extractLegoSetNumber(fullText);

  // Name is the full text
  const name = fullText || null;

  return { setNumber, name };
}

/**
 * Extracts value from a row with specific label
 * @param doc - Parsed document
 * @param labelText - Text to search for in the row label
 * @returns Value text or null
 */
function extractRowValue(doc: Document, labelText: string): string | null {
  const rows = doc.querySelectorAll(".row.rowlist");

  for (const row of rows) {
    const label = row.querySelector(".text-muted");
    if (label && label.textContent?.trim().toLowerCase().includes(labelText.toLowerCase())) {
      const valueCol = row.querySelector(".col-xs-7");
      if (valueCol) {
        // Get text content, strip HTML tags and extra whitespace
        return valueCol.textContent?.trim() || null;
      }
    }
  }

  return null;
}

/**
 * Extracts numeric value from price string
 * @param priceStr - Price string like "$29.99", "£24.99", etc.
 * @returns Price in cents or null
 */
function extractNumericPrice(priceStr: string | null): number | null {
  if (!priceStr) return null;

  // Remove currency symbols and parse
  return parsePriceToCents(priceStr);
}

/**
 * Extracts percentage from string like "+33.38%" or "+6.40%"
 * @param percentStr - Percentage string
 * @returns Percentage as string (with sign) or null
 */
function extractPercentage(percentStr: string | null): string | null {
  if (!percentStr) return null;

  const match = percentStr.match(/([+-]?\d+\.?\d*)%/);
  return match ? match[1] : null;
}

/**
 * Extracts retail price (MSRP)
 * @param doc - Parsed document
 * @returns Retail price in cents or null
 */
export function extractRetailPrice(doc: Document): number | null {
  const retailPriceStr = extractRowValue(doc, "Retail price");
  return extractNumericPrice(retailPriceStr);
}

/**
 * Extracts current market value (New/Sealed)
 * @param doc - Parsed document
 * @returns Market value in cents or null
 */
export function extractMarketValue(doc: Document): number | null {
  // Look for "Value" under "New/Sealed" section
  const valueStr = extractRowValue(doc, "Value");
  return extractNumericPrice(valueStr);
}

/**
 * Extracts used value
 * @param doc - Parsed document
 * @returns Used value in cents or null
 */
export function extractUsedValue(doc: Document): number | null {
  // Find all "Value" rows and check which one is for used (without <b> tag)
  const rows = doc.querySelectorAll(".row.rowlist");
  const valueRows: Array<{ row: Element; value: string }> = [];

  for (const row of rows) {
    const label = row.querySelector(".col-xs-5.text-muted");
    if (label && label.textContent?.trim().toLowerCase() === "value") {
      const valueCol = row.querySelector(".col-xs-7");
      if (valueCol) {
        const valueText = valueCol.textContent?.trim() || "";

        // Check if this is NOT the market value (market value has <b> tag)
        const hasBoldTag = valueCol.querySelector("b") !== null;

        if (!hasBoldTag && valueText.startsWith("$")) {
          valueRows.push({ row, value: valueText });
        }
      }
    }
  }

  // The used value should be the second value without bold (first is market value with bold)
  if (valueRows.length > 0) {
    return extractNumericPrice(valueRows[0].value);
  }

  return null;
}

/**
 * Extracts growth percentage
 * @param doc - Parsed document
 * @returns Growth percentage string or null
 */
export function extractGrowth(doc: Document): string | null {
  const growthStr = extractRowValue(doc, "Growth");
  return extractPercentage(growthStr);
}

/**
 * Extracts annual growth percentage
 * @param doc - Parsed document
 * @returns Annual growth percentage string or null
 */
export function extractAnnualGrowth(doc: Document): string | null {
  const annualGrowthStr = extractRowValue(doc, "Annual growth");
  return extractPercentage(annualGrowthStr);
}

/**
 * Extracts 90-day change percentage
 * @param doc - Parsed document
 * @returns 90-day change percentage string or null
 */
export function extract90DayChange(doc: Document): string | null {
  const change90Str = extractRowValue(doc, "90-day change");
  return extractPercentage(change90Str);
}

/**
 * Extracts pieces count
 * @param doc - Parsed document
 * @returns Number of pieces or null
 */
export function extractPieces(doc: Document): number | null {
  const piecesStr = extractRowValue(doc, "Pieces");
  if (!piecesStr) return null;

  // Extract just the number (before any parentheses)
  const match = piecesStr.match(/^(\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

/**
 * Extracts minifigs count and value
 * @param doc - Parsed document
 * @returns Object with count and value
 */
export function extractMinifigs(doc: Document): { count: number | null; value: number | null } {
  const minifigsStr = extractRowValue(doc, "Minifigs");
  if (!minifigsStr) return { count: null, value: null };

  // Extract count (first number)
  const countMatch = minifigsStr.match(/^(\d+)/);
  const count = countMatch ? parseInt(countMatch[1], 10) : null;

  // Extract value from parentheses like "(Value $12.19)"
  const valueMatch = minifigsStr.match(/Value\s+\$?([\d.]+)/);
  const value = valueMatch ? extractNumericPrice(`$${valueMatch[1]}`) : null;

  return { count, value };
}

/**
 * Extracts price per piece (PPP)
 * @param doc - Parsed document
 * @returns PPP in cents or null
 */
export function extractPPP(doc: Document): number | null {
  const piecesStr = extractRowValue(doc, "Pieces");
  if (!piecesStr) return null;

  // Extract from parentheses like "(PPP $0.11)"
  const match = piecesStr.match(/PPP\s+\$?([\d.]+)/);
  return match ? extractNumericPrice(`$${match[1]}`) : null;
}

/**
 * Extracts theme, subtheme, and year
 * @param doc - Parsed document
 * @returns Object with theme info
 */
export function extractThemeInfo(doc: Document): { theme: string | null; subtheme: string | null; year: string | null } {
  const theme = extractRowValue(doc, "Theme");
  const subtheme = extractRowValue(doc, "Subtheme");
  const year = extractRowValue(doc, "Year");

  return { theme, subtheme, year };
}

/**
 * Extracts release and retirement dates
 * @param doc - Parsed document
 * @returns Object with dates
 */
export function extractDates(doc: Document): { released: string | null; retired: string | null } {
  const released = extractRowValue(doc, "Released");
  const retired = extractRowValue(doc, "Retired");

  return { released, retired };
}

/**
 * Extracts availability status
 * @param doc - Parsed document
 * @returns Availability status string or null
 */
export function extractAvailability(doc: Document): string | null {
  return extractRowValue(doc, "Availability");
}

/**
 * Extracts Quick Buy prices
 * @param doc - Parsed document
 * @returns Object with marketplace prices
 */
export function extractQuickBuyPrices(doc: Document): {
  ebay_lowest: number | null;
  ebay_highest: number | null;
  amazon_average: number | null;
  stockx_price: number | null;
  bricklink_lowest: number | null;
  bricklink_highest: number | null;
} {
  const result = {
    ebay_lowest: null as number | null,
    ebay_highest: null as number | null,
    amazon_average: null as number | null,
    stockx_price: null as number | null,
    bricklink_lowest: null as number | null,
    bricklink_highest: null as number | null,
  };

  // Find Quick Buy section
  const quickBuyPanel = doc.querySelector("#ContentPlaceHolder1_PanelSetBuying");
  if (!quickBuyPanel) return result;

  const rows = quickBuyPanel.querySelectorAll(".row.rowlist");
  let currentMarketplace = "";

  for (const row of rows) {
    // Check for marketplace header (semibold div)
    const prevSibling = row.previousElementSibling;
    if (prevSibling?.classList.contains("semibold")) {
      const headerText = prevSibling.textContent?.toLowerCase() || "";
      if (headerText.includes("ebay")) currentMarketplace = "ebay";
      else if (headerText.includes("amazon")) currentMarketplace = "amazon";
      else if (headerText.includes("stockx")) currentMarketplace = "stockx";
      else if (headerText.includes("bricklink")) currentMarketplace = "bricklink";
    }

    const label = row.querySelector(".text-muted");
    const valueCol = row.querySelector(".col-xs-7");

    if (!label || !valueCol) continue;

    const labelText = label.textContent?.trim().toLowerCase() || "";
    const priceStr = valueCol.textContent?.trim() || "";
    const price = extractNumericPrice(priceStr);

    if (currentMarketplace === "ebay") {
      if (labelText.includes("lowest")) result.ebay_lowest = price;
      if (labelText.includes("highest")) result.ebay_highest = price;
    } else if (currentMarketplace === "amazon") {
      if (labelText.includes("average")) result.amazon_average = price;
    } else if (currentMarketplace === "stockx") {
      if (labelText.includes("buy") || labelText.includes("bid")) result.stockx_price = price;
    } else if (currentMarketplace === "bricklink") {
      if (labelText.includes("lowest")) result.bricklink_lowest = price;
      if (labelText.includes("highest")) result.bricklink_highest = price;
    }
  }

  return result;
}

/**
 * Extracts 1-year and 5-year forecasts
 * @param doc - Parsed document
 * @returns Object with forecast prices in cents
 */
export function extractForecasts(doc: Document): { oneYear: number | null; fiveYear: number | null } {
  // Find Set Predictions panel
  const predictionsPanel = doc.querySelector("#ContentPlaceHolder1_PanelSetPredictions");
  if (!predictionsPanel) return { oneYear: null, fiveYear: null };

  const rows = predictionsPanel.querySelectorAll(".row.rowlist");

  let oneYear: number | null = null;
  let fiveYear: number | null = null;

  for (const row of rows) {
    const label = row.querySelector(".text-muted");
    const valueCol = row.querySelector(".col-xs-7");

    if (!label || !valueCol) continue;

    const labelText = label.textContent?.trim().toLowerCase() || "";
    const valueText = valueCol.textContent?.trim() || "";

    // Extract price (first part before any percentage)
    const priceMatch = valueText.match(/^\$?([\d.]+)/);
    if (!priceMatch) continue;

    const price = extractNumericPrice(`$${priceMatch[1]}`);

    if (labelText.includes("1 year")) oneYear = price;
    if (labelText.includes("5 year")) fiveYear = price;
  }

  return { oneYear, fiveYear };
}

/**
 * Extracts primary product image
 * @param doc - Parsed document
 * @returns Image URL or null
 */
export function extractImage(doc: Document): string | null {
  // Look for main product image
  const imgElement = doc.querySelector("img.set-image-main") ||
                     doc.querySelector("img[alt*='LEGO']");

  if (!imgElement) return null;

  const src = imgElement.getAttribute("src");

  // Convert relative URLs to absolute
  if (src && src.startsWith("/")) {
    return `https://www.brickeconomy.com${src}`;
  }

  return src || null;
}

/**
 * Extracts barcodes (UPC and EAN)
 * @param doc - Parsed document
 * @returns Object with barcodes
 */
export function extractBarcodes(doc: Document): { upc: string | null; ean: string | null } {
  const upc = extractRowValue(doc, "UPC");
  const ean = extractRowValue(doc, "EAN");

  return { upc, ean };
}

/**
 * Parses BrickEconomy HTML to extract product information
 * @param htmlContent - Raw HTML string
 * @returns Parsed product object or null
 */
export function parseBrickEconomyHtml(
  htmlContent: string,
): ParsedBrickEconomyProduct | null {
  try {
    const doc = parseHtmlDocument(htmlContent);

    const { setNumber, name } = extractSetInfo(doc);
    if (!setNumber || !name) {
      console.warn("Could not extract set number or name from BrickEconomy page");
      return null;
    }

    // Generate product ID
    const productId = `brickeconomy_${setNumber}`;

    // Extract pricing
    const retailPrice = extractRetailPrice(doc);
    const marketValue = extractMarketValue(doc);
    const usedValue = extractUsedValue(doc);

    // Extract investment metrics
    const growth = extractGrowth(doc);
    const annualGrowth = extractAnnualGrowth(doc);
    const growth90day = extract90DayChange(doc);

    // Extract metadata
    const pieces = extractPieces(doc);
    const { count: minifigs, value: minifigsValue } = extractMinifigs(doc);
    const ppp = extractPPP(doc);
    const { theme, subtheme, year } = extractThemeInfo(doc);
    const { released, retired } = extractDates(doc);
    const availability = extractAvailability(doc);

    // Extract Quick Buy prices
    const quickBuyPrices = extractQuickBuyPrices(doc);

    // Extract forecasts
    const { oneYear, fiveYear } = extractForecasts(doc);

    // Extract additional data
    const image = extractImage(doc);
    const { upc, ean } = extractBarcodes(doc);

    // Build raw data object
    const rawData = {
      theme,
      subtheme,
      year,
      retailPrice,
      marketValue,
      usedValue,
      growth,
      annualGrowth,
      growth90day,
      pieces,
      minifigs,
      minifigsValue,
      ppp,
      released,
      retired,
      availability,
      quickBuy: {
        ebay: { lowest: quickBuyPrices.ebay_lowest, highest: quickBuyPrices.ebay_highest },
        amazon: quickBuyPrices.amazon_average,
        stockx: quickBuyPrices.stockx_price,
        bricklink: { lowest: quickBuyPrices.bricklink_lowest, highest: quickBuyPrices.bricklink_highest },
      },
      forecasts: { oneYear, fiveYear },
      barcodes: { upc, ean },
    };

    return {
      product_id: productId,
      product_name: name,
      lego_set_number: setNumber,
      brand: "LEGO",
      retail_price: retailPrice,
      market_value: marketValue,
      used_value: usedValue,
      growth_percent: growth,
      annual_growth_percent: annualGrowth,
      growth_90day_percent: growth90day,
      forecast_1year: oneYear,
      forecast_5year: fiveYear,
      pieces,
      minifigs,
      minifigs_value: minifigsValue,
      ppp,
      theme,
      subtheme,
      year,
      released,
      retired,
      availability,
      ebay_lowest: quickBuyPrices.ebay_lowest,
      ebay_highest: quickBuyPrices.ebay_highest,
      amazon_average: quickBuyPrices.amazon_average,
      stockx_price: quickBuyPrices.stockx_price,
      bricklink_lowest: quickBuyPrices.bricklink_lowest,
      bricklink_highest: quickBuyPrices.bricklink_highest,
      image,
      upc,
      ean,
      raw_data: rawData,
    };
  } catch (error) {
    console.error("Error parsing BrickEconomy HTML:", error);
    return null;
  }
}
