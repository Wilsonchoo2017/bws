/**
 * BricklinkRepository - Data access layer for Bricklink data
 * Single Responsibility: Bricklink database operations only
 * Follows Repository Pattern for clean architecture
 */

import { eq } from "drizzle-orm";
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
    return this.findByItemId(itemId);
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
}
