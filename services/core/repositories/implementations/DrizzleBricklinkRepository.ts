/**
 * Drizzle ORM implementation of IBricklinkRepository
 * Single Responsibility: BrickLink data access using existing repository
 *
 * This is an adapter that wraps the existing BricklinkRepository
 * to comply with the new interface structure
 */

import type { BricklinkItem } from "../../../../db/schema.ts";
import { getBricklinkRepository } from "../../../bricklink/BricklinkRepository.ts";
import type {
  IBricklinkRepository,
  PastSalesStatistics,
} from "../interfaces/IBricklinkRepository.ts";
import { eq, inArray } from "drizzle-orm";
import { db } from "../../../../db/client.ts";
import { bricklinkItems } from "../../../../db/schema.ts";

export class DrizzleBricklinkRepository implements IBricklinkRepository {
  /**
   * Find BrickLink item by LEGO set number
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
   * Find BrickLink item by exact item ID
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
        `[DrizzleBricklinkRepository] Failed to fetch item ${itemId}:`,
        error instanceof Error ? error.message : error,
      );
      return null; // Return null instead of throwing
    }
  }

  /**
   * Find multiple BrickLink items by LEGO set numbers (batch operation)
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
      const items = await db
        .select()
        .from(bricklinkItems)
        .where(inArray(bricklinkItems.itemId, itemIds));

      // Build map: setNumber -> BricklinkItem
      // Handle both "12345" and "12345-1" formats
      const resultMap = new Map<string, BricklinkItem>();
      for (const item of items) {
        // Map both with and without "-1" suffix
        resultMap.set(item.itemId, item);
        if (item.itemId.endsWith("-1")) {
          const baseNumber = item.itemId.slice(0, -2); // Remove "-1"
          if (!resultMap.has(baseNumber)) {
            resultMap.set(baseNumber, item);
          }
        }
      }

      return resultMap;
    } catch (error) {
      console.warn(
        `[DrizzleBricklinkRepository] Failed to batch fetch items (count: ${setNumbers.length}):`,
        error instanceof Error ? error.message : error,
      );
      return new Map(); // Return empty map on error
    }
  }

  /**
   * Get past sales statistics for an item
   * Delegates to existing BricklinkRepository for monthly sales data
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
        `[DrizzleBricklinkRepository] Failed to fetch monthly sales statistics for ${itemId}:`,
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
      // Parallelized for performance
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
        `[DrizzleBricklinkRepository] Failed to batch fetch monthly sales statistics (count: ${itemIds.length}):`,
        error instanceof Error ? error.message : error,
      );
      return new Map();
    }
  }
}
