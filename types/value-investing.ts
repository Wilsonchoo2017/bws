export interface ValueMetrics {
  currentPrice: number;
  targetPrice: number;
  intrinsicValue: number;
  marginOfSafety: number; // Percentage
  expectedROI: number; // Percentage
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
  bricklinkAvgPrice?: number;
  bricklinkMaxPrice?: number;
  historicalPriceData?: number[];
  retirementStatus?: "active" | "retiring_soon" | "retired";
  demandScore?: number;
  qualityScore?: number;
}
