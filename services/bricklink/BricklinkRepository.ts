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
  bricklinkPriceHistory,
  bricklinkVolumeHistory,
  type NewBricklinkItem,
  type NewBricklinkPriceHistory,
  type NewBricklinkVolumeHistory,
} from "../../db/schema.ts";
import { eq } from "drizzle-orm";
import type { PricingBox, PriceData } from "./BricklinkParser.ts";

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
   * Update an existing item
   */
  async update(
    itemId: string,
    data: UpdateBricklinkItemData,
  ): Promise<BricklinkItem | undefined> {
    const [updated] = await db.update(bricklinkItems)
      .set({
        ...data,
        updatedAt: new Date(),
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
   */
  async findItemsNeedingScraping(): Promise<BricklinkItem[]> {
    const now = new Date();

    // Use raw SQL for better control
    const items = await db.select()
      .from(bricklinkItems)
      .where(eq(bricklinkItems.watchStatus, "active"));

    // Filter items that need scraping
    return items.filter((item) => {
      if (!item.nextScrapeAt) {
        // If never scraped, needs scraping
        return true;
      }
      return item.nextScrapeAt <= now;
    });
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
   * Create or update item (upsert logic)
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
    const existing = await this.findByItemId(itemId);

    if (existing) {
      // Update existing
      const updateData: UpdateBricklinkItemData = {
        title: data.title,
        weight: data.weight,
        sixMonthNew: data.sixMonthNew,
        sixMonthUsed: data.sixMonthUsed,
        currentNew: data.currentNew,
        currentUsed: data.currentUsed,
      };

      // Update image fields if provided
      if (data.imageUrl !== undefined) {
        updateData.imageUrl = data.imageUrl;
      }
      if (data.localImagePath !== undefined) {
        updateData.localImagePath = data.localImagePath;
        updateData.imageDownloadedAt = new Date();
      }
      if (data.imageDownloadStatus !== undefined) {
        updateData.imageDownloadStatus = data.imageDownloadStatus;
      }

      const updated = await this.update(itemId, updateData);

      return { item: updated!, isNew: false };
    } else {
      // Create new
      const now = new Date();
      const intervalDays = data.scrapeIntervalDays || 30;
      const nextScrape = new Date(
        now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
      );

      const newItemData: NewBricklinkItem = {
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
      };

      const created = await this.create(newItemData);

      return { item: created, isNew: true };
    }
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
   */
  async count(): Promise<number> {
    const result = await db.select()
      .from(bricklinkItems);

    return result.length;
  }

  /**
   * Count items by watch status
   */
  async countByWatchStatus(
    watchStatus: "active" | "paused" | "stopped" | "archived",
  ): Promise<number> {
    const result = await db.select()
      .from(bricklinkItems)
      .where(eq(bricklinkItems.watchStatus, watchStatus));

    return result.length;
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
    const sixMonthNewRecord = createRecord(data.sixMonthNew, "new", "six_month");
    const sixMonthUsedRecord = createRecord(data.sixMonthUsed, "used", "six_month");
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
    let query = db.select()
      .from(bricklinkVolumeHistory)
      .where(eq(bricklinkVolumeHistory.itemId, itemId));

    // Note: Additional filtering would require building the query dynamically
    // For now, we return all records and let the caller filter
    const results = await query
      .orderBy(bricklinkVolumeHistory.recordedAt)
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
