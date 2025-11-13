/**
 * BargainHunterStrategy - Optimized for finding deep discounts
 * Prioritizes: discount depth, good ratings, decent demand
 * Use case: Getting the best deals on quality products
 */

import { BaseStrategy } from "./BaseStrategy.ts";
import type { DimensionWeights } from "../types.ts";

export class BargainHunterStrategy extends BaseStrategy {
  constructor() {
    const weights: DimensionWeights = {
      quality: 0.50, // Highest priority - want quality products (25% + 25%)
      demand: 0.40, // Important - want popular items (15% + 25%)
      availability: 0.10, // Lower priority - not urgency focused (unchanged)
    };

    super(
      "Bargain Hunter",
      "Finds quality products with good ratings and demand. Buy prices set conservatively with large margin of safety.",
      weights,
    );
  }

  // Override action determination to be more selective on pricing
  protected override determineAction(
    score: number,
  ): "strong_buy" | "buy" | "hold" | "pass" {
    if (score >= 85) return "strong_buy"; // Higher threshold
    if (score >= 70) return "buy";
    if (score >= 50) return "hold";
    return "pass";
  }
}
