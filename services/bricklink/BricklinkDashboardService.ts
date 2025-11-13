/**
 * BricklinkDashboardService - Query helper for dashboard visualizations
 *
 * Responsibilities:
 * - Query volume history data for charts
 * - Aggregate and transform data for dashboard consumption
 * - Calculate trends and growth rates
 * - Provide dashboard-friendly JSON format
 *
 * This service follows SOLID principles:
 * - SRP: Only handles dashboard data queries
 * - OCP: Extensible with new query methods
 * - DIP: Depends on database abstraction
 */

import { db } from "../../db/client.ts";
import { bricklinkVolumeHistory } from "../../db/schema.ts";
import { and, eq, gte, lte, sql } from "drizzle-orm";

/**
 * Time-series data point for charts
 */
export interface VolumeDataPoint {
  recordedAt: Date;
  totalQty: number | null;
  timesSold: number | null;
  totalLots: number | null;
  avgPrice: number | null; // In dollars (converted from cents)
  minPrice: number | null;
  maxPrice: number | null;
  qtyAvgPrice: number | null;
  currency: string;
}

/**
 * Aggregated volume data for a condition/period combination
 */
export interface VolumeSeriesData {
  condition: "new" | "used";
  timePeriod: "six_month" | "current";
  dataPoints: VolumeDataPoint[];
}

/**
 * Complete volume history for an item
 */
export interface ItemVolumeHistory {
  itemId: string;
  series: VolumeSeriesData[];
}

/**
 * Trend analysis result
 */
export interface VolumeTrend {
  direction: "up" | "down" | "stable" | "unknown";
  percentageChange: number | null;
  periodStart: Date | null;
  periodEnd: Date | null;
  startVolume: number | null;
  endVolume: number | null;
}

/**
 * Dashboard summary statistics
 */
export interface VolumeStatistics {
  totalVolume: number;
  averageVolume: number;
  peakVolume: number;
  peakDate: Date | null;
  transactionCount: number;
  averageTransactionSize: number;
  trend: VolumeTrend;
}

/**
 * BricklinkDashboardService - Provides dashboard-ready data
 */
export class BricklinkDashboardService {
  /**
   * Get volume history for an item, organized by series
   */
  async getVolumeHistory(
    itemId: string,
    options?: {
      startDate?: Date;
      endDate?: Date;
      conditions?: Array<"new" | "used">;
      timePeriods?: Array<"six_month" | "current">;
    },
  ): Promise<ItemVolumeHistory> {
    // Build query conditions
    const conditions = [eq(bricklinkVolumeHistory.itemId, itemId)];

    if (options?.startDate) {
      conditions.push(
        gte(bricklinkVolumeHistory.recordedAt, options.startDate),
      );
    }

    if (options?.endDate) {
      conditions.push(lte(bricklinkVolumeHistory.recordedAt, options.endDate));
    }

    // Query all records
    const records = await db
      .select()
      .from(bricklinkVolumeHistory)
      .where(and(...conditions))
      .orderBy(bricklinkVolumeHistory.recordedAt);

    // Group by condition and time period
    const seriesMap = new Map<string, VolumeDataPoint[]>();

    for (const record of records) {
      // Filter by condition if specified
      if (
        options?.conditions &&
        !options.conditions.includes(record.condition)
      ) {
        continue;
      }

      // Filter by time period if specified
      if (
        options?.timePeriods &&
        !options.timePeriods.includes(record.timePeriod)
      ) {
        continue;
      }

      const key = `${record.condition}-${record.timePeriod}`;

      if (!seriesMap.has(key)) {
        seriesMap.set(key, []);
      }

      seriesMap.get(key)!.push({
        recordedAt: record.recordedAt,
        totalQty: record.totalQty,
        timesSold: record.timesSold,
        totalLots: record.totalLots,
        avgPrice: record.avgPrice ? record.avgPrice / 100 : null, // Convert cents to dollars
        minPrice: record.minPrice ? record.minPrice / 100 : null,
        maxPrice: record.maxPrice ? record.maxPrice / 100 : null,
        qtyAvgPrice: record.qtyAvgPrice ? record.qtyAvgPrice / 100 : null,
        currency: record.currency || "USD",
      });
    }

    // Convert map to series array
    const series: VolumeSeriesData[] = [];
    for (const [key, dataPoints] of seriesMap.entries()) {
      const [condition, timePeriod] = key.split("-") as [
        "new" | "used",
        "six_month" | "current",
      ];
      series.push({ condition, timePeriod, dataPoints });
    }

    return { itemId, series };
  }

  /**
   * Get volume statistics for an item
   */
  async getVolumeStatistics(
    itemId: string,
    options?: {
      condition?: "new" | "used";
      timePeriod?: "six_month" | "current";
      startDate?: Date;
      endDate?: Date;
    },
  ): Promise<VolumeStatistics> {
    // Build query conditions
    const conditions = [eq(bricklinkVolumeHistory.itemId, itemId)];

    if (options?.condition) {
      conditions.push(eq(bricklinkVolumeHistory.condition, options.condition));
    }

    if (options?.timePeriod) {
      conditions.push(
        eq(bricklinkVolumeHistory.timePeriod, options.timePeriod),
      );
    }

    if (options?.startDate) {
      conditions.push(
        gte(bricklinkVolumeHistory.recordedAt, options.startDate),
      );
    }

    if (options?.endDate) {
      conditions.push(lte(bricklinkVolumeHistory.recordedAt, options.endDate));
    }

    // Query records
    const records = await db
      .select()
      .from(bricklinkVolumeHistory)
      .where(and(...conditions))
      .orderBy(bricklinkVolumeHistory.recordedAt);

    if (records.length === 0) {
      return {
        totalVolume: 0,
        averageVolume: 0,
        peakVolume: 0,
        peakDate: null,
        transactionCount: 0,
        averageTransactionSize: 0,
        trend: {
          direction: "unknown",
          percentageChange: null,
          periodStart: null,
          periodEnd: null,
          startVolume: null,
          endVolume: null,
        },
      };
    }

    // Calculate statistics
    let totalVolume = 0;
    let totalTransactions = 0;
    let peakVolume = 0;
    let peakDate: Date | null = null;

    for (const record of records) {
      const volume = record.totalQty || 0;
      totalVolume += volume;
      totalTransactions += record.timesSold || 0;

      if (volume > peakVolume) {
        peakVolume = volume;
        peakDate = record.recordedAt;
      }
    }

    const averageVolume = records.length > 0 ? totalVolume / records.length : 0;
    const averageTransactionSize = totalTransactions > 0
      ? totalVolume / totalTransactions
      : 0;

    // Calculate trend
    const trend = this.calculateTrend(records);

    return {
      totalVolume,
      averageVolume,
      peakVolume,
      peakDate,
      transactionCount: totalTransactions,
      averageTransactionSize,
      trend,
    };
  }

  /**
   * Calculate volume trend from records
   */
  private calculateTrend(
    records: typeof bricklinkVolumeHistory.$inferSelect[],
  ): VolumeTrend {
    if (records.length < 2) {
      return {
        direction: "unknown",
        percentageChange: null,
        periodStart: null,
        periodEnd: null,
        startVolume: null,
        endVolume: null,
      };
    }

    const first = records[0];
    const last = records[records.length - 1];

    const startVolume = first.totalQty || 0;
    const endVolume = last.totalQty || 0;

    let percentageChange: number | null = null;
    let direction: "up" | "down" | "stable" = "stable";

    if (startVolume > 0) {
      percentageChange = ((endVolume - startVolume) / startVolume) * 100;

      if (percentageChange > 5) {
        direction = "up";
      } else if (percentageChange < -5) {
        direction = "down";
      } else {
        direction = "stable";
      }
    } else if (endVolume > 0) {
      direction = "up";
      percentageChange = 100;
    }

    return {
      direction,
      percentageChange,
      periodStart: first.recordedAt,
      periodEnd: last.recordedAt,
      startVolume,
      endVolume,
    };
  }

  /**
   * Compare volume across multiple items
   */
  async compareItems(
    itemIds: string[],
    options?: {
      condition?: "new" | "used";
      timePeriod?: "six_month" | "current";
      startDate?: Date;
      endDate?: Date;
    },
  ): Promise<
    Array<{
      itemId: string;
      statistics: VolumeStatistics;
    }>
  > {
    const results = [];

    for (const itemId of itemIds) {
      const statistics = await this.getVolumeStatistics(itemId, options);
      results.push({ itemId, statistics });
    }

    return results;
  }

  /**
   * Get latest volume snapshot for an item
   */
  async getLatestVolume(
    itemId: string,
    options?: {
      condition?: "new" | "used";
      timePeriod?: "six_month" | "current";
    },
  ): Promise<VolumeDataPoint | null> {
    const conditions = [eq(bricklinkVolumeHistory.itemId, itemId)];

    if (options?.condition) {
      conditions.push(eq(bricklinkVolumeHistory.condition, options.condition));
    }

    if (options?.timePeriod) {
      conditions.push(
        eq(bricklinkVolumeHistory.timePeriod, options.timePeriod),
      );
    }

    const records = await db
      .select()
      .from(bricklinkVolumeHistory)
      .where(and(...conditions))
      .orderBy(sql`${bricklinkVolumeHistory.recordedAt} DESC`)
      .limit(1);

    if (records.length === 0) return null;

    const record = records[0];

    return {
      recordedAt: record.recordedAt,
      totalQty: record.totalQty,
      timesSold: record.timesSold,
      totalLots: record.totalLots,
      avgPrice: record.avgPrice ? record.avgPrice / 100 : null,
      minPrice: record.minPrice ? record.minPrice / 100 : null,
      maxPrice: record.maxPrice ? record.maxPrice / 100 : null,
      qtyAvgPrice: record.qtyAvgPrice ? record.qtyAvgPrice / 100 : null,
      currency: record.currency || "USD",
    };
  }
}

/**
 * Singleton instance
 */
let dashboardServiceInstance: BricklinkDashboardService | null = null;

/**
 * Get the singleton BricklinkDashboardService instance
 */
export function getBricklinkDashboardService(): BricklinkDashboardService {
  if (!dashboardServiceInstance) {
    dashboardServiceInstance = new BricklinkDashboardService();
  }
  return dashboardServiceInstance;
}
