/**
 * BricklinkRepository - Data access layer for Bricklink data
 * Single Responsibility: Bricklink database operations only
 * Follows Repository Pattern for clean architecture
 */

import { eq, inArray } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import { type BricklinkItem, bricklinkItems } from "../../../db/schema.ts";
import type {
  IBricklinkRepository,
  PastSalesStatistics,
} from "./IRepository.ts";
import { getBricklinkRepository } from "../../../services/bricklink/BricklinkRepository.ts";

export class BricklinkRepository implements IBricklinkRepository {
  /**
   * Find Bricklink item by LEGO set number
   * Tries both exact match and with "-1" suffix (e.g., "10368" and "10368-1")
   */
  async findByLegoSetNumber(setNumber: string): Promise<BricklinkItem | null> {
    // Try exact match first
    let item = await this.findByItemId(setNumber);
    if (item) {
      return item;
    }

    // Try with "-1" suffix if not already present
    if (!setNumber.endsWith("-1")) {
      const itemIdWithSuffix = `${setNumber}-1`;
      item = await this.findByItemId(itemIdWithSuffix);
      if (item) {
        return item;
      }
    }

    return null;
  }

  /**
   * Find Bricklink item by item ID
   */
  async findByItemId(itemId: string): Promise<BricklinkItem | null> {
    try {
      const result = await db
        .select()
        .from(bricklinkItems)
        .where(eq(bricklinkItems.itemId, itemId))
        .limit(1);

      return result.length > 0 ? result[0] : null;
    } catch (error) {
      // Gracefully handle missing table or other DB errors
      console.warn(
        `[BricklinkRepository] Failed to fetch item ${itemId}:`,
        error instanceof Error ? error.message : error,
      );
      return null; // Return null instead of throwing
    }
  }

  /**
   * Find multiple Bricklink items by LEGO set numbers (batch operation)
   * Returns a map of setNumber -> BricklinkItem for O(1) lookup
   * Solves N+1 query problem
   */
  async findByLegoSetNumbers(
    setNumbers: string[],
  ): Promise<Map<string, BricklinkItem>> {
    if (setNumbers.length === 0) return new Map();

    // Try both formats: exact match and with "-1" suffix
    // Some sets use "10368" and some use "10368-1"
    const itemIds: string[] = [];
    for (const num of setNumbers) {
      itemIds.push(num); // Exact match
      if (!num.endsWith("-1")) {
        itemIds.push(`${num}-1`); // Try with -1 suffix
      }
    }

    try {
      const results = await db
        .select()
        .from(bricklinkItems)
        .where(inArray(bricklinkItems.itemId, itemIds));

      // Build map: setNumber -> BricklinkItem
      // Map using the original set number (without -1 suffix)
      const resultMap = new Map<string, BricklinkItem>();
      for (const item of results) {
        // Remove "-1" suffix if present to get original set number
        const setNumber = item.itemId.replace(/-1$/, "");
        // Only set if not already mapped (prefer exact match over -1 variant)
        if (!resultMap.has(setNumber)) {
          resultMap.set(setNumber, item);
        }
      }

      return resultMap;
    } catch (error) {
      console.warn(
        `[BricklinkRepository] Failed to batch fetch items (count: ${setNumbers.length}):`,
        error instanceof Error ? error.message : error,
      );
      return new Map(); // Return empty map on error
    }
  }

  /**
   * Get past sales statistics for an item
   * Now uses monthly sales data instead of individual transactions
   * Delegates to BricklinkRepository for actual data access
   */
  async getPastSalesStatistics(
    itemId: string,
  ): Promise<PastSalesStatistics | null> {
    try {
      const repo = getBricklinkRepository();
      const stats = await repo.getMonthlySalesStatistics(itemId);
      return stats;
    } catch (error) {
      console.warn(
        `[BricklinkRepository] Failed to fetch monthly sales statistics for ${itemId}:`,
        error instanceof Error ? error.message : error,
      );
      return null;
    }
  }

  /**
   * Get past sales statistics for multiple items (batch operation)
   * Returns a map of itemId -> PastSalesStatistics for O(1) lookup
   * Solves N+1 query problem for past sales data
   */
  async getPastSalesStatisticsBatch(
    itemIds: string[],
  ): Promise<Map<string, PastSalesStatistics>> {
    if (itemIds.length === 0) return new Map();

    try {
      const repo = getBricklinkRepository();
      const resultMap = new Map<string, PastSalesStatistics>();

      // Fetch statistics for each item using monthly sales data
      // Note: This is parallelized but could be optimized further with a true batch query
      const results = await Promise.allSettled(
        itemIds.map(async (itemId) => {
          const stats = await repo.getMonthlySalesStatistics(itemId);
          return { itemId, stats };
        }),
      );

      // Build result map from successful fetches
      for (const result of results) {
        if (result.status === "fulfilled" && result.value.stats) {
          resultMap.set(result.value.itemId, result.value.stats);
        }
      }

      return resultMap;
    } catch (error) {
      console.warn(
        `[BricklinkRepository] Failed to batch fetch monthly sales statistics (count: ${itemIds.length}):`,
        error instanceof Error ? error.message : error,
      );
      return new Map();
    }
  }
}
