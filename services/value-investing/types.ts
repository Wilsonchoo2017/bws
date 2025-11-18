/**
 * Type definitions for enriched data structures used in value investing calculations
 *
 * These interfaces represent data that has been processed and enriched by repositories
 * and services, containing computed fields beyond what's in the raw parser types.
 */

/**
 * Enriched BricklinkData with computed fields from repositories
 *
 * This represents processed data from BricklinkRepository, including:
 * - Aggregated pricing statistics
 * - Sales velocity metrics
 * - Market availability data
 * - Historical price trends
 *
 * All price fields are in CENTS for consistency with database storage.
 */
export interface EnrichedBricklinkData {
  // Pricing fields (in cents)
  avgPrice?: number; // Average price from sales data
  minPrice?: number; // Minimum price observed
  maxPrice?: number; // Maximum price observed

  // Sales volume fields
  totalQty?: number; // Total quantity sold
  timesSold?: number; // Number of sales transactions
  totalLots?: number; // Number of seller lots available

  // Market metrics
  salesVelocity?: number; // Sales per day (units/day)
  availableQty?: number; // Current available quantity for sale

  // Volatility/trend fields
  priceVolatility?: number; // Price coefficient of variation (0-1+)
  priceHistory?: number[]; // Array of historical prices in cents
}

/**
 * Enriched WorldBricksData with metadata from WorldBricks source
 *
 * This represents processed data from WorldBricksRepository, including:
 * - Product metadata (MSRP, theme, piece count)
 * - Retirement status tracking
 * - Release/retirement dates
 *
 * MSRP is in CENTS for consistency with database storage.
 */
export interface EnrichedWorldBricksData {
  // Product metadata
  msrp?: number; // Manufacturer's suggested retail price (cents)
  status?: string; // Retirement status: "active" | "retired" | "retiring soon"
  theme?: string; // LEGO theme name (e.g., "Star Wars", "Architecture")
  pieces?: number; // Parts count

  // Retirement tracking
  yearRetired?: number; // Year the set was retired (if retired)
  yearReleased?: number; // Year the set was released

  // Additional fields for compatibility
  retiringSoon?: boolean; // Flag for pre-retirement catalyst detection
}
