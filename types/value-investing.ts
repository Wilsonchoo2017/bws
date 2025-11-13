export interface ValueMetrics {
  currentPrice: number;
  targetPrice: number;
  intrinsicValue: number;
  realizedValue?: number; // After transaction costs
  marginOfSafety: number; // Percentage
  expectedROI: number; // Percentage (theoretical)
  realizedROI?: number; // Percentage (after transaction costs)
  timeHorizon: string;
}

export interface ValueInvestingProduct {
  // Product details
  id: number;
  productId: string;
  name: string;
  image: string;
  legoSetNumber: string | null;
  source: string;
  brand: string;

  // Pricing
  currentPrice: number;
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

export interface ValueInvestingFilters {
  strategy?: string;
  minROI?: number;
  maxPrice?: number;
  minPrice?: number;
  actionTypes?: Array<"strong_buy" | "buy">;
}

export interface IntrinsicValueInputs {
  // FUNDAMENTAL VALUE INPUTS (Replacement cost - TRUE intrinsic value)
  msrp?: number; // Original manufacturer's suggested retail price
  currentRetailPrice?: number; // Current retail price if still available
  // Market prices (for comparison, NOT base value)
  bricklinkAvgPrice?: number;
  bricklinkMaxPrice?: number;
  historicalPriceData?: number[];
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
