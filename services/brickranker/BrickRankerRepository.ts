/**
 * BrickRankerRepository - Database access layer for BrickRanker retirement items
 *
 * Responsibilities (Single Responsibility Principle):
 * - CRUD operations for brickranker_retirement_items table
 * - Query building and execution
 * - Transaction management
 * - Product matching/linking logic
 *
 * This service follows SOLID principles:
 * - SRP: Only handles database operations
 * - OCP: Can be extended without modifying core logic
 * - DIP: Depends on database abstraction (Drizzle ORM)
 * - ISP: Focused interface for BrickRanker retirement data
 */

import { db } from "../../db/client.ts";
import {
  type BrickrankerRetirementItem,
  brickrankerRetirementItems,
  type NewBrickrankerRetirementItem,
  products,
} from "../../db/schema.ts";
import { eq } from "drizzle-orm";

/**
 * Interface for update data
 */
export interface UpdateRetirementItemData {
  setName?: string;
  yearReleased?: number | null;
  retiringSoon?: boolean;
  expectedRetirementDate?: string | null;
  theme?: string;
  productId?: number | null;
  isActive?: boolean;
  lastScrapedAt?: Date;
  nextScrapeAt?: Date;
  updatedAt?: Date;
}

/**
 * BrickRankerRepository - Handles all database operations for BrickRanker retirement items
 */
export class BrickRankerRepository {
  /**
   * Find item by set number
   */
  async findBySetNumber(
    setNumber: string,
  ): Promise<BrickrankerRetirementItem | undefined> {
    return await db.query.brickrankerRetirementItems.findFirst({
      where: eq(brickrankerRetirementItems.setNumber, setNumber),
    });
  }

  /**
   * Find item by database ID
   */
  async findById(id: number): Promise<BrickrankerRetirementItem | undefined> {
    return await db.query.brickrankerRetirementItems.findFirst({
      where: eq(brickrankerRetirementItems.id, id),
    });
  }

  /**
   * Create a new retirement item
   */
  async create(
    data: NewBrickrankerRetirementItem,
  ): Promise<BrickrankerRetirementItem> {
    const [item] = await db.insert(brickrankerRetirementItems)
      .values(data)
      .returning();

    return item;
  }

  /**
   * Update an existing item
   */
  async update(
    setNumber: string,
    data: UpdateRetirementItemData,
  ): Promise<BrickrankerRetirementItem | undefined> {
    const [updated] = await db.update(brickrankerRetirementItems)
      .set({
        ...data,
        updatedAt: new Date(),
      })
      .where(eq(brickrankerRetirementItems.setNumber, setNumber))
      .returning();

    return updated;
  }

  /**
   * Delete an item
   */
  async delete(setNumber: string): Promise<boolean> {
    await db.delete(brickrankerRetirementItems)
      .where(eq(brickrankerRetirementItems.setNumber, setNumber));

    return true;
  }

  /**
   * Get all active items
   */
  async findActiveItems(): Promise<BrickrankerRetirementItem[]> {
    return await db.query.brickrankerRetirementItems.findMany({
      where: eq(brickrankerRetirementItems.isActive, true),
    });
  }

  /**
   * Get items by theme
   */
  async findByTheme(theme: string): Promise<BrickrankerRetirementItem[]> {
    return await db.query.brickrankerRetirementItems.findMany({
      where: eq(brickrankerRetirementItems.theme, theme),
    });
  }

  /**
   * Get items that need scraping (next_scrape_at <= now and is_active = true)
   */
  async findItemsNeedingScraping(): Promise<BrickrankerRetirementItem[]> {
    const now = new Date();

    // Get all active items
    const items = await db.select()
      .from(brickrankerRetirementItems)
      .where(eq(brickrankerRetirementItems.isActive, true));

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
   * Update scraping timestamps
   */
  async updateScrapingTimestamps(
    setNumber: string,
    intervalDays: number,
  ): Promise<void> {
    const now = new Date();
    const nextScrape = new Date(
      now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
    );

    await db.update(brickrankerRetirementItems)
      .set({
        lastScrapedAt: now,
        nextScrapeAt: nextScrape,
        scrapedAt: now,
        updatedAt: now,
      })
      .where(eq(brickrankerRetirementItems.setNumber, setNumber));
  }

  /**
   * Find matching product in products table by LEGO set number
   */
  async findProductBySetNumber(setNumber: string): Promise<number | null> {
    const product = await db.query.products.findFirst({
      where: eq(products.legoSetNumber, setNumber),
      columns: {
        id: true,
      },
    });

    return product?.id || null;
  }

  /**
   * Link retirement item to product
   */
  async linkToProduct(
    setNumber: string,
    productId: number,
  ): Promise<void> {
    await db.update(brickrankerRetirementItems)
      .set({
        productId,
        updatedAt: new Date(),
      })
      .where(eq(brickrankerRetirementItems.setNumber, setNumber));
  }

  /**
   * Mark items as inactive (not found on page anymore)
   */
  async markAsInactive(setNumbers: string[]): Promise<void> {
    // Note: Drizzle doesn't have a NOT IN operator helper, so we'll do individual updates
    for (const setNumber of setNumbers) {
      await db.update(brickrankerRetirementItems)
        .set({
          isActive: false,
          updatedAt: new Date(),
        })
        .where(eq(brickrankerRetirementItems.setNumber, setNumber));
    }
  }

  /**
   * Mark all items as inactive except the provided set numbers
   */
  async markAllAsInactiveExcept(activeSetNumbers: string[]): Promise<void> {
    // Get all current items
    const allItems = await db.select({
      setNumber: brickrankerRetirementItems.setNumber,
    })
      .from(brickrankerRetirementItems);

    // Find items not in active list
    const inactiveSetNumbers = allItems
      .map((item) => item.setNumber)
      .filter((setNumber) => !activeSetNumbers.includes(setNumber));

    // Mark them as inactive
    if (inactiveSetNumbers.length > 0) {
      await this.markAsInactive(inactiveSetNumbers);
    }
  }

  /**
   * Create or update item (upsert logic)
   */
  async upsert(
    setNumber: string,
    data: {
      setName: string;
      yearReleased: number | null;
      retiringSoon: boolean;
      expectedRetirementDate: string | null;
      theme: string;
      scrapeIntervalDays?: number;
    },
  ): Promise<{ item: BrickrankerRetirementItem; isNew: boolean }> {
    const existing = await this.findBySetNumber(setNumber);

    if (existing) {
      // Update existing
      const updated = await this.update(setNumber, {
        setName: data.setName,
        yearReleased: data.yearReleased,
        retiringSoon: data.retiringSoon,
        expectedRetirementDate: data.expectedRetirementDate,
        theme: data.theme,
        isActive: true, // Mark as active since it's still on the page
      });

      return { item: updated!, isNew: false };
    } else {
      // Create new
      const now = new Date();
      const intervalDays = data.scrapeIntervalDays || 30;
      const nextScrape = new Date(
        now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
      );

      // Try to find matching product
      const productId = await this.findProductBySetNumber(setNumber);

      const created = await this.create({
        setNumber,
        setName: data.setName,
        yearReleased: data.yearReleased,
        retiringSoon: data.retiringSoon,
        expectedRetirementDate: data.expectedRetirementDate,
        theme: data.theme,
        productId,
        isActive: true,
        scrapeIntervalDays: intervalDays,
        lastScrapedAt: now,
        nextScrapeAt: nextScrape,
        scrapedAt: now,
      });

      return { item: created, isNew: true };
    }
  }

  /**
   * Batch upsert items (for full page scrape)
   */
  async batchUpsert(
    items: {
      setNumber: string;
      setName: string;
      yearReleased: number | null;
      retiringSoon: boolean;
      expectedRetirementDate: string | null;
      theme: string;
    }[],
  ): Promise<{
    created: number;
    updated: number;
    total: number;
  }> {
    let created = 0;
    let updated = 0;

    // Process each item
    for (const item of items) {
      const result = await this.upsert(item.setNumber, item);
      if (result.isNew) {
        created++;
      } else {
        updated++;
      }
    }

    // Mark items not in the list as inactive
    const activeSetNumbers = items.map((item) => item.setNumber);
    await this.markAllAsInactiveExcept(activeSetNumbers);

    return {
      created,
      updated,
      total: items.length,
    };
  }

  /**
   * Get all items (with pagination)
   */
  async findAll(
    options: {
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<BrickrankerRetirementItem[]> {
    const limit = options.limit || 50;
    const offset = options.offset || 0;

    return await db.select()
      .from(brickrankerRetirementItems)
      .limit(limit)
      .offset(offset);
  }

  /**
   * Count total items
   */
  async count(): Promise<number> {
    const result = await db.select()
      .from(brickrankerRetirementItems);

    return result.length;
  }

  /**
   * Count active items
   */
  async countActive(): Promise<number> {
    const result = await db.select()
      .from(brickrankerRetirementItems)
      .where(eq(brickrankerRetirementItems.isActive, true));

    return result.length;
  }
}

/**
 * Singleton instance for reuse across the application
 */
let repositoryInstance: BrickRankerRepository | null = null;

/**
 * Get the singleton BrickRankerRepository instance
 */
export function getBrickRankerRepository(): BrickRankerRepository {
  if (!repositoryInstance) {
    repositoryInstance = new BrickRankerRepository();
  }
  return repositoryInstance;
}
