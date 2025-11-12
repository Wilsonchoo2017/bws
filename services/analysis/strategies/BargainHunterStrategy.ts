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
      pricing: 0.50, // Highest priority - looking for discounts
      quality: 0.25, // Important - want quality products
      demand: 0.15, // Medium priority - want popular items
      availability: 0.10, // Lower priority - not urgency focused
    };

    super(
      "Bargain Hunter",
      "Finds deep discounts on quality products with good ratings. Best for getting great deals on popular sets.",
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
