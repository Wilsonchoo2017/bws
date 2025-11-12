/**
 * RetirementRepository - Data access layer for BrickRanker retirement data
 * Single Responsibility: Retirement database operations only
 * Follows Repository Pattern for clean architecture
 */

import { eq } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import {
  type BrickrankerRetirementItem,
  brickrankerRetirementItems,
} from "../../../db/schema.ts";
import type { IRetirementRepository } from "./IRepository.ts";

export class RetirementRepository implements IRetirementRepository {
  /**
   * Find retirement data by LEGO set number
   */
  async findByLegoSetNumber(
    setNumber: string,
  ): Promise<BrickrankerRetirementItem | null> {
    try {
      const result = await db
        .select()
        .from(brickrankerRetirementItems)
        .where(eq(brickrankerRetirementItems.setNumber, setNumber))
        .limit(1);

      return result.length > 0 ? result[0] : null;
    } catch (error) {
      // Gracefully handle missing table or other DB errors
      console.warn(
        `[RetirementRepository] Failed to fetch retirement data for set ${setNumber}:`,
        error instanceof Error ? error.message : error,
      );
      return null; // Return null instead of throwing
    }
  }
}
