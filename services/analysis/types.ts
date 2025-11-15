/**
 * Core types and interfaces for the product analysis system
 * Following SOLID principles for extensibility and maintainability
 */

import type { Cents } from "../../types/price.ts";

// ============================================================================
// Analysis Result Types
// ============================================================================

export interface ScoreComponent {
  name: string; // Component name (e.g., "Bricklink Market Pricing")
  weight: number; // Weight percentage (0-1)
  score: number; // Component score (0-100)
  rawValue?: number | string; // Raw input value
  calculation: string; // How this score was calculated
  reasoning: string; // Why this score matters
}

export interface ScoreBreakdown {
  components: ScoreComponent[]; // Individual calculation components
  formula: string; // Overall formula used
  totalScore: number; // Final calculated score
  dataPoints: Record<string, unknown>; // All raw data used
  missingData?: string[]; // What data was missing (if any)
}

export interface AnalysisScore {
  value: number; // 0-100
  confidence: number; // 0-1 (how confident we are in this score)
  reasoning: string; // Human-readable explanation
  dataPoints: Record<string, unknown>; // Raw data used for calculation
  breakdown?: ScoreBreakdown; // Detailed calculation breakdown
}

export interface DimensionalScores {
  demand: AnalysisScore | null;
  availability: AnalysisScore | null;
  quality: AnalysisScore | null;
}

export interface ProductRecommendation {
  overall: AnalysisScore;
  dimensions: DimensionalScores;
  availableDimensions: number; // How many dimensions had sufficient data (0-3)
  action: "strong_buy" | "buy" | "hold" | "pass" | "insufficient_data";
  strategy: string;
  urgency: "urgent" | "moderate" | "low" | "no_rush";
  estimatedROI?: number; // Percentage
  timeHorizon?: string; // e.g., "6-12 months"
  /**
   * Recommended buy price calculation
   * @property {Cents} price - Target buy price in cents (e.g., 31503 = RM 315.03)
   */
  recommendedBuyPrice?: {
    price: Cents;
    reasoning: string;
    confidence: number;
    breakdown?: {
      intrinsicValue: Cents;
      baseMargin: number;
      adjustedMargin: number;
      marginAdjustments: Array<{ reason: string; value: number }>;
      inputs: {
        msrp?: number;
        bricklinkAvgPrice?: number;
        bricklinkMaxPrice?: number;
        retirementStatus?: string;
        demandScore?: number;
        qualityScore?: number;
        availabilityScore?: number;
      };
    };
  };
  risks: string[];
  opportunities: string[];
  analyzedAt: Date;
}

// ============================================================================
// Input Data Types (normalized from various sources)
// ============================================================================

/**
 * Pricing data from various sources
 * ⚠️ All price fields are in CENTS for precision
 */
export interface PricingData {
  // Retail pricing (Shopee/ToysRUs) - CENTS
  currentRetailPrice?: Cents;
  originalRetailPrice?: Cents;
  discountPercentage?: number; // Percentage (0-100)

  // Resale pricing (Bricklink) - CENTS
  bricklink?: {
    current: {
      newAvg?: Cents;
      newMin?: Cents;
      newMax?: Cents;
      usedAvg?: Cents;
      usedMin?: Cents;
      usedMax?: Cents;
    };
    sixMonth: {
      newAvg?: Cents;
      newMin?: Cents;
      newMax?: Cents;
      usedAvg?: Cents;
      usedMin?: Cents;
      usedMax?: Cents;
    };
  };

  // Historical trends
  priceHistory?: Array<{
    price: number;
    recordedAt: Date;
  }>;
}

export interface DemandData {
  // Calculated demand score (0-100) from DemandCalculator
  demandScore?: number;
  demandScoreConfidence?: number; // 0-1
  demandScoreBreakdown?: {
    components: {
      salesVelocity: {
        score: number;
        weight: number;
        weightedScore: number;
        confidence: number;
        notes?: string;
      };
      priceMomentum: {
        score: number;
        weight: number;
        weightedScore: number;
        confidence: number;
        notes?: string;
      };
      marketDepth: {
        score: number;
        weight: number;
        weightedScore: number;
        confidence: number;
        notes?: string;
      };
      supplyDemandRatio: {
        score: number;
        weight: number;
        weightedScore: number;
        confidence: number;
        notes?: string;
      };
      velocityConsistency: {
        score: number;
        weight: number;
        weightedScore: number;
        confidence: number;
        notes?: string;
      };
    };
    dataQuality: {
      hasSalesData: boolean;
      hasPriceData: boolean;
      hasMarketDepth: boolean;
      observationPeriod: number;
    };
  };

  // Retail sales metrics (Shopee) - minimal weight for investment analysis
  unitsSold?: number;
  lifetimeSold?: number;

  // PRIMARY: Bricklink pricing data (market indicators)
  bricklinkCurrentNewAvg?: number;
  bricklinkCurrentNewMin?: number;
  bricklinkCurrentNewMax?: number;
  bricklinkCurrentNewQty?: number;
  bricklinkCurrentNewLots?: number;
  bricklinkSixMonthNewAvg?: number;
  bricklinkSixMonthNewMin?: number;
  bricklinkSixMonthNewMax?: number;
  bricklinkSixMonthNewTimesSold?: number;
  bricklinkSixMonthNewQty?: number;

  // Legacy Bricklink aggregated metrics (from pricing boxes)
  bricklinkTimesSold?: number;
  bricklinkTotalQty?: number;

  // SECONDARY: Market-driven Bricklink metrics (from past sales data)
  // Inspired by stock market analysis principles

  // Liquidity & Velocity metrics (like trading volume)
  bricklinkPastSalesCount?: number; // Total transaction count
  bricklinkSalesVelocity?: number; // Transactions per day
  bricklinkAvgDaysBetweenSales?: number; // Liquidity indicator
  bricklinkRecentSales30d?: number;
  bricklinkRecentSales60d?: number;
  bricklinkRecentSales90d?: number;

  // Momentum & Trend metrics (like price/volume trends)
  bricklinkPriceTrend?: "increasing" | "stable" | "decreasing" | "neutral";
  bricklinkPriceMomentum?: number; // Linear regression slope
  bricklinkPriceChangePercent?: number; // % change over period
  bricklinkVolumeTrend?: "increasing" | "stable" | "decreasing" | "neutral";

  // Volatility metrics (like price stability)
  bricklinkPriceVolatility?: number; // Coefficient of variation
  bricklinkAvgPrice?: number; // Volume-weighted average price
  bricklinkMedianPrice?: number; // Median transaction price

  // Market strength indicators
  bricklinkRSI?: number; // Relative Strength Index (0-100)
  // RSI > 70 = overbought (may decrease), RSI < 30 = oversold (may increase)

  // Condition-specific weighting (new items prioritized for investment)
  bricklinkNewConditionWeight?: number; // 0-1 weight for 'new' vs 'used' data

  // TERTIARY: Engagement metrics (Shopee)
  viewCount?: number;
  likedCount?: number;
  commentCount?: number;

  // Community sentiment (Reddit) - social validation like analyst ratings
  redditPosts?: number;
  redditTotalScore?: number;
  redditTotalComments?: number;
  redditAverageScore?: number;
}

export interface AvailabilityData {
  // Stock information
  currentStock?: number;
  stockType?: string;

  // Retirement information
  retiringSoon?: boolean;
  expectedRetirementDate?: Date;
  yearReleased?: number;
  yearRetired?: number; // NEW: Official retirement year from WorldBricks
  daysUntilRetirement?: number;

  // Platform availability
  isActive: boolean;
  source: string; // shopee, toysrus, etc.
}

export interface QualityData {
  // Calculated quality score (0-100) from QualityCalculator
  qualityScore?: number;
  qualityScoreConfidence?: number; // 0-1
  qualityScoreBreakdown?: {
    components: {
      ppdScore: { score: number; weightedScore: number; notes: string };
      complexityScore: { score: number; weightedScore: number; notes: string };
      themePremium: { score: number; weightedScore: number; notes: string };
      scarcityScore: { score: number; weightedScore: number; notes: string };
    };
    dataQuality: {
      hasParts: boolean;
      hasMsrp: boolean;
      hasTheme: boolean;
      hasAvailability: boolean;
    };
  };

  // Ratings
  avgStarRating?: number;
  ratingCount?: number;
  ratingDistribution?: Record<string, number>;

  // Trust signals
  isPreferredSeller?: boolean;
  isServiceByShopee?: boolean;
  isMart?: boolean;
  shopLocation?: string;

  // Product metadata
  brand?: string;
  theme?: string;
  legoSetNumber?: string;
  partsCount?: number; // NEW: For PPD calculation
}

export interface ProductAnalysisInput {
  productId: string;
  name: string;
  pricing: PricingData;
  demand: DemandData;
  availability: AvailabilityData;
  quality: QualityData;
}

// ============================================================================
// Analyzer and Strategy Interfaces
// ============================================================================

/**
 * Base interface for all analyzers
 * Each analyzer focuses on one dimension (Single Responsibility Principle)
 * Returns null if insufficient data to analyze (smart skipping)
 */
export interface IAnalyzer<T> {
  analyze(data: T): Promise<AnalysisScore | null>;
  getName(): string;
  getDescription(): string;
}

/**
 * Strategy interface for different recommendation approaches
 * Allows for different weighting and interpretation of scores
 */
export interface IStrategy {
  getName(): string;
  getDescription(): string;
  getWeights(): DimensionWeights;
  interpret(scores: DimensionalScores): ProductRecommendation;
}

export interface DimensionWeights {
  demand: number; // 0-1
  availability: number; // 0-1
  quality: number; // 0-1
}

// ============================================================================
// Configuration Types
// ============================================================================

export interface AnalysisConfig {
  strategy: string;
  cacheTTL?: number; // Time to live in milliseconds
  minConfidence?: number; // Minimum confidence threshold (0-1)
  includeRisks?: boolean;
  includeOpportunities?: boolean;
}

// ============================================================================
// Helper Types
// ============================================================================

export type AnalyzerType = "demand" | "availability" | "quality";

export interface AnalyzerRegistry {
  [key: string]: IAnalyzer<unknown>;
}

export interface StrategyRegistry {
  [key: string]: IStrategy;
}
