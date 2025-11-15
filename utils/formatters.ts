/**
 * Shared formatting utilities for consistent data presentation across the app.
 * Follows DRY principle by centralizing all formatting logic.
 *
 * ⚠️ UNIT CONVENTION: All prices are in CENTS throughout the application
 * - Database stores prices in cents
 * - All price parameters expect cents
 * - Only convert to dollars for display
 */

import type { Cents } from "../types/price.ts";

/**
 * Formats price from cents to Ringgit Malaysia (RM) currency format
 * @param priceInCents - Price value in cents (e.g., 12990 = RM 129.90)
 * @returns Formatted price string with RM prefix
 * @example
 * formatPrice(12990 as Cents) // "RM 129.90"
 * formatPrice(null) // "N/A"
 *
 * ⚠️ UNIT CONVENTION: Accepts CENTS, displays as currency
 * Note: Also accepts raw number for backward compatibility (will be treated as cents)
 */
export function formatPrice(
  priceInCents: Cents | number | null | undefined,
): string {
  if (priceInCents === null || priceInCents === undefined) return "N/A";
  return `RM ${(priceInCents / 100).toFixed(2)}`;
}

/**
 * Formats large numbers with K suffix for thousands
 * @param num - Number to format
 * @returns Formatted number string (e.g., "1.5k" for 1500)
 * @example
 * formatNumber(1500) // "1.5k"
 * formatNumber(500) // "500"
 * formatNumber(null) // "0"
 */
export function formatNumber(num: number | null | undefined): string {
  if (num === null || num === undefined) return "0";
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}k`;
  }
  return num.toString();
}

/**
 * Formats date to Malaysian locale format
 * @param date - Date object or null
 * @returns Formatted date string (e.g., "Jan 12, 2025")
 * @example
 * formatDate(new Date('2025-01-12')) // "Jan 12, 2025"
 * formatDate(null) // "N/A"
 */
export function formatDate(date: Date | null | undefined): string {
  if (!date) return "N/A";
  const d = new Date(date);
  return d.toLocaleDateString("en-MY", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Formats sold units count (alias for formatNumber for semantic clarity)
 * @param sold - Number of units sold
 * @returns Formatted sold units string
 */
export function formatSold(sold: number | null | undefined): string {
  return formatNumber(sold);
}

/**
 * Delta formatting result
 */
export interface DeltaFormat {
  text: string;
  isPositive: boolean;
}

/**
 * Formats delta (change) values for price or sold units
 * @param delta - The change amount (in CENTS for price type)
 * @param type - Type of delta ("sold" or "price")
 * @returns Formatted delta object with text and sign, or null if no change
 * @example
 * formatDelta(100, "sold") // { text: "+100", isPositive: true }
 * formatDelta(-5000 as Cents, "price") // { text: "-RM 50.00", isPositive: false }
 * formatDelta(0, "sold") // null
 *
 * ⚠️ UNIT CONVENTION: For price type, delta must be in CENTS
 */
export function formatDelta(
  delta: number | Cents | null,
  type: "sold" | "price",
): DeltaFormat | null {
  if (delta === null || delta === 0) return null;

  const isPositive = delta > 0;
  const prefix = isPositive ? "+" : "";

  if (type === "sold") {
    const formatted = Math.abs(delta) >= 1000
      ? `${(delta / 1000).toFixed(1)}k`
      : delta.toString();
    return { text: `${prefix}${formatted}`, isPositive };
  } else {
    // Price type - delta is in CENTS
    const formatted = (delta / 100).toFixed(2);
    return { text: `${prefix}RM ${formatted}`, isPositive };
  }
}

/**
 * Formats currency with custom currency code
 * @param amountInCents - Amount to format in CENTS
 * @param currency - Currency code (e.g., "SGD", "RM", "USD")
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted currency string
 * @example
 * formatCurrency(12999 as Cents, "SGD") // "SGD 129.99"
 * formatCurrency(5000 as Cents, "RM", 0) // "RM 50"
 *
 * ⚠️ UNIT CONVENTION: Accepts CENTS, displays as currency
 * Note: Also accepts raw number for backward compatibility (will be treated as cents)
 * @deprecated Consider using formatPrice() for consistent RM formatting
 */
export function formatCurrency(
  amountInCents: Cents | number | null | undefined,
  currency: string = "SGD",
  decimals: number = 2,
): string {
  if (
    amountInCents === null || amountInCents === undefined ||
    isNaN(amountInCents)
  ) return "N/A";
  const dollars = amountInCents / 100;
  return `${currency} ${dollars.toFixed(decimals)}`;
}

/**
 * Formats percentage with optional sign
 * @param value - Percentage value to format
 * @param decimals - Number of decimal places (default: 1)
 * @param showSign - Whether to show + sign for positive values (default: true)
 * @returns Formatted percentage string
 * @example
 * formatPercentage(25.5) // "+25.5%"
 * formatPercentage(-10.2) // "-10.2%"
 * formatPercentage(15, 0, false) // "15%"
 */
export function formatPercentage(
  value: number | null | undefined,
  decimals: number = 1,
  showSign: boolean = true,
): string {
  if (value === null || value === undefined || isNaN(value)) return "0%";

  const sign = showSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}
