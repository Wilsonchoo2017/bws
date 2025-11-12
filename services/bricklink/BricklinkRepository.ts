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
  type NewBricklinkItem,
  type NewBricklinkPriceHistory,
} from "../../db/schema.ts";
import { eq } from "drizzle-orm";
import type { PricingBox } from "./BricklinkParser.ts";

/**
 * Interface for update data
 */
export interface UpdateBricklinkItemData {
  title?: string | null;
  weight?: string | null;
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
      const updated = await this.update(itemId, {
        title: data.title,
        weight: data.weight,
        sixMonthNew: data.sixMonthNew,
        sixMonthUsed: data.sixMonthUsed,
        currentNew: data.currentNew,
        currentUsed: data.currentUsed,
      });

      return { item: updated!, isNew: false };
    } else {
      // Create new
      const now = new Date();
      const intervalDays = data.scrapeIntervalDays || 30;
      const nextScrape = new Date(
        now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
      );

      const created = await this.create({
        itemId,
        itemType: data.itemType,
        title: data.title,
        weight: data.weight,
        sixMonthNew: data.sixMonthNew,
        sixMonthUsed: data.sixMonthUsed,
        currentNew: data.currentNew,
        currentUsed: data.currentUsed,
        scrapeIntervalDays: intervalDays,
        lastScrapedAt: now,
        nextScrapeAt: nextScrape,
      });

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
