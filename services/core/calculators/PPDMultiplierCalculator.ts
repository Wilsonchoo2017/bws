/**
 * PPDMultiplierCalculator - Extract Parts-Per-Dollar multiplier logic
 *
 * EXTRACTED FROM:
 * - services/value-investing/ValueCalculator.ts (lines 730-756)
 *
 * SOLID Principles:
 * - Single Responsibility: Only calculates PPD multipliers
 * - Open/Closed: Easy to adjust PPD thresholds
 *
 * Key Insight: Parts-Per-Dollar measures brick value quality
 * Higher PPD = better value per dollar spent
 * - Excellent (≥10 PPD): Premium sets, 1.10× multiplier
 * - Good (8-10 PPD): Solid value, 1.05× multiplier
 * - Fair (6-8 PPD): Average, 1.0× multiplier
 * - Poor (<6 PPD): Overpriced, 0.95× penalty
 */

import { VALUE_INVESTING_CONFIG as CONFIG } from "../../value-investing/ValueInvestingConfig.ts";
import type { Cents } from "../../../types/price.ts";

/**
 * PPD multiplier input
 */
export interface PPDMultiplierInput {
  partsCount?: number; // Number of pieces in the set
  msrp?: Cents; // Original retail price in cents
}

/**
 * PPD multiplier calculation result
 */
export interface PPDMultiplierResult {
  /** Final multiplier (0.95-1.10 range) */
  multiplier: number;
  /** Parts per dollar ratio */
  ppd: number | null;
  /** PPD tier (excellent, good, fair, poor) */
  tier: string;
  /** Human-readable explanation */
  explanation: string;
}

/**
 * PPDMultiplierCalculator - Instance-based for testability
 */
export class PPDMultiplierCalculator {
  constructor(
    private config = CONFIG.INTRINSIC_VALUE.PARTS_PER_DOLLAR,
  ) {}

  /**
   * Calculate Parts-Per-Dollar multiplier
   *
   * PPD = partsCount / (msrp in dollars)
   */
  calculate(input: PPDMultiplierInput): PPDMultiplierResult {
    const { partsCount, msrp } = input;

    // No data = neutral (1.0)
    if (!partsCount || !msrp || msrp <= 0) {
      return {
        multiplier: 1.0,
        ppd: null,
        tier: "unknown",
        explanation: "No PPD data available, neutral multiplier (1.0×)",
      };
    }

    // Convert cents to dollars for PPD calculation
    const msrpDollars = msrp / 100;
    const ppd = partsCount / msrpDollars;

    // Determine tier and multiplier
    let multiplier: number;
    let tier: string;

    if (ppd >= this.config.EXCELLENT) {
      multiplier = 1.10;
      tier = "excellent";
    } else if (ppd >= this.config.GOOD) {
      multiplier = 1.05;
      tier = "good";
    } else if (ppd >= this.config.FAIR) {
      multiplier = 1.00;
      tier = "fair";
    } else {
      multiplier = 0.95;
      tier = "poor";
    }

    const explanation = `${tier.toUpperCase()} PPD (${ppd.toFixed(1)} parts/$), ${multiplier.toFixed(2)}× multiplier`;

    return {
      multiplier,
      ppd,
      tier,
      explanation,
    };
  }

  /**
   * Get PPD thresholds
   */
  getThresholds() {
    return {
      excellent: this.config.EXCELLENT,
      good: this.config.GOOD,
      fair: this.config.FAIR,
      poor: this.config.POOR,
    };
  }

  /**
   * Check if PPD is good value (>= 8 PPD)
   */
  isGoodValue(ppd: number): boolean {
    return ppd >= this.config.GOOD;
  }
}
