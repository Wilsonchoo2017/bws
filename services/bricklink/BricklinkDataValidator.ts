import type { BricklinkItem } from "../../db/schema.ts";

export interface BricklinkDataValidationResult {
  isComplete: boolean;
  missingBoxes: string[];
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
    bricklinkItem: BricklinkItem | null | undefined
  ): BricklinkDataValidationResult {
    if (!bricklinkItem) {
      return {
        isComplete: false,
        missingBoxes: ["sixMonthNew", "sixMonthUsed", "currentNew", "currentUsed"],
        message: "No Bricklink item data exists"
      };
    }

    const missingBoxes: string[] = [];
    const pricingBoxes = [
      { key: "sixMonthNew", value: bricklinkItem.sixMonthNew },
      { key: "sixMonthUsed", value: bricklinkItem.sixMonthUsed },
      { key: "currentNew", value: bricklinkItem.currentNew },
      { key: "currentUsed", value: bricklinkItem.currentUsed }
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
        : `Missing pricing data: ${missingBoxes.join(", ")}`
    };
  }

  /**
   * Validates an array of Bricklink items and returns which ones are incomplete
   */
  static validateBatch(
    items: Map<number, BricklinkItem | null>
  ): Map<number, BricklinkDataValidationResult> {
    const results = new Map<number, BricklinkDataValidationResult>();

    for (const [productId, item] of items.entries()) {
      results.set(productId, this.validateCompleteness(item));
    }

    return results;
  }
}
