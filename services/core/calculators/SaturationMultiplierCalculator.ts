/**
 * SaturationMultiplierCalculator - Extract market saturation multiplier logic
 *
 * EXTRACTED FROM:
 * - services/value-investing/ValueCalculator.ts (lines 265-403)
 *
 * SOLID Principles:
 * - Single Responsibility: Only calculates saturation multipliers
 * - Open/Closed: Easy to adjust inventory thresholds
 *
 * Key Insight: MONTHS OF INVENTORY
 * How many months would it take to sell all available inventory?
 * - <1 month: Very scarce (1.05× premium)
 * - 1-3 months: Low inventory (1.0-1.05×)
 * - 3-12 months: Healthy (1.0×, neutral)
 * - 12-24 months: Oversupplied (0.50-1.0× discount)
 * - >24 months: Dead inventory (0.50× heavy discount)
 */

import { VALUE_INVESTING_CONFIG as CONFIG } from "../../value-investing/ValueInvestingConfig.ts";

/**
 * Saturation multiplier input
 */
export interface SaturationMultiplierInput {
  availableQty?: number; // Total units available for sale
  availableLots?: number; // Number of competing sellers
  salesVelocity?: number; // Sales per day
}

/**
 * Saturation multiplier calculation result
 */
export interface SaturationMultiplierResult {
  /** Final multiplier (0.50-1.05 range) */
  multiplier: number;
  /** Months of inventory (null if cannot calculate) */
  monthsOfInventory: number | null;
  /** Saturation tier (scarce, healthy, oversupplied, dead) */
  tier: string;
  /** Human-readable explanation */
  explanation: string;
}

/**
 * SaturationMultiplierCalculator - Instance-based for testability
 */
export class SaturationMultiplierCalculator {
  constructor(
    private config = CONFIG.INTRINSIC_VALUE.SATURATION_PENALTY,
  ) {}

  /**
   * Calculate market saturation multiplier
   *
   * Primary mode: Uses months of inventory (qty / velocity)
   * Fallback mode: Uses quantity + lots scoring
   */
  calculate(input: SaturationMultiplierInput): SaturationMultiplierResult {
    const { availableQty, availableLots, salesVelocity } = input;

    // No data = no penalty (benefit of doubt)
    if (
      (availableQty === undefined || availableQty === null) &&
      (availableLots === undefined || availableLots === null)
    ) {
      return {
        multiplier: this.config.MAX,
        monthsOfInventory: null,
        tier: "unknown",
        explanation: "No saturation data available, neutral multiplier (1.0×)",
      };
    }

    // Calculate months of inventory
    const monthsOfInventory = this.calculateMonthsOfInventory(
      availableQty,
      salesVelocity,
    );

    if (monthsOfInventory !== null) {
      // Primary mode: Months of inventory
      return this.calculateFromMonthsOfInventory(monthsOfInventory);
    } else {
      // Fallback mode: Quantity + lots scoring
      return this.calculateFromQuantityAndLots(availableQty, availableLots);
    }
  }

  /**
   * Calculate multiplier from months of inventory
   */
  private calculateFromMonthsOfInventory(
    months: number,
  ): SaturationMultiplierResult {
    let multiplier = 1.0;
    let tier = "healthy";
    let explanation = "";

    if (months > 24) {
      // Dead inventory: >24 months to sell through
      multiplier = 0.50;
      tier = "dead";
      explanation = `Dead inventory (${months.toFixed(1)} months to sell), 50% discount`;
    } else if (months > 12) {
      // Oversupplied: 12-24 months inventory
      const excessMonths = months - 12;
      const discountFactor = excessMonths / 12;
      multiplier = 1.0 - discountFactor * 0.50;
      tier = "oversupplied";
      explanation = `Oversupplied (${months.toFixed(1)} months inventory), ${((1 - multiplier) * 100).toFixed(0)}% discount`;
    } else if (months > 3) {
      // Healthy: 3-12 months inventory
      multiplier = 1.0;
      tier = "healthy";
      explanation = `Healthy inventory (${months.toFixed(1)} months), neutral`;
    } else if (months > 1) {
      // Low inventory: 1-3 months
      const scarcityFactor = (3 - months) / 2;
      multiplier = 1.0 + scarcityFactor * 0.05;
      tier = "low";
      explanation = `Low inventory (${months.toFixed(1)} months), ${((multiplier - 1) * 100).toFixed(0)}% scarcity premium`;
    } else {
      // Very scarce: <1 month inventory
      multiplier = 1.05;
      tier = "scarce";
      explanation = `Very scarce (<${months.toFixed(1)} month inventory), 5% premium`;
    }

    return {
      multiplier: Math.max(this.config.MIN, Math.min(this.config.MAX, multiplier)),
      monthsOfInventory: months,
      tier,
      explanation,
    };
  }

  /**
   * Fallback: Calculate multiplier from quantity and lots
   */
  private calculateFromQuantityAndLots(
    qty?: number,
    lots?: number,
  ): SaturationMultiplierResult {
    let saturationScore = 0; // 0 = healthy, 100 = saturated

    // Factor 1: Absolute quantity (40% weight)
    if (qty !== undefined && qty !== null && qty > 0) {
      if (qty >= this.config.QTY_EXTREME) {
        saturationScore += 40;
      } else if (qty >= this.config.QTY_HIGH) {
        saturationScore += 30 +
          ((qty - this.config.QTY_HIGH) /
            (this.config.QTY_EXTREME - this.config.QTY_HIGH)) * 10;
      } else if (qty >= this.config.QTY_MEDIUM) {
        saturationScore += 15 +
          ((qty - this.config.QTY_MEDIUM) /
            (this.config.QTY_HIGH - this.config.QTY_MEDIUM)) * 15;
      } else if (qty >= this.config.QTY_LOW) {
        saturationScore += ((qty - this.config.QTY_LOW) /
          (this.config.QTY_MEDIUM - this.config.QTY_LOW)) * 15;
      }
    }

    // Factor 2: Number of competing sellers (30% weight)
    if (lots !== undefined && lots !== null && lots > 0) {
      if (lots >= this.config.LOTS_EXTREME) {
        saturationScore += 30;
      } else if (lots >= this.config.LOTS_HIGH) {
        saturationScore += 22 +
          ((lots - this.config.LOTS_HIGH) /
            (this.config.LOTS_EXTREME - this.config.LOTS_HIGH)) * 8;
      } else if (lots >= this.config.LOTS_MEDIUM) {
        saturationScore += 12 +
          ((lots - this.config.LOTS_MEDIUM) /
            (this.config.LOTS_HIGH - this.config.LOTS_MEDIUM)) * 10;
      } else if (lots >= this.config.LOTS_LOW) {
        saturationScore += ((lots - this.config.LOTS_LOW) /
          (this.config.LOTS_MEDIUM - this.config.LOTS_LOW)) * 12;
      }
    }

    // Convert saturation score (0-100) to discount multiplier (0.50-1.0)
    const range = this.config.MAX - this.config.MIN;
    const multiplier = this.config.MAX - (saturationScore / 100) * range;

    const tier = saturationScore > 60 ? "oversupplied" : saturationScore > 30 ? "moderate" : "healthy";

    return {
      multiplier: Math.max(this.config.MIN, Math.min(this.config.MAX, multiplier)),
      monthsOfInventory: null,
      tier,
      explanation: `Saturation score ${saturationScore.toFixed(0)}/100 (qty: ${qty ?? "N/A"}, lots: ${lots ?? "N/A"}), ${((1 - multiplier) * 100).toFixed(0)}% discount`,
    };
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
}
