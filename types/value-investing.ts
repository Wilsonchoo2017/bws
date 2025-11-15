import type { Cents } from "./price.ts";
import type { VoucherTemplate } from "./voucher.ts";

/**
 * Value metrics for investment analysis (API/Display layer)
 *
 * UNIT CONVENTION: All prices are in CENTS for API responses and display
 * - Used by services that return data to the client
 * - All price fields are in cents for consistency with database
 */
export interface ValueMetrics {
  currentPrice: Cents; // Current market price in cents
  targetPrice: Cents; // Recommended buy price in cents
  intrinsicValue: Cents; // Calculated intrinsic value in cents
  realizedValue?: Cents; // After transaction costs in cents
  marginOfSafety: number; // Percentage (e.g., 25 = 25%)
  expectedROI: number; // Percentage (theoretical)
  realizedROI?: number; // Percentage (after transaction costs)
  timeHorizon: string;
  // Deal quality analysis
  dealQualityScore?: number; // 0-100 score (85+ = Excellent, 70+ = Very Good, 60+ = Good)
  dealQualityLabel?: string; // Human-readable label
  dealRecommendation?: string; // Brief recommendation text
  retailDiscountPercent?: number; // Discount from original retail/MSRP
  priceToMarketRatio?: number; // Current retail vs BrickLink market
  priceToValueRatio?: number; // Current retail vs intrinsic value
  // Detailed calculation breakdown (optional, for transparency)
  calculationBreakdown?: IntrinsicValueBreakdown;
}

/**
 * Extended value metrics that include voucher-adjusted calculations
 * Used for voucher simulation on the /buy page
 */
export interface VoucherEnhancedMetrics extends ValueMetrics {
  // Original metrics (base values without vouchers)
  originalPrice: Cents;
  originalExpectedROI: number;
  originalMarginOfSafety: number;

  // Voucher-adjusted metrics
  voucherDiscountedPrice: Cents;
  voucherSavings: Cents;
  voucherEnhancedROI: number;
  voucherEnhancedMarginOfSafety: number;

  // Comparison metrics
  roiImprovement: number; // Percentage point improvement
  worthItWithVoucher: boolean; // Whether deal becomes good with voucher
  optimalVoucherOrder: VoucherTemplate[]; // Best order to apply vouchers
}

/**
 * Value metrics (Internal calculation layer)
 *
 * UNIT CONVENTION: All prices are in CENTS (using branded Cents type)
 * - Used internally by ValueCalculator (works in cents)
 * - Despite the legacy name "InDollars", this now uses CENTS branded type
 * - TODO: Rename interface to ValueMetricsInternal for clarity
 */
export interface ValueMetricsInDollars {
  currentPrice: Cents; // Current market price in CENTS
  targetPrice: Cents; // Recommended buy price in CENTS
  intrinsicValue: Cents; // Calculated intrinsic value in CENTS
  realizedValue?: Cents; // After transaction costs in CENTS
  marginOfSafety: number; // Percentage (e.g., 25 = 25%)
  expectedROI: number; // Percentage (theoretical)
  realizedROI?: number; // Percentage (after transaction costs)
  timeHorizon: string;
  // Deal quality analysis
  dealQualityScore?: number; // 0-100 score
  dealQualityLabel?: string; // Human-readable label
  dealRecommendation?: string; // Brief recommendation text
  retailDiscountPercent?: number; // Discount from original retail/MSRP
  priceToMarketRatio?: number; // Current retail vs BrickLink market
  priceToValueRatio?: number; // Current retail vs intrinsic value
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
  minROI?: number; // Percentage
  maxPrice?: Cents; // Maximum price in cents
  minPrice?: Cents; // Minimum price in cents
  actionTypes?: Array<"strong_buy" | "buy">;
}

/**
 * Inputs for intrinsic value calculation
 *
 * ⚠️ UNIT CONVENTION: ValueCalculator now works in CENTS (integers)
 * All calculations done with integer cents to avoid floating point errors
 */
export interface IntrinsicValueInputs {
  // FUNDAMENTAL VALUE INPUTS (Replacement cost - TRUE intrinsic value)
  // All prices in CENTS for precision
  msrp?: Cents; // Original manufacturer's suggested retail price (CENTS)
  currentRetailPrice?: Cents; // Current retail price if still available (CENTS)
  originalRetailPrice?: Cents; // Original retail price before discount (for deal quality) (CENTS)
  // Market prices (for comparison, NOT base value) (CENTS)
  bricklinkAvgPrice?: Cents;
  bricklinkMaxPrice?: Cents;
  historicalPriceData?: Cents[]; // Historical prices (CENTS)
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
  timesSold?: number; // Total number of sales in observation period (for zero sales penalty)
  // Volatility metric for risk-adjusted valuation
  priceVolatility?: number; // Coefficient of variation (0-1+)
  // Saturation metrics for market oversupply detection
  availableQty?: number; // Total units available for sale
  availableLots?: number; // Number of competing sellers
  // Set characteristics
  theme?: string; // LEGO theme (Star Wars, Architecture, etc.)
  partsCount?: number; // Number of pieces (for PPD calculation)
}

/**
 * Detailed breakdown of intrinsic value calculation
 * Shows step-by-step how the final intrinsic value is derived
 */
export interface IntrinsicValueBreakdown {
  // Base value information
  baseValue: Cents;
  baseValueSource: "msrp" | "currentRetail" | "bricklink" | "none";
  baseValueExplanation: string;

  // Quality multipliers (increase value)
  qualityMultipliers: {
    retirement: {
      value: number;
      explanation: string;
      applied: boolean;
    };
    quality: {
      value: number;
      score: number;
      explanation: string;
    };
    demand: {
      value: number;
      score: number;
      explanation: string;
    };
    theme: {
      value: number;
      themeName: string;
      explanation: string;
    };
    partsPerDollar: {
      value: number;
      ppdValue?: number;
      explanation: string;
    };
  };

  // Risk discounts (decrease value)
  riskDiscounts: {
    liquidity: {
      value: number;
      explanation: string;
      applied: boolean;
    };
    volatility: {
      value: number;
      volatilityPercent?: number;
      explanation: string;
      applied: boolean;
    };
    saturation: {
      value: number;
      explanation: string;
      applied: boolean;
    };
    zeroSales: {
      value: number;
      explanation: string;
      applied: boolean;
    };
  };

  // Intermediate calculation results
  intermediateValues: {
    afterQualityMultipliers: Cents;
    afterRiskDiscounts: Cents;
  };

  // Final result
  finalIntrinsicValue: Cents;

  // Combined multiplier (for display)
  totalMultiplier: number;
}
