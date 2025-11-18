import type { BricklinkItem } from "../../../../db/schema.ts";

/**
 * Past sales statistics for market analysis
 * Inspired by stock market analysis metrics
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
 * BrickLink repository interface (DIP - Dependency Inversion Principle)
 * Single Responsibility: BrickLink data access abstraction
 *
 * Benefits:
 * - Allows mocking in tests
 * - Decouples business logic from database implementation
 * - Enables API fallback or caching strategies
 */
export interface IBricklinkRepository {
  /**
   * Find BrickLink item by LEGO set number
   * Handles both "12345" and "12345-1" formats automatically
   */
  findByLegoSetNumber(setNumber: string): Promise<BricklinkItem | null>;

  /**
   * Find BrickLink item by exact item ID
   */
  findByItemId(itemId: string): Promise<BricklinkItem | null>;

  /**
   * Batch operation: Find multiple BrickLink items
   * Returns Map for O(1) lookup by set number
   * Solves N+1 query problem
   */
  findByLegoSetNumbers(
    setNumbers: string[],
  ): Promise<Map<string, BricklinkItem>>;

  /**
   * Get comprehensive past sales statistics for an item
   * Used for liquidity, volatility, and trend analysis
   */
  getPastSalesStatistics(itemId: string): Promise<PastSalesStatistics | null>;

  /**
   * Batch operation: Get past sales statistics for multiple items
   * Returns Map for O(1) lookup
   */
  getPastSalesStatisticsBatch(
    itemIds: string[],
  ): Promise<Map<string, PastSalesStatistics>>;
}
