import type { BricklinkItem } from "../../db/schema.ts";
import { getBricklinkRepository } from "./BricklinkRepository.ts";

export interface BricklinkDataValidationResult {
  isComplete: boolean;
  missingBoxes: string[];
  hasMonthlyData?: boolean;
  message?: string;
}

/**
 * Service for validating Bricklink data completeness
 */
export class BricklinkDataValidator {
  /**
   * Validates that all four pricing boxes are populated (not null).
   * Note: A null pricing box is valid (means no sales data exists).
   * A non-null box with null total_qty indicates incomplete scraping.
   *
   * For prerequisite checks, we require ALL four boxes to be populated.
   */
  static validateCompleteness(
    bricklinkItem: BricklinkItem | null | undefined,
  ): BricklinkDataValidationResult {
    if (!bricklinkItem) {
      return {
        isComplete: false,
        missingBoxes: [
          "sixMonthNew",
          "sixMonthUsed",
          "currentNew",
          "currentUsed",
        ],
        message: "No Bricklink item data exists",
      };
    }

    const missingBoxes: string[] = [];
    const pricingBoxes = [
      { key: "sixMonthNew", value: bricklinkItem.sixMonthNew },
      { key: "sixMonthUsed", value: bricklinkItem.sixMonthUsed },
      { key: "currentNew", value: bricklinkItem.currentNew },
      { key: "currentUsed", value: bricklinkItem.currentUsed },
    ];

    for (const box of pricingBoxes) {
      if (box.value === null || box.value === undefined) {
        missingBoxes.push(box.key);
      }
    }

    const isComplete = missingBoxes.length === 0;

    return {
      isComplete,
      missingBoxes,
      message: isComplete
        ? undefined
        : `Missing pricing data: ${missingBoxes.join(", ")}`,
    };
  }

  /**
   * Validates completeness including monthly sales data check
   * This is async because it queries the database for monthly sales
   */
  static async validateCompletenessWithMonthlyData(
    bricklinkItem: BricklinkItem | null | undefined,
  ): Promise<BricklinkDataValidationResult> {
    const basicValidation = this.validateCompleteness(bricklinkItem);

    if (!bricklinkItem) {
      return {
        ...basicValidation,
        hasMonthlyData: false,
      };
    }

    // Check if monthly sales data exists
    try {
      const repo = getBricklinkRepository();
      const hasMonthlyData = await repo.hasMonthlyData(bricklinkItem.itemId);

      return {
        ...basicValidation,
        hasMonthlyData,
        isComplete: basicValidation.isComplete && hasMonthlyData,
        message: !hasMonthlyData
          ? `${basicValidation.message || ""} No monthly sales data available`.trim()
          : basicValidation.message,
      };
    } catch (error) {
      console.warn(
        `[BricklinkDataValidator] Failed to check monthly data for ${bricklinkItem.itemId}:`,
        error,
      );
      return {
        ...basicValidation,
        hasMonthlyData: false,
      };
    }
  }

  /**
   * Validates an array of Bricklink items and returns which ones are incomplete
   */
  static validateBatch(
    items: Map<number, BricklinkItem | null>,
  ): Map<number, BricklinkDataValidationResult> {
    const results = new Map<number, BricklinkDataValidationResult>();

    for (const [productId, item] of items.entries()) {
      results.set(productId, this.validateCompleteness(item));
    }

    return results;
  }

  /**
   * Validates an array of Bricklink items including monthly data check (async)
   */
  static async validateBatchWithMonthlyData(
    items: Map<number, BricklinkItem | null>,
  ): Promise<Map<number, BricklinkDataValidationResult>> {
    const results = new Map<number, BricklinkDataValidationResult>();

    const validations = await Promise.all(
      Array.from(items.entries()).map(async ([productId, item]) => {
        const validation = await this.validateCompletenessWithMonthlyData(item);
        return { productId, validation };
      }),
    );

    for (const { productId, validation } of validations) {
      results.set(productId, validation);
    }

    return results;
  }
}
