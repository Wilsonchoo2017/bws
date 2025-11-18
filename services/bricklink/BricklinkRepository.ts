/**
 * BricklinkRepository - Database access layer for Bricklink items
 *
 * Responsibilities (Single Responsibility Principle):
 * - CRUD operations for bricklink_items table
 * - Price history management
 * - Query building and execution
 * - Transaction management
 *
 * This service follows SOLID principles:
 * - SRP: Only handles database operations
 * - OCP: Can be extended without modifying core logic
 * - DIP: Depends on database abstraction (Drizzle ORM)
 * - ISP: Focused interface for Bricklink data
 */

import { db } from "../../db/client.ts";
import {
  type BricklinkItem,
  bricklinkItems,
  bricklinkMonthlySales,
  bricklinkPastSales,
  bricklinkPriceHistory,
  bricklinkVolumeHistory,
  type NewBricklinkItem,
  type NewBricklinkMonthlySale as _NewBricklinkMonthlySale,
  type NewBricklinkPriceHistory,
  type NewBricklinkVolumeHistory,
} from "../../db/schema.ts";
import { and, eq, lte, or, sql } from "drizzle-orm";
import type {
  MonthlySalesSummary,
  PastSaleTransaction,
  PriceData,
  PricingBox,
} from "./BricklinkParser.ts";

/**
 * Interface for update data
 */
export interface UpdateBricklinkItemData {
  title?: string | null;
  weight?: string | null;
  imageUrl?: string | null;
  localImagePath?: string | null;
  imageDownloadedAt?: Date;
  imageDownloadStatus?: string;
  sixMonthNew?: PricingBox | null;
  sixMonthUsed?: PricingBox | null;
  currentNew?: PricingBox | null;
  currentUsed?: PricingBox | null;
  watchStatus?: "active" | "paused" | "stopped" | "archived";
  scrapeIntervalDays?: number;
  lastScrapedAt?: Date;
  nextScrapeAt?: Date;
  updatedAt?: Date;
}

/**
 * BricklinkRepository - Handles all database operations for Bricklink items
 */
export class BricklinkRepository {
  /**
   * Find item by item ID
   */
  async findByItemId(itemId: string): Promise<BricklinkItem | undefined> {
    return await db.query.bricklinkItems.findFirst({
      where: eq(bricklinkItems.itemId, itemId),
    });
  }

  /**
   * Find item by database ID
   */
  async findById(id: number): Promise<BricklinkItem | undefined> {
    return await db.query.bricklinkItems.findFirst({
      where: eq(bricklinkItems.id, id),
    });
  }

  /**
   * Create a new item
   */
  async create(data: NewBricklinkItem): Promise<BricklinkItem> {
    const [item] = await db.insert(bricklinkItems)
      .values(data)
      .returning();

    return item;
  }

  /**
   * Update an existing item with optimistic locking
   * @param itemId - The item ID to update
   * @param data - The data to update
   * @param expectedUpdatedAt - Optional timestamp for optimistic locking
   * @returns Updated item or undefined if update failed due to conflict
   * @throws Error if item not found or concurrent update detected
   */
  async update(
    itemId: string,
    data: UpdateBricklinkItemData,
    expectedUpdatedAt?: Date,
  ): Promise<BricklinkItem | undefined> {
    const now = new Date();

    // If optimistic locking is requested, check updatedAt timestamp
    if (expectedUpdatedAt) {
      const [updated] = await db.update(bricklinkItems)
        .set({
          ...data,
          updatedAt: now,
        })
        .where(
          and(
            eq(bricklinkItems.itemId, itemId),
            eq(bricklinkItems.updatedAt, expectedUpdatedAt),
          ),
        )
        .returning();

      if (!updated) {
        // Either item doesn't exist or updatedAt doesn't match (concurrent update)
        const existing = await this.findByItemId(itemId);
        if (!existing) {
          throw new Error(`Item ${itemId} not found`);
        }
        throw new Error(
          `Concurrent update detected for item ${itemId}. Expected updatedAt: ${expectedUpdatedAt.toISOString()}, actual: ${existing.updatedAt.toISOString()}`,
        );
      }

      return updated;
    }

    // No optimistic locking - standard update
    const [updated] = await db.update(bricklinkItems)
      .set({
        ...data,
        updatedAt: now,
      })
      .where(eq(bricklinkItems.itemId, itemId))
      .returning();

    return updated;
  }

  /**
   * Delete an item
   */
  async delete(itemId: string): Promise<boolean> {
    await db.delete(bricklinkItems)
      .where(eq(bricklinkItems.itemId, itemId));

    return true;
  }

  /**
   * Get all items with specific watch status
   */
  async findByWatchStatus(
    watchStatus: "active" | "paused" | "stopped" | "archived",
  ): Promise<BricklinkItem[]> {
    return await db.query.bricklinkItems.findMany({
      where: eq(bricklinkItems.watchStatus, watchStatus),
    });
  }

  /**
   * Get items that need scraping (next_scrape_at <= now and watch_status = active)
   * Optimized: Uses SQL WHERE clause instead of filtering in application code
   */
  async findItemsNeedingScraping(): Promise<BricklinkItem[]> {
    const now = new Date();

    // Use SQL to filter items that need scraping
    // Items need scraping if: watch_status = active AND (next_scrape_at IS NULL OR next_scrape_at <= now)
    return await db.select()
      .from(bricklinkItems)
      .where(
        and(
          eq(bricklinkItems.watchStatus, "active"),
          or(
            sql`${bricklinkItems.nextScrapeAt} IS NULL`,
            lte(bricklinkItems.nextScrapeAt, now),
          ),
        ),
      );
  }

  /**
   * Create a price history record
   */
  async createPriceHistory(
    data: NewBricklinkPriceHistory,
  ): Promise<void> {
    await db.insert(bricklinkPriceHistory).values(data);
  }

  /**
   * Get price history for an item
   */
  async getPriceHistory(
    itemId: string,
    limit: number = 100,
  ): Promise<typeof bricklinkPriceHistory.$inferSelect[]> {
    return await db.select()
      .from(bricklinkPriceHistory)
      .where(eq(bricklinkPriceHistory.itemId, itemId))
      .orderBy(bricklinkPriceHistory.recordedAt)
      .limit(limit);
  }

  /**
   * Update scraping timestamps
   */
  async updateScrapingTimestamps(
    itemId: string,
    intervalDays: number,
  ): Promise<void> {
    const now = new Date();
    const nextScrape = new Date(
      now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
    );

    await db.update(bricklinkItems)
      .set({
        lastScrapedAt: now,
        nextScrapeAt: nextScrape,
        updatedAt: now,
      })
      .where(eq(bricklinkItems.itemId, itemId));
  }

  /**
   * Batch update scraping timestamps for multiple items
   * Optimized: Updates multiple items at once using SQL IN clause
   */
  async updateManyScrapingTimestamps(
    itemIds: string[],
    intervalDays: number,
  ): Promise<void> {
    if (itemIds.length === 0) return;

    const now = new Date();
    const nextScrape = new Date(
      now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
    );

    await db.update(bricklinkItems)
      .set({
        lastScrapedAt: now,
        nextScrapeAt: nextScrape,
        updatedAt: now,
      })
      .where(sql`${bricklinkItems.itemId} = ANY(${itemIds})`);
  }

  /**
   * Batch update multiple items with different data
   * Note: For truly different data per item, use transactions with individual updates
   * For same-data updates, use updateManyScrapingTimestamps or similar methods
   */
  async updateMany(
    updates: Array<{
      itemId: string;
      data: UpdateBricklinkItemData;
    }>,
  ): Promise<void> {
    if (updates.length === 0) return;

    // Use a transaction to ensure atomicity
    await db.transaction(async (tx) => {
      for (const { itemId, data } of updates) {
        await tx.update(bricklinkItems)
          .set({
            ...data,
            updatedAt: new Date(),
          })
          .where(eq(bricklinkItems.itemId, itemId));
      }
    });
  }

  /**
   * Create or update item (atomic upsert using ON CONFLICT)
   * This prevents race conditions in concurrent environments
   */
  async upsert(
    itemId: string,
    data: {
      itemType: string;
      title: string | null;
      weight: string | null;
      yearReleased?: number | null;
      imageUrl?: string | null;
      localImagePath?: string | null;
      imageDownloadStatus?: string;
      sixMonthNew: PricingBox | null;
      sixMonthUsed: PricingBox | null;
      currentNew: PricingBox | null;
      currentUsed: PricingBox | null;
      scrapeIntervalDays?: number;
    },
  ): Promise<{ item: BricklinkItem; isNew: boolean }> {
    const now = new Date();
    const intervalDays = data.scrapeIntervalDays || 30;
    const nextScrape = new Date(
      now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
    );

    // Prepare update fields (only update what's provided)
    const updateFields: Partial<typeof bricklinkItems.$inferInsert> = {
      title: data.title,
      weight: data.weight,
      yearReleased: data.yearReleased,
      sixMonthNew: data.sixMonthNew,
      sixMonthUsed: data.sixMonthUsed,
      currentNew: data.currentNew,
      currentUsed: data.currentUsed,
      lastScrapedAt: now,
      nextScrapeAt: nextScrape,
      updatedAt: now,
    };

    // Conditionally add image fields if provided
    if (data.imageUrl !== undefined) {
      updateFields.imageUrl = data.imageUrl;
    }
    if (data.localImagePath !== undefined) {
      updateFields.localImagePath = data.localImagePath;
      updateFields.imageDownloadedAt = now;
    }
    if (data.imageDownloadStatus !== undefined) {
      updateFields.imageDownloadStatus = data.imageDownloadStatus;
    }

    // Atomic upsert using PostgreSQL ON CONFLICT
    const [result] = await db
      .insert(bricklinkItems)
      .values({
        itemId,
        itemType: data.itemType,
        title: data.title,
        weight: data.weight,
        yearReleased: data.yearReleased || null,
        imageUrl: data.imageUrl || null,
        localImagePath: data.localImagePath || null,
        imageDownloadedAt: data.localImagePath ? now : null,
        imageDownloadStatus: data.imageDownloadStatus || null,
        sixMonthNew: data.sixMonthNew,
        sixMonthUsed: data.sixMonthUsed,
        currentNew: data.currentNew,
        currentUsed: data.currentUsed,
        scrapeIntervalDays: intervalDays,
        lastScrapedAt: now,
        nextScrapeAt: nextScrape,
      })
      .onConflictDoUpdate({
        target: bricklinkItems.itemId,
        set: updateFields,
      })
      .returning();

    // Determine if this was a new insert by checking if lastScrapedAt was null before this operation
    // Since we always set lastScrapedAt, we use createdAt = updatedAt as proxy for new records
    const isNew = result.createdAt.getTime() === result.updatedAt.getTime();

    return { item: result, isNew };
  }

  /**
   * Get all items (with pagination)
   */
  async findAll(
    options: {
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<BricklinkItem[]> {
    const limit = options.limit || 50;
    const offset = options.offset || 0;

    return await db.select()
      .from(bricklinkItems)
      .limit(limit)
      .offset(offset);
  }

  /**
   * Count total items
   * Optimized: Uses SQL COUNT(*) instead of fetching all rows
   */
  async count(): Promise<number> {
    const result = await db
      .select({ count: sql<number>`cast(count(*) as integer)` })
      .from(bricklinkItems);

    return result[0]?.count ?? 0;
  }

  /**
   * Count items by watch status
   * Optimized: Uses SQL COUNT(*) instead of fetching all rows
   */
  async countByWatchStatus(
    watchStatus: "active" | "paused" | "stopped" | "archived",
  ): Promise<number> {
    const result = await db
      .select({ count: sql<number>`cast(count(*) as integer)` })
      .from(bricklinkItems)
      .where(eq(bricklinkItems.watchStatus, watchStatus));

    return result[0]?.count ?? 0;
  }

  /**
   * Helper to convert price to cents (integer)
   * ⚠️ UNIT CONVENTION: Converts DOLLARS to CENTS for database storage
   *
   * Parser validation: Ensures price is non-negative before storing
   */
  private priceToInteger(priceData?: PriceData): number | undefined {
    if (!priceData) return undefined;

    const cents = Math.round(priceData.amount * 100);

    // Validation: Ensure price is valid
    if (cents < 0 || !isFinite(cents)) {
      console.warn(
        `[BricklinkRepository] Invalid price: ${priceData.amount} → ${cents} cents`,
      );
      return undefined;
    }

    return cents;
  }

  /**
   * Create normalized volume history records from pricing boxes
   * Creates 4 records (six_month new/used, current new/used)
   */
  async createVolumeHistory(data: {
    itemId: string;
    sixMonthNew: PricingBox | null;
    sixMonthUsed: PricingBox | null;
    currentNew: PricingBox | null;
    currentUsed: PricingBox | null;
  }): Promise<void> {
    const records: NewBricklinkVolumeHistory[] = [];
    const now = new Date();

    // Helper to create record from pricing box
    const createRecord = (
      box: PricingBox | null,
      condition: "new" | "used",
      timePeriod: "six_month" | "current",
    ): NewBricklinkVolumeHistory | null => {
      if (!box) return null;

      return {
        itemId: data.itemId,
        condition,
        timePeriod,
        totalQty: box.total_qty ?? null,
        timesSold: box.times_sold ?? null,
        totalLots: box.total_lots ?? null,
        minPrice: this.priceToInteger(box.min_price) ?? null,
        avgPrice: this.priceToInteger(box.avg_price) ?? null,
        qtyAvgPrice: this.priceToInteger(box.qty_avg_price) ?? null,
        maxPrice: this.priceToInteger(box.max_price) ?? null,
        currency: box.min_price?.currency ||
          box.avg_price?.currency ||
          box.max_price?.currency ||
          "USD",
        recordedAt: now,
      };
    };

    // Create records for all 4 boxes
    const sixMonthNewRecord = createRecord(
      data.sixMonthNew,
      "new",
      "six_month",
    );
    const sixMonthUsedRecord = createRecord(
      data.sixMonthUsed,
      "used",
      "six_month",
    );
    const currentNewRecord = createRecord(data.currentNew, "new", "current");
    const currentUsedRecord = createRecord(data.currentUsed, "used", "current");

    // Add non-null records
    if (sixMonthNewRecord) records.push(sixMonthNewRecord);
    if (sixMonthUsedRecord) records.push(sixMonthUsedRecord);
    if (currentNewRecord) records.push(currentNewRecord);
    if (currentUsedRecord) records.push(currentUsedRecord);

    // Batch insert all records
    if (records.length > 0) {
      await db.insert(bricklinkVolumeHistory).values(records);
    }
  }

  /**
   * Get volume history for an item
   */
  async getVolumeHistory(
    itemId: string,
    options?: {
      condition?: "new" | "used";
      timePeriod?: "six_month" | "current";
      limit?: number;
      startDate?: Date;
      endDate?: Date;
    },
  ): Promise<typeof bricklinkVolumeHistory.$inferSelect[]> {
    // Note: Additional filtering would require building the query dynamically
    // For now, we return all records and let the caller filter
    const results = await db.select()
      .from(bricklinkVolumeHistory)
      .where(eq(bricklinkVolumeHistory.itemId, itemId))
      .orderBy(bricklinkVolumeHistory.recordedAt)
      .limit(options?.limit || 1000);

    return results;
  }

  /**
   * Upsert past sales transactions for an item
   * Uses ON CONFLICT to avoid duplicates based on (itemId, dateSold, condition, price)
   *
   * @param itemId - The Bricklink item ID
   * @param transactions - Array of past sale transactions to store
   * @returns Number of transactions inserted (may be less than input if duplicates exist)
   */
  async upsertPastSales(
    itemId: string,
    transactions: PastSaleTransaction[],
  ): Promise<number> {
    if (transactions.length === 0) {
      return 0;
    }

    const now = new Date();

    // Convert transactions to database format
    const values = transactions.map((tx) => ({
      itemId,
      dateSold: tx.date_sold,
      condition: tx.condition,
      price: Math.round(tx.price.amount * 100), // Store as cents
      currency: tx.price.currency,
      sellerLocation: tx.seller_location || null,
      quantity: tx.quantity || null,
      scrapedAt: now,
    }));

    // Bulk insert with ON CONFLICT DO NOTHING to skip duplicates
    const result = await db.insert(bricklinkPastSales)
      .values(values)
      .onConflictDoNothing({
        target: [
          bricklinkPastSales.itemId,
          bricklinkPastSales.dateSold,
          bricklinkPastSales.condition,
          bricklinkPastSales.price,
        ],
      })
      .returning();

    return result.length;
  }

  /**
   * Get past sales transactions for an item
   *
   * @param itemId - The Bricklink item ID
   * @param options - Optional filters for condition, date range, and limit
   * @returns Array of past sales transactions
   */
  async getPastSales(
    itemId: string,
    options?: {
      condition?: "new" | "used";
      startDate?: Date;
      endDate?: Date;
      limit?: number;
    },
  ): Promise<typeof bricklinkPastSales.$inferSelect[]> {
    const conditions = [eq(bricklinkPastSales.itemId, itemId)];

    if (options?.condition) {
      conditions.push(eq(bricklinkPastSales.condition, options.condition));
    }

    if (options?.startDate) {
      conditions.push(
        sql`${bricklinkPastSales.dateSold} >= ${options.startDate}`,
      );
    }

    if (options?.endDate) {
      conditions.push(
        sql`${bricklinkPastSales.dateSold} <= ${options.endDate}`,
      );
    }

    const results = await db.select()
      .from(bricklinkPastSales)
      .where(and(...conditions))
      .orderBy(bricklinkPastSales.dateSold)
      .limit(options?.limit || 1000);

    return results;
  }

  /**
   * Upsert monthly sales summaries for an item
   * Uses ON CONFLICT DO UPDATE to replace existing monthly summaries with new data
   *
   * @param itemId - The Bricklink item ID
   * @param summaries - Array of monthly sales summaries to store
   * @returns Number of summaries inserted or updated
   */
  async upsertMonthlySales(
    itemId: string,
    summaries: MonthlySalesSummary[],
  ): Promise<number> {
    if (summaries.length === 0) {
      return 0;
    }

    const now = new Date();

    // Convert summaries to database format
    const values = summaries.map((summary) => ({
      itemId,
      month: summary.month,
      condition: summary.condition,
      timesSold: summary.times_sold,
      totalQuantity: summary.total_quantity,
      minPrice: summary.min_price
        ? Math.round(summary.min_price.amount * 100)
        : null,
      maxPrice: summary.max_price
        ? Math.round(summary.max_price.amount * 100)
        : null,
      avgPrice: summary.avg_price
        ? Math.round(summary.avg_price.amount * 100)
        : null,
      currency: summary.min_price?.currency ||
        summary.max_price?.currency ||
        summary.avg_price?.currency ||
        "USD",
      scrapedAt: now,
    }));

    // Bulk insert with ON CONFLICT DO UPDATE to replace existing data
    const result = await db.insert(bricklinkMonthlySales)
      .values(values)
      .onConflictDoUpdate({
        target: [
          bricklinkMonthlySales.itemId,
          bricklinkMonthlySales.month,
          bricklinkMonthlySales.condition,
        ],
        set: {
          timesSold: sql`EXCLUDED.times_sold`,
          totalQuantity: sql`EXCLUDED.total_quantity`,
          minPrice: sql`EXCLUDED.min_price`,
          maxPrice: sql`EXCLUDED.max_price`,
          avgPrice: sql`EXCLUDED.avg_price`,
          currency: sql`EXCLUDED.currency`,
          scrapedAt: sql`EXCLUDED.scraped_at`,
        },
      })
      .returning();

    return result.length;
  }

  /**
   * Get monthly sales summaries for an item
   *
   * @param itemId - The Bricklink item ID
   * @param options - Optional filters for condition and date range
   * @returns Array of monthly sales summaries
   */
  async getMonthlySales(
    itemId: string,
    options?: {
      condition?: "new" | "used";
      startMonth?: string; // YYYY-MM format
      endMonth?: string; // YYYY-MM format
    },
  ): Promise<typeof bricklinkMonthlySales.$inferSelect[]> {
    const conditions = [eq(bricklinkMonthlySales.itemId, itemId)];

    if (options?.condition) {
      conditions.push(eq(bricklinkMonthlySales.condition, options.condition));
    }

    if (options?.startMonth) {
      conditions.push(
        sql`${bricklinkMonthlySales.month} >= ${options.startMonth}`,
      );
    }

    if (options?.endMonth) {
      conditions.push(
        sql`${bricklinkMonthlySales.month} <= ${options.endMonth}`,
      );
    }

    const results = await db.select()
      .from(bricklinkMonthlySales)
      .where(and(...conditions))
      .orderBy(bricklinkMonthlySales.month);

    return results;
  }

  /**
   * Check if monthly sales data exists for an item
   * Used to determine if immediate scraping priority is needed
   */
  async hasMonthlyData(itemId: string): Promise<boolean> {
    const result = await db.select({ count: sql<number>`count(*)` })
      .from(bricklinkMonthlySales)
      .where(eq(bricklinkMonthlySales.itemId, itemId));

    return result[0]?.count > 0;
  }

  /**
   * Update monthly data availability status
   * Sets the flag indicating whether monthly sales data exists on BrickLink
   * @param itemId - The BrickLink item ID
   * @param unavailable - True if monthly data doesn't exist, false if it does
   */
  async updateMonthlyDataStatus(
    itemId: string,
    unavailable: boolean,
  ): Promise<void> {
    await db.update(bricklinkItems)
      .set({
        monthlyDataUnavailable: unavailable,
        monthlyDataLastChecked: new Date(),
      })
      .where(eq(bricklinkItems.itemId, itemId));
  }

  /**
   * Get market-driven statistics from MONTHLY sales data
   * Uses aggregated monthly sales instead of individual transactions
   * Calculates similar metrics to getPastSalesStatistics but from monthly summaries
   *
   * @param itemId - The Bricklink item ID
   * @returns Market statistics derived from monthly aggregated data
   */
  async getMonthlySalesStatistics(itemId: string): Promise<{
    totalTransactions: number;
    dateRangeStart: Date | null;
    dateRangeEnd: Date | null;
    totalDays: number;
    new: {
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
    };
    used: {
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
    };
    rsi: {
      new: number | null;
      used: number | null;
    };
  }> {
    // Calculate 6 months ago for filtering
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    const startMonth = `${sixMonthsAgo.getFullYear()}-${String(sixMonthsAgo.getMonth() + 1).padStart(2, '0')}`;

    // Fetch monthly sales for this item (last 6 months only)
    const monthlySales = await this.getMonthlySales(itemId, { startMonth });

    if (monthlySales.length === 0) {
      return this.getEmptyStatistics();
    }

    // Separate by condition
    const newSales = monthlySales.filter((s) => s.condition === "new");
    const usedSales = monthlySales.filter((s) => s.condition === "used");

    // Calculate date range from month strings (YYYY-MM format)
    const months = monthlySales.map((s) => s.month).sort();
    const startMonth = months[0];
    const endMonth = months[months.length - 1];

    // Convert YYYY-MM to Date (use first day of month)
    const minDate = new Date(`${startMonth}-01`);
    const maxDate = new Date(`${endMonth}-01`);

    // Calculate total days (approximate - use 30 days per month)
    const totalDays = Math.max(
      1,
      Math.ceil(
        (maxDate.getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24),
      ) + 30, // Add 30 days for the last month
    );

    // Calculate metrics for each condition from monthly data
    const newMetrics = this.calculateMonthlyConditionMetrics(newSales, totalDays);
    const usedMetrics = this.calculateMonthlyConditionMetrics(usedSales, totalDays);

    // Calculate RSI from monthly price data
    const newRsi = this.calculateMonthlyRSI(newSales);
    const usedRsi = this.calculateMonthlyRSI(usedSales);

    return {
      totalTransactions: monthlySales.reduce((sum, s) => sum + s.timesSold, 0),
      dateRangeStart: minDate,
      dateRangeEnd: maxDate,
      totalDays,
      new: newMetrics,
      used: usedMetrics,
      rsi: {
        new: newRsi,
        used: usedRsi,
      },
    };
  }

  /**
   * Get market-driven statistics from past sales data
   * Inspired by stock market technical analysis:
   * - Velocity: Sales transactions per day (like trading volume)
   * - Liquidity: Average time between sales
   * - Momentum: Price trends over time periods
   * - Volatility: Price stability (coefficient of variation)
   * - Market depth: Available lots vs demand
   *
   * @param itemId - The Bricklink item ID
   * @returns Market statistics for investment analysis
   */
  async getPastSalesStatistics(itemId: string): Promise<{
    // Overall metrics
    totalTransactions: number;
    dateRangeStart: Date | null;
    dateRangeEnd: Date | null;
    totalDays: number;

    // Condition-specific metrics (new items weighted higher for investment)
    new: {
      transactionCount: number;
      totalQuantity: number;
      salesVelocity: number; // transactions per day
      avgDaysBetweenSales: number;

      // Price metrics (in cents)
      avgPrice: number;
      medianPrice: number;
      minPrice: number;
      maxPrice: number;
      priceStdDev: number;
      volatilityIndex: number; // coefficient of variation (stdDev / mean)

      // Trend analysis (30d, 90d, 180d, all-time)
      trends: {
        last30Days: TrendMetrics;
        last90Days: TrendMetrics;
        last180Days: TrendMetrics;
        allTime: TrendMetrics;
      };

      // Recent activity
      recent30d: number;
      recent60d: number;
      recent90d: number;
    };

    used: {
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
    };

    // Relative strength index (adapted for LEGO)
    // Measures if item is overbought (>70) or oversold (<30) based on price history
    rsi: {
      new: number | null;
      used: number | null;
    };
  }> {
    // Fetch all past sales for this item
    const allSales = await this.getPastSales(itemId);

    if (allSales.length === 0) {
      return this.getEmptyStatistics();
    }

    // Separate by condition
    const newSales = allSales.filter((s) => s.condition === "new");
    const usedSales = allSales.filter((s) => s.condition === "used");

    // Calculate date range
    const dates = allSales.map((s) => s.dateSold.getTime());
    const minDate = new Date(Math.min(...dates));
    const maxDate = new Date(Math.max(...dates));
    const totalDays = Math.max(
      1,
      Math.ceil(
        (maxDate.getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24),
      ),
    );

    // Calculate metrics for each condition
    const newMetrics = this.calculateConditionMetrics(newSales, totalDays);
    const usedMetrics = this.calculateConditionMetrics(usedSales, totalDays);

    // Calculate RSI
    const newRsi = this.calculateRSI(newSales);
    const usedRsi = this.calculateRSI(usedSales);

    return {
      totalTransactions: allSales.length,
      dateRangeStart: minDate,
      dateRangeEnd: maxDate,
      totalDays,
      new: newMetrics,
      used: usedMetrics,
      rsi: {
        new: newRsi,
        used: usedRsi,
      },
    };
  }

  /**
   * Calculate metrics for a specific condition (new or used)
   */
  private calculateConditionMetrics(
    sales: typeof bricklinkPastSales.$inferSelect[],
    totalDays: number,
  ) {
    if (sales.length === 0) {
      return this.getEmptyConditionMetrics();
    }

    const now = new Date();
    const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    const sixtyDaysAgo = new Date(now.getTime() - 60 * 24 * 60 * 60 * 1000);
    const ninetyDaysAgo = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
    const oneEightyDaysAgo = new Date(
      now.getTime() - 180 * 24 * 60 * 60 * 1000,
    );

    // Basic counts
    const transactionCount = sales.length;
    const totalQuantity = sales.reduce((sum, s) => sum + (s.quantity || 1), 0);
    const salesVelocity = transactionCount / totalDays;
    const avgDaysBetweenSales = totalDays / transactionCount;

    // Recent activity counts
    const recent30d = sales.filter((s) => s.dateSold >= thirtyDaysAgo).length;
    const recent60d = sales.filter((s) => s.dateSold >= sixtyDaysAgo).length;
    const recent90d = sales.filter((s) => s.dateSold >= ninetyDaysAgo).length;

    // Price statistics
    const prices = sales.map((s) => s.price);
    prices.sort((a, b) => a - b);

    const avgPrice = prices.reduce((sum, p) => sum + p, 0) / prices.length;
    const medianPrice = prices[Math.floor(prices.length / 2)];
    const minPrice = prices[0];
    const maxPrice = prices[prices.length - 1];

    // Standard deviation and volatility
    const variance = prices.reduce(
      (sum, p) => sum + Math.pow(p - avgPrice, 2),
      0,
    ) / prices.length;
    const priceStdDev = Math.sqrt(variance);
    const volatilityIndex = avgPrice > 0 ? priceStdDev / avgPrice : 0;

    // Calculate trends for different time periods
    const trends = {
      last30Days: this.calculateTrendMetrics(
        sales.filter((s) => s.dateSold >= thirtyDaysAgo),
      ),
      last90Days: this.calculateTrendMetrics(
        sales.filter((s) => s.dateSold >= ninetyDaysAgo),
      ),
      last180Days: this.calculateTrendMetrics(
        sales.filter((s) => s.dateSold >= oneEightyDaysAgo),
      ),
      allTime: this.calculateTrendMetrics(sales),
    };

    return {
      transactionCount,
      totalQuantity,
      salesVelocity,
      avgDaysBetweenSales,
      avgPrice,
      medianPrice,
      minPrice,
      maxPrice,
      priceStdDev,
      volatilityIndex,
      trends,
      recent30d,
      recent60d,
      recent90d,
    };
  }

  /**
   * Calculate trend metrics for a time period
   * Returns momentum indicators (bullish/bearish/neutral)
   */
  private calculateTrendMetrics(
    sales: typeof bricklinkPastSales.$inferSelect[],
  ): TrendMetrics {
    if (sales.length < 2) {
      return {
        direction: "neutral",
        momentum: 0,
        percentChange: 0,
        volumeTrend: "neutral",
        avgPrice: sales.length > 0 ? sales[0].price : 0,
      };
    }

    // Sort by date
    const sorted = [...sales].sort((a, b) =>
      a.dateSold.getTime() - b.dateSold.getTime()
    );

    // Calculate price trend using linear regression slope
    const n = sorted.length;
    const avgPrice = sorted.reduce((sum, s) => sum + s.price, 0) / n;

    // Use index as x-axis (time progression)
    const avgX = (n - 1) / 2;
    let numerator = 0;
    let denominator = 0;

    for (let i = 0; i < n; i++) {
      const xDiff = i - avgX;
      const yDiff = sorted[i].price - avgPrice;
      numerator += xDiff * yDiff;
      denominator += xDiff * xDiff;
    }

    const slope = denominator !== 0 ? numerator / denominator : 0;

    // Calculate percent change from first to last
    const firstPrice = sorted[0].price;
    const lastPrice = sorted[n - 1].price;
    const percentChange = firstPrice > 0
      ? ((lastPrice - firstPrice) / firstPrice) * 100
      : 0;

    // Determine direction based on slope and percent change
    let direction: "increasing" | "stable" | "decreasing" | "neutral" =
      "neutral";
    if (percentChange > 5) direction = "increasing";
    else if (percentChange < -5) direction = "decreasing";
    else direction = "stable";

    // Calculate volume trend (comparing first half to second half)
    const midpoint = Math.floor(n / 2);
    const firstHalf = sorted.slice(0, midpoint);
    const secondHalf = sorted.slice(midpoint);

    const firstHalfAvgVolume = firstHalf.length > 0
      ? firstHalf.reduce((sum, s) => sum + (s.quantity || 1), 0) /
        firstHalf.length
      : 0;
    const secondHalfAvgVolume = secondHalf.length > 0
      ? secondHalf.reduce((sum, s) => sum + (s.quantity || 1), 0) /
        secondHalf.length
      : 0;

    let volumeTrend: "increasing" | "stable" | "decreasing" | "neutral" =
      "neutral";
    if (secondHalfAvgVolume > firstHalfAvgVolume * 1.2) {
      volumeTrend = "increasing";
    } else if (secondHalfAvgVolume < firstHalfAvgVolume * 0.8) {
      volumeTrend = "decreasing";
    } else {
      volumeTrend = "stable";
    }

    return {
      direction,
      momentum: slope,
      percentChange,
      volumeTrend,
      avgPrice,
    };
  }

  /**
   * Calculate Relative Strength Index (RSI)
   * Adapted from stock market technical analysis
   * RSI > 70 = overbought (price may decrease)
   * RSI < 30 = oversold (price may increase)
   */
  private calculateRSI(
    sales: typeof bricklinkPastSales.$inferSelect[],
    period: number = 14,
  ): number | null {
    if (sales.length < period + 1) {
      return null;
    }

    // Sort by date
    const sorted = [...sales].sort((a, b) =>
      a.dateSold.getTime() - b.dateSold.getTime()
    );

    // Calculate price changes
    const changes: number[] = [];
    for (let i = 1; i < sorted.length; i++) {
      changes.push(sorted[i].price - sorted[i - 1].price);
    }

    // Use last 'period' changes
    const recentChanges = changes.slice(-period);

    // Separate gains and losses
    const gains = recentChanges.filter((c) => c > 0);
    const losses = recentChanges.filter((c) => c < 0).map((c) => Math.abs(c));

    const avgGain = gains.length > 0
      ? gains.reduce((sum, g) => sum + g, 0) / period
      : 0;
    const avgLoss = losses.length > 0
      ? losses.reduce((sum, l) => sum + l, 0) / period
      : 0;

    if (avgLoss === 0) {
      return 100; // All gains, maximum RSI
    }

    const rs = avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));

    return Math.round(rsi * 100) / 100;
  }

  /**
   * Calculate metrics for a specific condition from MONTHLY sales data
   * Similar to calculateConditionMetrics but works with monthly aggregates
   */
  private calculateMonthlyConditionMetrics(
    monthlySales: typeof bricklinkMonthlySales.$inferSelect[],
    totalDays: number,
  ) {
    if (monthlySales.length === 0) {
      return this.getEmptyConditionMetrics();
    }

    // Sort by month
    const sorted = [...monthlySales].sort((a, b) => a.month.localeCompare(b.month));

    // Calculate totals
    const transactionCount = sorted.reduce((sum, s) => sum + s.timesSold, 0);
    const totalQuantity = sorted.reduce((sum, s) => sum + s.totalQuantity, 0);

    // Calculate velocity (transactions per day)
    const salesVelocity = totalDays > 0 ? transactionCount / totalDays : 0;

    // Approximate days between sales
    const avgDaysBetweenSales = transactionCount > 0 ? totalDays / transactionCount : 0;

    // Calculate price statistics from monthly averages
    const prices = sorted
      .filter((s) => s.avgPrice !== null)
      .map((s) => s.avgPrice!);

    const avgPrice = prices.length > 0
      ? prices.reduce((sum, p) => sum + p, 0) / prices.length
      : 0;

    const sortedPrices = [...prices].sort((a, b) => a - b);
    const medianPrice = sortedPrices.length > 0
      ? sortedPrices[Math.floor(sortedPrices.length / 2)]
      : 0;

    const minPrice = sorted
      .filter((s) => s.minPrice !== null)
      .reduce((min, s) => Math.min(min, s.minPrice!), Infinity);

    const maxPrice = sorted
      .filter((s) => s.maxPrice !== null)
      .reduce((max, s) => Math.max(max, s.maxPrice!), -Infinity);

    // Calculate standard deviation from monthly averages
    const variance = prices.length > 1
      ? prices.reduce((sum, p) => sum + Math.pow(p - avgPrice, 2), 0) /
        (prices.length - 1)
      : 0;
    const priceStdDev = Math.sqrt(variance);
    const volatilityIndex = avgPrice > 0 ? priceStdDev / avgPrice : 0;

    // Calculate trend metrics for different time periods
    const now = new Date();
    const last30DaysTrend = this.calculateMonthlyTrendMetrics(
      sorted,
      new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000),
    );
    const last90DaysTrend = this.calculateMonthlyTrendMetrics(
      sorted,
      new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000),
    );
    const last180DaysTrend = this.calculateMonthlyTrendMetrics(
      sorted,
      new Date(now.getTime() - 180 * 24 * 60 * 60 * 1000),
    );
    const allTimeTrend = this.calculateMonthlyTrendMetrics(sorted, null);

    // Calculate recent activity (approximate using month-based filtering)
    const recent30d = sorted
      .filter((s) => {
        const monthDate = new Date(`${s.month}-01`);
        return monthDate >= new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      })
      .reduce((sum, s) => sum + s.timesSold, 0);

    const recent60d = sorted
      .filter((s) => {
        const monthDate = new Date(`${s.month}-01`);
        return monthDate >= new Date(now.getTime() - 60 * 24 * 60 * 60 * 1000);
      })
      .reduce((sum, s) => sum + s.timesSold, 0);

    const recent90d = sorted
      .filter((s) => {
        const monthDate = new Date(`${s.month}-01`);
        return monthDate >= new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
      })
      .reduce((sum, s) => sum + s.timesSold, 0);

    return {
      transactionCount,
      totalQuantity,
      salesVelocity,
      avgDaysBetweenSales,
      avgPrice,
      medianPrice,
      minPrice: minPrice === Infinity ? 0 : minPrice,
      maxPrice: maxPrice === -Infinity ? 0 : maxPrice,
      priceStdDev,
      volatilityIndex,
      trends: {
        last30Days: last30DaysTrend,
        last90Days: last90DaysTrend,
        last180Days: last180DaysTrend,
        allTime: allTimeTrend,
      },
      recent30d,
      recent60d,
      recent90d,
    };
  }

  /**
   * Calculate trend metrics from monthly sales data
   */
  private calculateMonthlyTrendMetrics(
    monthlySales: typeof bricklinkMonthlySales.$inferSelect[],
    startDate: Date | null,
  ): TrendMetrics {
    // Filter to date range if specified
    const filtered = startDate
      ? monthlySales.filter((s) => {
        const monthDate = new Date(`${s.month}-01`);
        return monthDate >= startDate;
      })
      : monthlySales;

    if (filtered.length === 0) {
      return {
        direction: "neutral",
        momentum: 0,
        percentChange: 0,
        volumeTrend: "neutral",
        avgPrice: 0,
      };
    }

    // Sort by month
    const sorted = [...filtered].sort((a, b) => a.month.localeCompare(b.month));

    // Calculate price trend
    const prices = sorted.filter((s) => s.avgPrice !== null).map((s) => s.avgPrice!);
    const firstPrice = prices[0];
    const lastPrice = prices[prices.length - 1];

    const percentChange = firstPrice > 0
      ? ((lastPrice - firstPrice) / firstPrice) * 100
      : 0;

    const direction: "increasing" | "decreasing" | "stable" =
      percentChange > 5 ? "increasing" : percentChange < -5 ? "decreasing" : "stable";

    // Calculate momentum (simple linear regression slope approximation)
    const avgPrice = prices.reduce((sum, p) => sum + p, 0) / prices.length;
    const momentum = percentChange; // Use percent change as momentum approximation

    // Volume trend
    const volumes = sorted.map((s) => s.timesSold);
    const firstHalfVol = volumes.slice(0, Math.floor(volumes.length / 2))
      .reduce((sum, v) => sum + v, 0);
    const secondHalfVol = volumes.slice(Math.floor(volumes.length / 2))
      .reduce((sum, v) => sum + v, 0);

    const volumeTrend: "increasing" | "decreasing" | "stable" =
      secondHalfVol > firstHalfVol * 1.1
        ? "increasing"
        : secondHalfVol < firstHalfVol * 0.9
        ? "decreasing"
        : "stable";

    return {
      direction,
      momentum,
      percentChange,
      volumeTrend,
      avgPrice,
    };
  }

  /**
   * Calculate RSI from monthly price data
   * Similar to calculateRSI but works with monthly averages
   */
  private calculateMonthlyRSI(
    monthlySales: typeof bricklinkMonthlySales.$inferSelect[],
    period: number = 6, // Use 6 months instead of 14 days
  ): number | null {
    if (monthlySales.length < period + 1) {
      return null;
    }

    // Sort by month
    const sorted = [...monthlySales].sort((a, b) => a.month.localeCompare(b.month));

    // Calculate price changes from monthly averages
    const changes: number[] = [];
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].avgPrice !== null && sorted[i - 1].avgPrice !== null) {
        changes.push(sorted[i].avgPrice! - sorted[i - 1].avgPrice!);
      }
    }

    if (changes.length < period) {
      return null;
    }

    // Use last 'period' changes
    const recentChanges = changes.slice(-period);

    // Separate gains and losses
    const gains = recentChanges.filter((c) => c > 0);
    const losses = recentChanges.filter((c) => c < 0).map((c) => Math.abs(c));

    const avgGain = gains.length > 0
      ? gains.reduce((sum, g) => sum + g, 0) / period
      : 0;
    const avgLoss = losses.length > 0
      ? losses.reduce((sum, l) => sum + l, 0) / period
      : 0;

    if (avgLoss === 0) {
      return 100; // All gains, maximum RSI
    }

    const rs = avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));

    return Math.round(rsi * 100) / 100;
  }

  /**
   * Return empty statistics structure
   */
  private getEmptyStatistics() {
    return {
      totalTransactions: 0,
      dateRangeStart: null,
      dateRangeEnd: null,
      totalDays: 0,
      new: this.getEmptyConditionMetrics(),
      used: this.getEmptyConditionMetrics(),
      rsi: {
        new: null,
        used: null,
      },
    };
  }

  /**
   * Return empty condition metrics
   */
  private getEmptyConditionMetrics() {
    const emptyTrend: TrendMetrics = {
      direction: "neutral",
      momentum: 0,
      percentChange: 0,
      volumeTrend: "neutral",
      avgPrice: 0,
    };

    return {
      transactionCount: 0,
      totalQuantity: 0,
      salesVelocity: 0,
      avgDaysBetweenSales: 0,
      avgPrice: 0,
      medianPrice: 0,
      minPrice: 0,
      maxPrice: 0,
      priceStdDev: 0,
      volatilityIndex: 0,
      trends: {
        last30Days: emptyTrend,
        last90Days: emptyTrend,
        last180Days: emptyTrend,
        allTime: emptyTrend,
      },
      recent30d: 0,
      recent60d: 0,
      recent90d: 0,
    };
  }
}

/**
 * Trend metrics for a time period
 */
export interface TrendMetrics {
  direction: "increasing" | "stable" | "decreasing" | "neutral";
  momentum: number; // Linear regression slope
  percentChange: number; // Percent change from start to end
  volumeTrend: "increasing" | "stable" | "decreasing" | "neutral";
  avgPrice: number;
}

/**
 * Singleton instance for reuse across the application
 */
let repositoryInstance: BricklinkRepository | null = null;

/**
 * Get the singleton BricklinkRepository instance
 */
export function getBricklinkRepository(): BricklinkRepository {
  if (!repositoryInstance) {
    repositoryInstance = new BricklinkRepository();
  }
  return repositoryInstance;
}
