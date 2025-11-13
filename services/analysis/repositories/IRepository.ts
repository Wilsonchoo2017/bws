/**
 * Repository interfaces following SOLID principles
 * Provides abstraction layer for data access (Dependency Inversion Principle)
 */

import type {
  BricklinkItem,
  BrickrankerRetirementItem,
  Product,
  RedditSearchResult,
} from "../../../db/schema.ts";

/**
 * Product repository interface
 * Single Responsibility: Product data access only
 */
export interface IProductRepository {
  findByProductId(productId: string): Promise<Product | null>;
  findByLegoSetNumber(setNumber: string): Promise<Product[]>;
  findByProductIds(productIds: string[]): Promise<Product[]>;
}

/**
 * Bricklink repository interface
 * Single Responsibility: Bricklink data access only
 */
export interface IBricklinkRepository {
  findByLegoSetNumber(setNumber: string): Promise<BricklinkItem | null>;
  findByItemId(itemId: string): Promise<BricklinkItem | null>;
  findByLegoSetNumbers(
    setNumbers: string[],
  ): Promise<Map<string, BricklinkItem>>;
  getPastSalesStatistics(itemId: string): Promise<PastSalesStatistics | null>;
  getPastSalesStatisticsBatch(
    itemIds: string[],
  ): Promise<Map<string, PastSalesStatistics>>;
}

/**
 * Past sales statistics interface
 * Market-driven metrics inspired by stock market analysis
 */
export interface PastSalesStatistics {
  totalTransactions: number;
  dateRangeStart: Date | null;
  dateRangeEnd: Date | null;
  totalDays: number;

  // Condition-specific metrics
  new: ConditionMetrics;
  used: ConditionMetrics;

  // Market indicators
  rsi: {
    new: number | null;
    used: number | null;
  };
}

export interface ConditionMetrics {
  transactionCount: number;
  totalQuantity: number;
  salesVelocity: number;
  avgDaysBetweenSales: number;
  avgPrice: number;
  medianPrice: number;
  minPrice: number;
  maxPrice: number;
  priceStdDev: number;
  volatilityIndex: number;
  trends: {
    last30Days: TrendMetrics;
    last90Days: TrendMetrics;
    last180Days: TrendMetrics;
    allTime: TrendMetrics;
  };
  recent30d: number;
  recent60d: number;
  recent90d: number;
}

export interface TrendMetrics {
  direction: "increasing" | "stable" | "decreasing" | "neutral";
  momentum: number;
  percentChange: number;
  volumeTrend: "increasing" | "stable" | "decreasing" | "neutral";
  avgPrice: number;
}

/**
 * Reddit repository interface
 * Single Responsibility: Reddit data access only
 */
export interface IRedditRepository {
  findByLegoSetNumber(setNumber: string): Promise<RedditSearchResult | null>;
  findByLegoSetNumbers(
    setNumbers: string[],
  ): Promise<Map<string, RedditSearchResult>>;
}

/**
 * Retirement repository interface
 * Single Responsibility: Retirement data access only
 */
export interface IRetirementRepository {
  findByLegoSetNumber(
    setNumber: string,
  ): Promise<BrickrankerRetirementItem | null>;
  findByLegoSetNumbers(
    setNumbers: string[],
  ): Promise<Map<string, BrickrankerRetirementItem>>;
}
