/**
 * Application configuration constants.
 * Centralizes all magic numbers and configuration values.
 */

/**
 * Pagination configuration
 */
export const PAGINATION = {
  /** Default number of items per page */
  DEFAULT_LIMIT: 50,
  /** Maximum allowed items per page */
  MAX_LIMIT: 100,
  /** Minimum allowed items per page */
  MIN_LIMIT: 10,
} as const;

/**
 * Sold units threshold configuration for color-coding
 * Higher thresholds appear first for proper matching
 */
export const SOLD_THRESHOLDS = [
  {
    name: "VIRAL",
    min: 10000,
    color: "#9333ea", // Purple
    tailwindClass: "!text-purple-600 font-bold",
    fontWeight: "700",
    label: "Viral",
  },
  {
    name: "HOT",
    min: 5000,
    color: "#dc2626", // Red
    tailwindClass: "!text-red-600 font-bold",
    fontWeight: "700",
    label: "Hot",
  },
  {
    name: "POPULAR",
    min: 1000,
    color: "#ea580c", // Orange
    tailwindClass: "!text-orange-600 font-semibold",
    fontWeight: "600",
    label: "Popular",
  },
  {
    name: "SELLING",
    min: 500,
    color: "#ca8a04", // Yellow
    tailwindClass: "!text-yellow-600 font-medium",
    fontWeight: "500",
    label: "Selling",
  },
  {
    name: "MODERATE",
    min: 100,
    color: "#16a34a", // Green
    tailwindClass: "!text-green-600",
    fontWeight: "400",
    label: "Moderate",
  },
] as const;

/**
 * Gets the color class for sold units based on thresholds
 * @param sold - Number of units sold
 * @returns Tailwind CSS class string for color styling
 */
export function getSoldColorClass(sold: number | null): string {
  if (sold === null || sold === 0) return "";

  for (const threshold of SOLD_THRESHOLDS) {
    if (sold >= threshold.min) {
      return threshold.tailwindClass;
    }
  }

  return ""; // Below all thresholds
}

/**
 * Gets the inline style for sold units (for non-Tailwind contexts)
 * @param sold - Number of units sold
 * @returns Style object with color and fontWeight
 */
export function getSoldStyle(
  sold: number | null,
): { color?: string; fontWeight?: string } {
  if (sold === null || sold === 0) return {};

  for (const threshold of SOLD_THRESHOLDS) {
    if (sold >= threshold.min) {
      return {
        color: threshold.color,
        fontWeight: threshold.fontWeight,
      };
    }
  }

  return {};
}

/**
 * Database query configuration
 */
export const QUERY_CONFIG = {
  /** Default timeout for database queries in milliseconds */
  DEFAULT_TIMEOUT: 30000,
  /** Maximum number of records to fetch in a single query */
  MAX_BATCH_SIZE: 1000,
} as const;

/**
 * Scraping configuration
 */
export const SCRAPING = {
  /** Maximum number of products to parse in a single request */
  MAX_PRODUCTS_PER_SCRAPE: 100,
  /** Delay between scrape requests in milliseconds */
  SCRAPE_DELAY_MS: 1000,
} as const;

/**
 * Price tracking configuration
 */
export const PRICE_TRACKING = {
  /** Watch status values */
  WATCH_STATUS: {
    ACTIVE: "active",
    PAUSED: "paused",
    STOPPED: "stopped",
    ARCHIVED: "archived",
  } as const,
} as const;

/**
 * Image configuration
 */
export const IMAGES = {
  /** Default thumbnail size in pixels */
  THUMBNAIL_SIZE: 64,
  /** Maximum image size for upload in bytes */
  MAX_UPLOAD_SIZE: 5 * 1024 * 1024, // 5MB
} as const;

/**
 * Date/Time configuration
 */
export const DATETIME = {
  /** Locale for date formatting */
  LOCALE: "en-MY",
  /** Timezone */
  TIMEZONE: "Asia/Kuala_Lumpur",
} as const;
