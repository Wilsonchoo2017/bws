/**
 * LiquidityMultiplierCalculator - Extract liquidity multiplier logic
 *
 * EXTRACTED FROM:
 * - services/value-investing/ValueCalculator.ts (lines 114-194)
 *
 * SOLID Principles:
 * - Single Responsibility: Only calculates liquidity multipliers
 * - Open/Closed: Easy to adjust velocity thresholds
 *
 * Key Insight:
 * High liquidity = easier to sell = premium (up to 1.10×)
 * Low liquidity = harder to sell = discount (down to 0.60×)
 * Dead inventory gets strict penalties
 */

import { VALUE_INVESTING_CONFIG as CONFIG } from "../../value-investing/ValueInvestingConfig.ts";

/**
 * Liquidity multiplier input
 */
export interface LiquidityMultiplierInput {
  salesVelocity?: number; // Sales per day
  avgDaysBetweenSales?: number; // Average days between sales
}

/**
 * Liquidity multiplier calculation result
 */
export interface LiquidityMultiplierResult {
  /** Final multiplier (0.60-1.10 range) */
  multiplier: number;
  /** Liquidity score (0-100) */
  liquidityScore: number;
  /** Liquidity tier (dead, low, medium, high) */
  tier: string;
  /** Human-readable explanation */
  explanation: string;
}

/**
 * LiquidityMultiplierCalculator - Instance-based for testability
 */
export class LiquidityMultiplierCalculator {
  constructor(
    private config = CONFIG.INTRINSIC_VALUE.LIQUIDITY_MULTIPLIER,
  ) {}

  /**
   * Calculate liquidity multiplier
   *
   * Prefers sales velocity if available, falls back to avgDaysBetweenSales
   */
  calculate(input: LiquidityMultiplierInput): LiquidityMultiplierResult {
    const { salesVelocity, avgDaysBetweenSales } = input;

    // No data = use default (1.0 = no adjustment)
    if (
      (salesVelocity === undefined || salesVelocity === null) &&
      (avgDaysBetweenSales === undefined || avgDaysBetweenSales === null)
    ) {
      return {
        multiplier: this.config.DEFAULT,
        liquidityScore: 50,
        tier: "unknown",
        explanation: "No liquidity data available, using default multiplier (1.0×)",
      };
    }

    let liquidityScore = 50;
    let tier = "medium";
    let source = "unknown";

    // Prefer sales velocity if available
    if (
      salesVelocity !== undefined && salesVelocity !== null &&
      salesVelocity >= 0
    ) {
      const velocityResult = this.calculateFromVelocity(salesVelocity);
      liquidityScore = velocityResult.score;
      tier = velocityResult.tier;
      source = "velocity";
    } else if (
      avgDaysBetweenSales !== undefined && avgDaysBetweenSales !== null
    ) {
      const daysResult = this.calculateFromDaysBetween(avgDaysBetweenSales);
      liquidityScore = daysResult.score;
      tier = daysResult.tier;
      source = "days_between";
    }

    // Convert 0-100 score to multiplier range (0.60 - 1.10)
    const range = this.config.MAX - this.config.MIN;
    const multiplier = this.config.MIN + (liquidityScore / 100) * range;
    const clampedMultiplier = Math.max(
      this.config.MIN,
      Math.min(this.config.MAX, multiplier),
    );

    const explanation = this.generateExplanation(
      source,
      tier,
      salesVelocity,
      avgDaysBetweenSales,
      clampedMultiplier,
    );

    return {
      multiplier: clampedMultiplier,
      liquidityScore,
      tier,
      explanation,
    };
  }

  /**
   * Calculate liquidity score from sales velocity
   */
  private calculateFromVelocity(
    velocity: number,
  ): { score: number; tier: string } {
    if (velocity >= this.config.VELOCITY_HIGH) {
      return { score: 90, tier: "high" };
    } else if (velocity >= this.config.VELOCITY_MEDIUM) {
      const score = 65 +
        ((velocity - this.config.VELOCITY_MEDIUM) /
          (this.config.VELOCITY_HIGH - this.config.VELOCITY_MEDIUM)) * 25;
      return { score, tier: "medium-high" };
    } else if (velocity >= this.config.VELOCITY_LOW) {
      const score = 40 +
        ((velocity - this.config.VELOCITY_LOW) /
          (this.config.VELOCITY_MEDIUM - this.config.VELOCITY_LOW)) * 25;
      return { score, tier: "medium" };
    } else if (velocity >= this.config.VELOCITY_DEAD) {
      const score = 15 +
        ((velocity - this.config.VELOCITY_DEAD) /
          (this.config.VELOCITY_LOW - this.config.VELOCITY_DEAD)) * 25;
      return { score, tier: "low" };
    } else {
      const score = Math.max(0, (velocity / this.config.VELOCITY_DEAD) * 15);
      return { score, tier: "dead" };
    }
  }

  /**
   * Calculate liquidity score from days between sales (inverse relationship)
   */
  private calculateFromDaysBetween(
    days: number,
  ): { score: number; tier: string } {
    if (days <= this.config.DAYS_FAST) {
      return { score: 90, tier: "high" };
    } else if (days <= this.config.DAYS_MEDIUM) {
      const score = 65 +
        (1 - (days - this.config.DAYS_FAST) /
          (this.config.DAYS_MEDIUM - this.config.DAYS_FAST)) * 25;
      return { score, tier: "medium-high" };
    } else if (days <= this.config.DAYS_SLOW) {
      const score = 40 +
        (1 - (days - this.config.DAYS_MEDIUM) /
          (this.config.DAYS_SLOW - this.config.DAYS_MEDIUM)) * 25;
      return { score, tier: "medium" };
    } else if (days <= this.config.DAYS_VERY_SLOW) {
      const score = 15 +
        (1 - (days - this.config.DAYS_SLOW) /
          (this.config.DAYS_VERY_SLOW - this.config.DAYS_SLOW)) * 25;
      return { score, tier: "low" };
    } else {
      const score = Math.max(0, 15 * (this.config.DAYS_VERY_SLOW / days));
      return { score, tier: "very_slow" };
    }
  }

  /**
   * Generate human-readable explanation
   */
  private generateExplanation(
    source: string,
    tier: string,
    velocity?: number,
    days?: number,
    multiplier?: number,
  ): string {
    if (source === "velocity" && velocity !== undefined) {
      return `${tier} liquidity (${velocity.toFixed(3)} sales/day), ${multiplier?.toFixed(2)}× multiplier`;
    } else if (source === "days_between" && days !== undefined) {
      return `${tier} liquidity (${days.toFixed(0)} days between sales), ${multiplier?.toFixed(2)}× multiplier`;
    }
    return "Unknown liquidity source";
  }
}
