/**
 * ScarcityMultiplierCalculator - Extract scarcity multiplier logic
 *
 * EXTRACTED FROM:
 * - services/value-investing/ValueCalculator.ts (lines 637-728)
 *
 * SOLID Principles:
 * - Single Responsibility: Only calculates scarcity multipliers
 * - Open/Closed: Easy to adjust scarcity thresholds
 *
 * Key Insight: TRUE SCARCITY = Low supply relative to demand
 * This is DIFFERENT from saturation (which penalizes oversupply)
 * Scarcity provides a small premium for genuinely scarce items
 */

import { VALUE_INVESTING_CONFIG as CONFIG } from "../../value-investing/ValueInvestingConfig.ts";

/**
 * Scarcity multiplier input
 */
export interface ScarcityMultiplierInput {
  availableQty?: number; // Total units available for sale
  availableLots?: number; // Number of sellers
  salesVelocity?: number; // Sales per day
}

/**
 * Scarcity multiplier calculation result
 */
export interface ScarcityMultiplierResult {
  /** Final multiplier (0.95-1.10 range) */
  multiplier: number;
  /** Months of inventory (null if cannot calculate) */
  monthsOfInventory: number | null;
  /** Scarcity score (0-100) */
  scarcityScore: number;
  /** Scarcity tier (extremely_scarce, very_scarce, etc.) */
  tier: string;
  /** Human-readable explanation */
  explanation: string;
}

/**
 * ScarcityMultiplierCalculator - Instance-based for testability
 */
export class ScarcityMultiplierCalculator {
  constructor() {}

  /**
   * Calculate scarcity multiplier
   *
   * Primary mode: Uses months of inventory (qty / velocity)
   * Fallback mode: Uses quantity + lots scoring
   */
  calculate(input: ScarcityMultiplierInput): ScarcityMultiplierResult {
    const { availableQty, availableLots, salesVelocity } = input;

    // No data = no adjustment (neutral)
    if (
      (availableQty === undefined || availableQty === null) &&
      (availableLots === undefined || availableLots === null)
    ) {
      return {
        multiplier: 1.0,
        monthsOfInventory: null,
        scarcityScore: 50,
        tier: "unknown",
        explanation: "No scarcity data available, neutral multiplier (1.0×)",
      };
    }

    // Calculate months of inventory
    const monthsOfInventory = this.calculateMonthsOfInventory(
      availableQty,
      salesVelocity,
    );

    let scarcityScore = 50; // Default to neutral
    let tier = "neutral";

    if (monthsOfInventory !== null) {
      // Primary mode: Months of inventory
      const result = this.calculateFromMonthsOfInventory(monthsOfInventory);
      scarcityScore = result.score;
      tier = result.tier;
    } else {
      // Fallback mode: Quantity + lots scoring
      const result = this.calculateFromQuantityAndLots(availableQty, availableLots);
      scarcityScore = result.score;
      tier = result.tier;
    }

    // Convert scarcity score (0-100) to multiplier (0.95-1.10)
    // High scarcity (score 100) = 1.10× multiplier
    // Low scarcity (score 0) = 0.95× multiplier
    const multiplier = 0.95 + (scarcityScore / 100) * 0.15;
    const clampedMultiplier = Math.max(0.95, Math.min(1.10, multiplier));

    const explanation = this.generateExplanation(
      tier,
      monthsOfInventory,
      scarcityScore,
      clampedMultiplier,
    );

    return {
      multiplier: clampedMultiplier,
      monthsOfInventory,
      scarcityScore,
      tier,
      explanation,
    };
  }

  /**
   * Calculate scarcity score from months of inventory
   */
  private calculateFromMonthsOfInventory(
    months: number,
  ): { score: number; tier: string } {
    if (months < 1) {
      return { score: 95, tier: "extremely_scarce" };
    } else if (months < 3) {
      return { score: 80, tier: "very_scarce" };
    } else if (months < 6) {
      return { score: 65, tier: "moderately_scarce" };
    } else if (months < 12) {
      return { score: 50, tier: "neutral" };
    } else if (months < 24) {
      return { score: 35, tier: "abundant" };
    } else {
      return { score: 20, tier: "oversupplied" };
    }
  }

  /**
   * Fallback: Calculate scarcity score from quantity and lots
   */
  private calculateFromQuantityAndLots(
    qty?: number,
    lots?: number,
  ): { score: number; tier: string } {
    let qtyScore = 50;
    let lotsScore = 50;

    if (qty !== undefined && qty !== null) {
      if (qty === 0) {
        qtyScore = 100; // Out of stock = maximum scarcity
      } else if (qty < 10) {
        qtyScore = 90; // Very low quantity
      } else if (qty < 50) {
        qtyScore = 70; // Low quantity
      } else if (qty < 200) {
        qtyScore = 50; // Moderate
      } else if (qty < 500) {
        qtyScore = 30; // High quantity
      } else {
        qtyScore = 10; // Extremely high quantity
      }
    }

    if (lots !== undefined && lots !== null) {
      if (lots < 5) {
        lotsScore = 90; // Few sellers = scarce
      } else if (lots < 15) {
        lotsScore = 70; // Moderate seller count
      } else if (lots < 30) {
        lotsScore = 50; // Many sellers
      } else if (lots < 50) {
        lotsScore = 30; // Very competitive
      } else {
        lotsScore = 10; // Oversaturated
      }
    }

    // Average the scores
    const score = (qtyScore + lotsScore) / 2;
    const tier = score >= 80
      ? "very_scarce"
      : score >= 60
      ? "moderately_scarce"
      : score >= 40
      ? "neutral"
      : "abundant";

    return { score, tier };
  }

  /**
   * Helper: Calculate months of inventory at current sales rate
   */
  private calculateMonthsOfInventory(
    availableQty?: number,
    salesVelocity?: number,
  ): number | null {
    if (
      availableQty === undefined || availableQty === null ||
      salesVelocity === undefined || salesVelocity === null
    ) {
      return null;
    }

    if (availableQty === 0) return 0; // Already out of stock
    if (salesVelocity === 0) return 999; // Not selling = infinite inventory

    // Sales velocity is in units/day
    const monthlyVelocity = salesVelocity * 30;

    if (monthlyVelocity === 0) return 999;

    const monthsOfInventory = availableQty / monthlyVelocity;

    // Cap at 999 to avoid infinity issues
    return Math.min(999, Math.round(monthsOfInventory * 10) / 10);
  }

  /**
   * Generate human-readable explanation
   */
  private generateExplanation(
    tier: string,
    months: number | null,
    score: number,
    multiplier: number,
  ): string {
    if (months !== null) {
      return `${tier.replace("_", " ")} (${months.toFixed(1)} months inventory, score: ${score.toFixed(0)}), ${multiplier.toFixed(2)}× multiplier`;
    } else {
      return `${tier.replace("_", " ")} (score: ${score.toFixed(0)} from qty/lots), ${multiplier.toFixed(2)}× multiplier`;
    }
  }
}
