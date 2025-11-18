import type { Cents } from "../../../types/price.ts";

/**
 * Core pricing information for value calculation
 * UNIT CONVENTION: All prices are in CENTS (branded type)
 */
export interface PricingInputs {
  /**
   * Original manufacturer's suggested retail price (CENTS)
   * This is the PRIMARY base value for intrinsic value calculation
   */
  msrp?: Cents;

  /**
   * Current retail price if still available for sale (CENTS)
   * Used as fallback if MSRP unavailable
   */
  currentRetailPrice?: Cents;

  /**
   * Original retail price before any discounts (CENTS)
   * Used for deal quality analysis
   */
  originalRetailPrice?: Cents;

  /**
   * BrickLink average price for new condition (CENTS)
   * Used as fallback base value or for comparison
   */
  bricklinkAvgPrice?: Cents;

  /**
   * BrickLink maximum price for new condition (CENTS)
   * Used for price-to-market ratio analysis
   */
  bricklinkMaxPrice?: Cents;

  /**
   * Historical price data points (CENTS)
   * Used for volatility and trend analysis
   */
  historicalPriceData?: Cents[];
}

/**
 * Market liquidity and activity metrics
 */
export interface MarketInputs {
  /**
   * Transactions per day
   * Measures market liquidity for liquidity multiplier
   */
  salesVelocity?: number;

  /**
   * Average days between sales
   * Another liquidity indicator (inverse of velocity)
   */
  avgDaysBetweenSales?: number;

  /**
   * Total number of sales in observation period
   * Used for zero sales penalty detection
   */
  timesSold?: number;

  /**
   * Total units available for sale across all sellers
   * Used for saturation discount calculation
   */
  availableQty?: number;

  /**
   * Number of competing sellers
   * Used for saturation discount calculation
   */
  availableLots?: number;

  /**
   * Price volatility (coefficient of variation 0-1+)
   * Measures price stability for volatility discount
   */
  priceVolatility?: number;

  /**
   * Price decline rate (0-1, where 0.15 = 15% decline)
   * Negative trend indicator
   */
  priceDecline?: number;

  /**
   * Price trend (positive = rising, negative = falling)
   * Momentum indicator
   */
  priceTrend?: number;
}

/**
 * Product retirement status and timeline
 */
export interface RetirementInputs {
  /**
   * Current retirement status of the product
   */
  retirementStatus?: "active" | "retiring_soon" | "retired";

  /**
   * Years since official retirement
   * Used for time-decayed retirement premium (J-curve)
   */
  yearsPostRetirement?: number;

  /**
   * Year the product was originally released
   * Used to calculate years since release
   */
  yearReleased?: number;
}

/**
 * Product quality and desirability metrics
 */
export interface QualityInputs {
  /**
   * Demand score (0-100)
   * Measures market demand/desirability
   */
  demandScore?: number;

  /**
   * Quality score (0-100)
   * Measures build quality, design, collectability
   */
  qualityScore?: number;

  /**
   * Availability score (0-100)
   * Note: Inverse relationship with scarcity
   * Low availability = high scarcity = value boost
   */
  availabilityScore?: number;

  /**
   * LEGO theme (Star Wars, Architecture, etc.)
   * Certain themes command premiums
   */
  theme?: string;

  /**
   * Number of pieces in the set
   * Used for parts-per-dollar calculation
   */
  partsCount?: number;
}

/**
 * Unified intrinsic value inputs
 * Aggregates all input categories for cleaner API
 */
export interface IntrinsicValueInputs {
  pricing: PricingInputs;
  market: MarketInputs;
  retirement: RetirementInputs;
  quality: QualityInputs;
}
