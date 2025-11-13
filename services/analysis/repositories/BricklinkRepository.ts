/**
 * BricklinkRepository - Data access layer for Bricklink data
 * Single Responsibility: Bricklink database operations only
 * Follows Repository Pattern for clean architecture
 */

import { eq, inArray } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import { type BricklinkItem, bricklinkItems } from "../../../db/schema.ts";
import type { IBricklinkRepository } from "./IRepository.ts";

export class BricklinkRepository implements IBricklinkRepository {
  /**
   * Find Bricklink item by LEGO set number
   * Automatically prefixes with "S-" for sets
   */
  async findByLegoSetNumber(setNumber: string): Promise<BricklinkItem | null> {
    const itemId = `S-${setNumber}`;
    return await this.findByItemId(itemId);
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

    // Convert to item IDs (prefix with "S-")
    const itemIds = setNumbers.map((num) => `S-${num}`);

    try {
      const results = await db
        .select()
        .from(bricklinkItems)
        .where(inArray(bricklinkItems.itemId, itemIds));

      // Build map: setNumber -> BricklinkItem
      const resultMap = new Map<string, BricklinkItem>();
      for (const item of results) {
        // Remove "S-" prefix to get set number
        const setNumber = item.itemId.replace(/^S-/, "");
        resultMap.set(setNumber, item);
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
}
