/**
 * Core types and interfaces for the product analysis system
 * Following SOLID principles for extensibility and maintainability
 */

// ============================================================================
// Analysis Result Types
// ============================================================================

export interface AnalysisScore {
  value: number; // 0-100
  confidence: number; // 0-1 (how confident we are in this score)
  reasoning: string; // Human-readable explanation
  dataPoints: Record<string, unknown>; // Raw data used for calculation
}

export interface DimensionalScores {
  pricing: AnalysisScore;
  demand: AnalysisScore;
  availability: AnalysisScore;
  quality: AnalysisScore;
}

export interface ProductRecommendation {
  overall: AnalysisScore;
  dimensions: DimensionalScores;
  action: "strong_buy" | "buy" | "hold" | "pass";
  strategy: string;
  urgency: "urgent" | "moderate" | "low" | "no_rush";
  estimatedROI?: number; // Percentage
  timeHorizon?: string; // e.g., "6-12 months"
  risks: string[];
  opportunities: string[];
  analyzedAt: Date;
}

// ============================================================================
// Input Data Types (normalized from various sources)
// ============================================================================

export interface PricingData {
  // Retail pricing (Shopee/ToysRUs)
  currentRetailPrice?: number;
  originalRetailPrice?: number;
  discountPercentage?: number;

  // Resale pricing (Bricklink)
  bricklink?: {
    current: {
      newAvg?: number;
      newMin?: number;
      newMax?: number;
      usedAvg?: number;
      usedMin?: number;
      usedMax?: number;
    };
    sixMonth: {
      newAvg?: number;
      newMin?: number;
      newMax?: number;
      usedAvg?: number;
      usedMin?: number;
      usedMax?: number;
    };
  };

  // Historical trends
  priceHistory?: Array<{
    price: number;
    recordedAt: Date;
  }>;
}

export interface DemandData {
  // Sales metrics
  unitsSold?: number;
  lifetimeSold?: number;
  bricklinkTimesSold?: number;
  bricklinkTotalQty?: number;

  // Engagement metrics
  viewCount?: number;
  likedCount?: number;
  commentCount?: number;

  // Community sentiment (Reddit)
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
  daysUntilRetirement?: number;

  // Platform availability
  isActive: boolean;
  source: string; // shopee, toysrus, etc.
}

export interface QualityData {
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
 */
export interface IAnalyzer<T> {
  analyze(data: T): Promise<AnalysisScore>;
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
  pricing: number; // 0-1
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

export type AnalyzerType = "pricing" | "demand" | "availability" | "quality";

export interface AnalyzerRegistry {
  [key: string]: IAnalyzer<unknown>;
}

export interface StrategyRegistry {
  [key: string]: IStrategy;
}
