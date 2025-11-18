/**
 * VolatilityPenaltyCalculator - Extract volatility penalty logic
 *
 * EXTRACTED FROM:
 * - services/value-investing/ValueCalculator.ts (lines 196-263)
 *
 * SOLID Principles:
 * - Single Responsibility: Only calculates volatility penalties
 * - Open/Closed: Easy to adjust risk aversion coefficients
 *
 * Key Insight: CONTEXT-AWARE VOLATILITY
 * - Retired + Rising prices + High volatility = GOOD (collector frenzy)
 * - Retired + Falling prices + High volatility = BAD (panic selling)
 * - Active + High volatility = BAD (unstable pricing)
 */

import { VALUE_INVESTING_CONFIG as CONFIG } from "../../value-investing/ValueInvestingConfig.ts";

/**
 * Volatility penalty input
 */
export interface VolatilityPenaltyInput {
  priceVolatility?: number; // Coefficient of variation (std dev / mean)
  retirementStatus?: "active" | "retiring_soon" | "retired" | string;
  yearsPostRetirement?: number;
  priceTrend?: number; // Positive = rising, negative = falling
}

/**
 * Volatility penalty calculation result
 */
export interface VolatilityPenaltyResult {
  /** Final multiplier (0.85-1.0 range, 1.0 = no penalty) */
  multiplier: number;
  /** Context (retired_rising, retired_falling, active_volatile, etc.) */
  context: string;
  /** Was a penalty applied? */
  isPenalized: boolean;
  /** Human-readable explanation */
  explanation: string;
}

/**
 * VolatilityPenaltyCalculator - Instance-based for testability
 */
export class VolatilityPenaltyCalculator {
  constructor(
    private config = CONFIG.INTRINSIC_VALUE.VOLATILITY_DISCOUNT,
  ) {}

  /**
   * Calculate volatility penalty
   *
   * Context-aware: Interprets volatility based on retirement status and price trend
   */
  calculate(input: VolatilityPenaltyInput): VolatilityPenaltyResult {
    const {
      priceVolatility,
      retirementStatus,
      yearsPostRetirement,
      priceTrend,
    } = input;

    // No data or invalid = no penalty (benefit of doubt)
    if (
      priceVolatility === undefined ||
      priceVolatility === null ||
      priceVolatility < 0
    ) {
      return {
        multiplier: 1.0,
        context: "no_data",
        isPenalized: false,
        explanation: "No volatility data available, no penalty applied",
      };
    }

    // CONTEXT-AWARE LOGIC for retired sets
    const isRetired = retirementStatus === "retired";
    const isMatured = yearsPostRetirement !== undefined &&
      yearsPostRetirement >= 2;

    if (isRetired && isMatured) {
      // For mature retired sets, interpret volatility in context of price direction

      if (priceTrend !== undefined && priceTrend > 0) {
        // RISING PRICES + HIGH VOLATILITY = Collector demand / appreciation phase
        // This is GOOD volatility - don't penalize
        return {
          multiplier: 1.0,
          context: "retired_rising",
          isPenalized: false,
          explanation: `Retired set with rising prices (trend: ${priceTrend.toFixed(2)}), volatility ${(priceVolatility * 100).toFixed(0)}% indicates collector demand (no penalty)`,
        };
      } else if (priceTrend !== undefined && priceTrend < 0) {
        // FALLING PRICES + HIGH VOLATILITY = Sellers panicking / market dump
        // This is BAD volatility - heavy penalty
        if (priceVolatility > 0.30) {
          return {
            multiplier: 0.85,
            context: "retired_falling",
            isPenalized: true,
            explanation: `Retired set with falling prices (trend: ${priceTrend.toFixed(2)}) and high volatility ${(priceVolatility * 100).toFixed(0)}% indicates panic selling (15% penalty)`,
          };
        } else {
          return {
            multiplier: 0.95,
            context: "retired_falling",
            isPenalized: true,
            explanation: `Retired set with falling prices but moderate volatility ${(priceVolatility * 100).toFixed(0)}% (5% penalty)`,
          };
        }
      }
    }

    // DEFAULT: For active sets or when no trend data, use risk-adjusted formula
    // High volatility in active/new sets = unstable pricing = risk
    const discount = Math.min(
      priceVolatility * this.config.RISK_AVERSION_COEFFICIENT,
      this.config.MAX_DISCOUNT,
    );

    const multiplier = 1.0 - discount;

    return {
      multiplier,
      context: "active_volatile",
      isPenalized: discount > 0,
      explanation: `${retirementStatus || "active"} set with ${(priceVolatility * 100).toFixed(0)}% volatility (${(discount * 100).toFixed(0)}% risk penalty)`,
    };
  }

  /**
   * Check if volatility is high (> 30%)
   */
  isHighVolatility(volatility: number): boolean {
    return volatility > 0.30;
  }

  /**
   * Get maximum possible discount
   */
  getMaxDiscount(): number {
    return this.config.MAX_DISCOUNT;
  }
}
