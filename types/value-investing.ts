import type { Cents, Dollars } from "./price.ts";

/**
 * Value metrics for investment analysis (API/Display layer)
 *
 * UNIT CONVENTION: All prices are in CENTS for API responses and display
 * - Used by services that return data to the client
 * - All price fields are in cents for consistency with database
 */
export interface ValueMetrics {
  currentPrice: Cents;        // Current market price in cents
  targetPrice: Cents;          // Recommended buy price in cents
  intrinsicValue: Cents;       // Calculated intrinsic value in cents
  realizedValue?: Cents;       // After transaction costs in cents
  marginOfSafety: number;      // Percentage (e.g., 25 = 25%)
  expectedROI: number;         // Percentage (theoretical)
  realizedROI?: number;        // Percentage (after transaction costs)
  timeHorizon: string;
}

/**
 * Value metrics in dollars (Internal calculation layer)
 *
 * UNIT CONVENTION: All prices are in DOLLARS for ValueCalculator
 * - Used internally by ValueCalculator
 * - Convert to ValueMetrics (cents) at service boundaries
 */
export interface ValueMetricsInDollars {
  currentPrice: number;        // Current market price in dollars
  targetPrice: number;          // Recommended buy price in dollars
  intrinsicValue: number;       // Calculated intrinsic value in dollars
  realizedValue?: number;       // After transaction costs in dollars
  marginOfSafety: number;      // Percentage (e.g., 25 = 25%)
  expectedROI: number;         // Percentage (theoretical)
  realizedROI?: number;        // Percentage (after transaction costs)
  timeHorizon: string;
}

/**
 * Value investing product with analysis results
 *
 * UNIT CONVENTION: currentPrice is in CENTS (from database)
 */
export interface ValueInvestingProduct {
  // Product details
  id: number;
  productId: string;
  name: string;
  image: string;
  legoSetNumber: string | null;
  source: string;
  brand: string;

  // Pricing (in CENTS)
  currentPrice: Cents;
  currency: string;

  // Value metrics
  valueMetrics: ValueMetrics;

  // Analysis data
  strategy: string;
  action: "strong_buy" | "buy" | "hold" | "pass" | "insufficient_data";
  urgency: "urgent" | "moderate" | "low" | "no_rush";
  overallScore: number;

  // Additional context
  risks: string[];
  opportunities: string[];

  // Market data
  unitsSold?: number;
  lifetimeSold?: number;
  currentStock?: number;
  avgStarRating?: number;
}

/**
 * Filters for value investing products
 *
 * UNIT CONVENTION: Price filters are in CENTS
 */
export interface ValueInvestingFilters {
  strategy?: string;
  minROI?: number;           // Percentage
  maxPrice?: Cents;          // Maximum price in cents
  minPrice?: Cents;          // Minimum price in cents
  actionTypes?: Array<"strong_buy" | "buy">;
}

/**
 * Inputs for intrinsic value calculation
 *
 * ⚠️ UNIT CONVENTION: ValueCalculator expects all prices in DOLLARS
 * Convert cents to dollars before passing to ValueCalculator.calculateIntrinsicValue()
 */
export interface IntrinsicValueInputs {
  // FUNDAMENTAL VALUE INPUTS (Replacement cost - TRUE intrinsic value)
  // All prices in DOLLARS for ValueCalculator
  msrp?: number;               // Original manufacturer's suggested retail price (DOLLARS)
  currentRetailPrice?: number; // Current retail price if still available (DOLLARS)
  // Market prices (for comparison, NOT base value) (DOLLARS)
  bricklinkAvgPrice?: number;
  bricklinkMaxPrice?: number;
  historicalPriceData?: number[];  // Historical prices (DOLLARS)
  // Retirement data
  retirementStatus?: "active" | "retiring_soon" | "retired";
  yearsPostRetirement?: number; // For time-decayed retirement premium
  yearReleased?: number; // For calculating years since release
  // Analysis scores
  demandScore?: number;
  qualityScore?: number;
  // Liquidity metrics for liquidity multiplier
  salesVelocity?: number; // Transactions per day
  avgDaysBetweenSales?: number; // Days between sales (liquidity indicator)
  // Volatility metric for risk-adjusted valuation
  priceVolatility?: number; // Coefficient of variation (0-1+)
  // Saturation metrics for market oversupply detection
  availableQty?: number; // Total units available for sale
  availableLots?: number; // Number of competing sellers
  // Set characteristics
  theme?: string; // LEGO theme (Star Wars, Architecture, etc.)
  partsCount?: number; // Number of pieces (for PPD calculation)
}
