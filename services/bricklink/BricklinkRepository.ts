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
  bricklinkPastSales,
  bricklinkPriceHistory,
  bricklinkVolumeHistory,
  type NewBricklinkItem,
  type NewBricklinkPriceHistory,
  type NewBricklinkVolumeHistory,
} from "../../db/schema.ts";
import { and, eq, lte, or, sql } from "drizzle-orm";
import type {
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
   */
  private priceToInteger(priceData?: PriceData): number | undefined {
    if (!priceData) return undefined;
    return Math.round(priceData.amount * 100);
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
