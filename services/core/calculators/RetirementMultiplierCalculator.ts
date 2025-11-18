/**
 * RetirementMultiplierCalculator - Extract retirement multiplier logic
 *
 * EXTRACTED FROM:
 * - services/value-investing/ValueCalculator.ts (lines 528-581)
 *
 * SOLID Principles:
 * - Single Responsibility: Only calculates retirement multipliers
 * - Open/Closed: Easy to adjust J-curve parameters
 *
 * Key Feature: DEMAND GATING
 * Retirement premium only applies with sufficient demand.
 * Being retired doesn't matter if nobody wants it!
 */

import { VALUE_INVESTING_CONFIG as CONFIG } from "../../value-investing/ValueInvestingConfig.ts";

/**
 * Retirement multiplier input
 */
export interface RetirementMultiplierInput {
  retirementStatus?: "active" | "retiring_soon" | "retired" | string;
  yearsPostRetirement?: number;
  demandScore?: number;
}

/**
 * Retirement multiplier calculation result
 */
export interface RetirementMultiplierResult {
  /** Final multiplier (0.95-2.0 range) */
  multiplier: number;
  /** Retirement phase (active, retiring_soon, retired_0-1, etc.) */
  phase: string;
  /** Was premium gated by low demand? */
  demandGated: boolean;
  /** Human-readable explanation */
  explanation: string;
}

/**
 * RetirementMultiplierCalculator - Instance-based for testability
 */
export class RetirementMultiplierCalculator {
  constructor(
    private config = CONFIG.INTRINSIC_VALUE,
  ) {}

  /**
   * Calculate time-decayed retirement multiplier
   *
   * Implements REALISTIC J-CURVE:
   * - Year 0-1: Market flooded (-5%)
   * - Year 1-2: Stabilization (0%)
   * - Year 2-5: Early appreciation (+15%)
   * - Year 5-10: Scarcity premium (+40%)
   * - Year 10+: Vintage status (+100%)
   *
   * CRITICAL: Demand-gated - premium only with real demand
   */
  calculate(input: RetirementMultiplierInput): RetirementMultiplierResult {
    const { retirementStatus, yearsPostRetirement, demandScore } = input;

    // Active or retiring soon - simple multipliers
    if (retirementStatus === "retiring_soon") {
      return {
        multiplier: this.config.RETIREMENT_MULTIPLIERS.RETIRING_SOON,
        phase: "retiring_soon",
        demandGated: false,
        explanation: `Retiring soon (${this.config.RETIREMENT_MULTIPLIERS.RETIRING_SOON}× multiplier)`,
      };
    }

    if (retirementStatus !== "retired") {
      return {
        multiplier: this.config.RETIREMENT_MULTIPLIERS.ACTIVE,
        phase: "active",
        demandGated: false,
        explanation: `Active production (${this.config.RETIREMENT_MULTIPLIERS.ACTIVE}× multiplier)`,
      };
    }

    // RETIRED STATUS - Apply demand gating
    const hasSufficientDemand = demandScore !== undefined &&
      demandScore !== null &&
      demandScore >= this.config.RETIREMENT_TIME_DECAY.MIN_DEMAND_FOR_PREMIUM;

    if (!hasSufficientDemand) {
      return {
        multiplier: this.config.RETIREMENT_TIME_DECAY.LOW_DEMAND_MAX_PREMIUM,
        phase: "retired_low_demand",
        demandGated: true,
        explanation: `Retired but low demand (score: ${demandScore ?? "N/A"}), capped at ${this.config.RETIREMENT_TIME_DECAY.LOW_DEMAND_MAX_PREMIUM}×`,
      };
    }

    // Sufficient demand: Apply REALISTIC J-CURVE
    if (
      yearsPostRetirement !== undefined &&
      yearsPostRetirement !== null &&
      yearsPostRetirement >= 0
    ) {
      if (yearsPostRetirement < 1) {
        return {
          multiplier: this.config.RETIREMENT_TIME_DECAY.YEAR_0_1,
          phase: "retired_0-1_years",
          demandGated: false,
          explanation: `Recently retired (0-1 years), market flooded (${this.config.RETIREMENT_TIME_DECAY.YEAR_0_1}×)`,
        };
      } else if (yearsPostRetirement < 2) {
        return {
          multiplier: this.config.RETIREMENT_TIME_DECAY.YEAR_1_2,
          phase: "retired_1-2_years",
          demandGated: false,
          explanation: `Stabilization phase (1-2 years), baseline (${this.config.RETIREMENT_TIME_DECAY.YEAR_1_2}×)`,
        };
      } else if (yearsPostRetirement < 5) {
        return {
          multiplier: this.config.RETIREMENT_TIME_DECAY.YEAR_2_5,
          phase: "retired_2-5_years",
          demandGated: false,
          explanation: `Early appreciation (2-5 years), ${this.config.RETIREMENT_TIME_DECAY.YEAR_2_5}× multiplier`,
        };
      } else if (yearsPostRetirement < 10) {
        return {
          multiplier: this.config.RETIREMENT_TIME_DECAY.YEAR_5_10,
          phase: "retired_5-10_years",
          demandGated: false,
          explanation: `Scarcity premium (5-10 years), ${this.config.RETIREMENT_TIME_DECAY.YEAR_5_10}× multiplier`,
        };
      } else {
        return {
          multiplier: this.config.RETIREMENT_TIME_DECAY.YEAR_10_PLUS,
          phase: "retired_10+_years",
          demandGated: false,
          explanation: `Vintage status (10+ years), ${this.config.RETIREMENT_TIME_DECAY.YEAR_10_PLUS}× multiplier`,
        };
      }
    }

    // No time data - use conservative baseline
    return {
      multiplier: this.config.RETIREMENT_MULTIPLIERS.RETIRED,
      phase: "retired_unknown_age",
      demandGated: false,
      explanation: `Retired (age unknown), conservative baseline (${this.config.RETIREMENT_MULTIPLIERS.RETIRED}×)`,
    };
  }

  /**
   * Get demand threshold for premium
   */
  getDemandThreshold(): number {
    return this.config.RETIREMENT_TIME_DECAY.MIN_DEMAND_FOR_PREMIUM;
  }

  /**
   * Get all J-curve multipliers
   */
  getJCurveMultipliers(): Record<string, number> {
    return {
      year_0_1: this.config.RETIREMENT_TIME_DECAY.YEAR_0_1,
      year_1_2: this.config.RETIREMENT_TIME_DECAY.YEAR_1_2,
      year_2_5: this.config.RETIREMENT_TIME_DECAY.YEAR_2_5,
      year_5_10: this.config.RETIREMENT_TIME_DECAY.YEAR_5_10,
      year_10_plus: this.config.RETIREMENT_TIME_DECAY.YEAR_10_PLUS,
    };
  }
}
