/**
 * Shared formatting utilities for consistent data presentation across the app.
 * Follows DRY principle by centralizing all formatting logic.
 */

/**
 * Formats price from cents to Ringgit Malaysia (RM) currency format
 * @param priceInCents - Price value in cents (e.g., 12990 = RM 129.90)
 * @returns Formatted price string with RM prefix
 * @example
 * formatPrice(12990) // "RM 129.90"
 * formatPrice(null) // "N/A"
 */
export function formatPrice(
  priceInCents: number | null | undefined,
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
 * @param delta - The change amount
 * @param type - Type of delta ("sold" or "price")
 * @returns Formatted delta object with text and sign, or null if no change
 * @example
 * formatDelta(100, "sold") // { text: "+100", isPositive: true }
 * formatDelta(-5000, "price") // { text: "-RM 50.00", isPositive: false }
 * formatDelta(0, "sold") // null
 */
export function formatDelta(
  delta: number | null,
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
    // Price type
    const formatted = (delta / 100).toFixed(2);
    return { text: `${prefix}RM ${formatted}`, isPositive };
  }
}
