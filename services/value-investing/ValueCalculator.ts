import type {
  IntrinsicValueInputs,
  ValueMetrics,
} from "../../types/value-investing.ts";
import {
  getValueRatingConfig,
  VALUE_INVESTING_CONFIG as CONFIG,
} from "./ValueInvestingConfig.ts";

/**
 * ValueCalculator implements value investing principles inspired by
 * Warren Buffett and Mohnish Pabrai - finding quality assets trading
 * below their intrinsic value.
 *
 * REFACTORED with:
 * - Input validation for resilience
 * - Centralized configuration
 * - Defensive programming against NaN/null/undefined
 */
export class ValueCalculator {
  /**
   * Validate score inputs (demandScore, qualityScore)
   * @throws {Error} if score is out of valid range
   */
  private static validateScore(
    score: number | undefined,
    fieldName: string,
  ): void {
    if (score === undefined) return; // Optional field

    if (
      typeof score !== "number" ||
      isNaN(score) ||
      score < CONFIG.VALIDATION.SCORE_MIN ||
      score > CONFIG.VALIDATION.SCORE_MAX
    ) {
      throw new Error(
        `${fieldName} must be a number between ${CONFIG.VALIDATION.SCORE_MIN} and ${CONFIG.VALIDATION.SCORE_MAX}, got: ${score}`,
      );
    }
  }

  /**
   * Validate price inputs
   * @throws {Error} if price is invalid
   */
  private static validatePrice(
    price: number | undefined,
    fieldName: string,
  ): void {
    if (price === undefined) return; // Optional field

    if (
      typeof price !== "number" ||
      isNaN(price) ||
      price < CONFIG.VALIDATION.PRICE_MIN
    ) {
      throw new Error(
        `${fieldName} must be a non-negative number, got: ${price}`,
      );
    }
  }

  /**
   * Safely clamp a score to valid range with default
   */
  private static safeScore(
    score: number | undefined,
    defaultValue: number,
  ): number {
    if (score === undefined || score === null || isNaN(score)) {
      return defaultValue;
    }
    return Math.max(
      CONFIG.VALIDATION.SCORE_MIN,
      Math.min(CONFIG.VALIDATION.SCORE_MAX, score),
    );
  }

  /**
   * Calculate intrinsic value using multiple approaches:
   * 1. Resale value (Bricklink data) - what can you sell it for?
   * 2. Quality adjustments (retirement status, demand)
   * 3. Conservative discounting for margin of safety
   */
  static calculateIntrinsicValue(inputs: IntrinsicValueInputs): number {
    // Validate inputs
    this.validatePrice(inputs.bricklinkAvgPrice, "bricklinkAvgPrice");
    this.validatePrice(inputs.bricklinkMaxPrice, "bricklinkMaxPrice");
    this.validateScore(inputs.demandScore, "demandScore");
    this.validateScore(inputs.qualityScore, "qualityScore");

    const {
      bricklinkAvgPrice,
      bricklinkMaxPrice,
      retirementStatus,
    } = inputs;

    // Safe scores with defaults and clamping
    const demandScore = this.safeScore(
      inputs.demandScore,
      CONFIG.INTRINSIC_VALUE.DEMAND_MULTIPLIER.DEFAULT_SCORE,
    );
    const qualityScore = this.safeScore(
      inputs.qualityScore,
      CONFIG.INTRINSIC_VALUE.QUALITY_MULTIPLIER.DEFAULT_SCORE,
    );

    // Base value: conservative estimate of resale potential
    let baseValue = 0;

    if (bricklinkAvgPrice && bricklinkMaxPrice) {
      // Use weighted average favoring average over max (conservative)
      baseValue = bricklinkAvgPrice *
          CONFIG.INTRINSIC_VALUE.BASE_WEIGHTS.AVG_PRICE +
        bricklinkMaxPrice * CONFIG.INTRINSIC_VALUE.BASE_WEIGHTS.MAX_PRICE;
    } else if (bricklinkAvgPrice) {
      baseValue = bricklinkAvgPrice;
    } else if (bricklinkMaxPrice) {
      // Very conservative if we only have max
      baseValue = bricklinkMaxPrice *
        CONFIG.INTRINSIC_VALUE.BASE_WEIGHTS.MAX_ONLY_DISCOUNT;
    } else {
      // No resale data - cannot calculate intrinsic value
      return 0;
    }

    // Retirement status multiplier (retired sets appreciate)
    let retirementMultiplier =
      CONFIG.INTRINSIC_VALUE.RETIREMENT_MULTIPLIERS.ACTIVE;
    if (retirementStatus === "retired") {
      retirementMultiplier =
        CONFIG.INTRINSIC_VALUE.RETIREMENT_MULTIPLIERS.RETIRED;
    } else if (retirementStatus === "retiring_soon") {
      retirementMultiplier =
        CONFIG.INTRINSIC_VALUE.RETIREMENT_MULTIPLIERS.RETIRING_SOON;
    }

    // Quality adjustment (0-100 score -> 0.9-1.1 multiplier)
    const qualityRange = CONFIG.INTRINSIC_VALUE.QUALITY_MULTIPLIER.MAX -
      CONFIG.INTRINSIC_VALUE.QUALITY_MULTIPLIER.MIN;
    const qualityMultiplier = CONFIG.INTRINSIC_VALUE.QUALITY_MULTIPLIER.MIN +
      (qualityScore / 100) * qualityRange;

    // Demand adjustment (0-100 score -> 0.85-1.15 multiplier)
    const demandRange = CONFIG.INTRINSIC_VALUE.DEMAND_MULTIPLIER.MAX -
      CONFIG.INTRINSIC_VALUE.DEMAND_MULTIPLIER.MIN;
    const demandMultiplier = CONFIG.INTRINSIC_VALUE.DEMAND_MULTIPLIER.MIN +
      (demandScore / 100) * demandRange;

    const intrinsicValue = baseValue * retirementMultiplier *
      qualityMultiplier * demandMultiplier;

    // Guard against NaN or negative values
    if (isNaN(intrinsicValue) || intrinsicValue < 0) {
      console.warn(
        "[ValueCalculator] Calculated invalid intrinsic value:",
        { intrinsicValue, inputs },
      );
      return 0;
    }

    return Math.round(intrinsicValue * Math.pow(10, CONFIG.PRECISION.PRICE)) /
      Math.pow(10, CONFIG.PRECISION.PRICE);
  }

  /**
   * Calculate target buy price (price at which you should buy)
   * Using margin of safety principle - buy at a discount to intrinsic value
   */
  static calculateTargetPrice(
    intrinsicValue: number,
    desiredMarginOfSafety: number = CONFIG.MARGIN_OF_SAFETY.DEFAULT,
  ): number {
    // Validate inputs
    if (
      typeof intrinsicValue !== "number" || isNaN(intrinsicValue) ||
      intrinsicValue <= 0
    ) {
      return 0;
    }

    if (
      typeof desiredMarginOfSafety !== "number" ||
      isNaN(desiredMarginOfSafety) ||
      desiredMarginOfSafety < 0 ||
      desiredMarginOfSafety >= 1
    ) {
      console.warn(
        "[ValueCalculator] Invalid margin of safety, using default:",
        desiredMarginOfSafety,
      );
      desiredMarginOfSafety = CONFIG.MARGIN_OF_SAFETY.DEFAULT;
    }

    const targetPrice = intrinsicValue * (1 - desiredMarginOfSafety);
    return Math.round(targetPrice * Math.pow(10, CONFIG.PRECISION.PRICE)) /
      Math.pow(10, CONFIG.PRECISION.PRICE);
  }

  /**
   * Calculate margin of safety percentage
   * Positive = buying below intrinsic value (good!)
   * Negative = paying above intrinsic value (bad!)
   */
  static calculateMarginOfSafety(
    currentPrice: number,
    intrinsicValue: number,
  ): number {
    // Validate inputs
    if (
      typeof currentPrice !== "number" || isNaN(currentPrice) ||
      currentPrice <= 0
    ) {
      return 0;
    }

    if (
      typeof intrinsicValue !== "number" || isNaN(intrinsicValue) ||
      intrinsicValue <= 0
    ) {
      return 0;
    }

    const margin = ((intrinsicValue - currentPrice) / intrinsicValue) * 100;

    // Guard against extreme values
    if (isNaN(margin) || !isFinite(margin)) {
      return 0;
    }

    return Math.round(margin * Math.pow(10, CONFIG.PRECISION.PERCENTAGE)) /
      Math.pow(10, CONFIG.PRECISION.PERCENTAGE);
  }

  /**
   * Calculate expected ROI based on buying at current price
   * and selling at intrinsic value
   */
  static calculateExpectedROI(
    currentPrice: number,
    intrinsicValue: number,
  ): number {
    // Validate inputs
    if (
      typeof currentPrice !== "number" || isNaN(currentPrice) ||
      currentPrice <= 0
    ) {
      return 0;
    }

    if (
      typeof intrinsicValue !== "number" || isNaN(intrinsicValue) ||
      intrinsicValue <= 0
    ) {
      return 0;
    }

    const roi = ((intrinsicValue - currentPrice) / currentPrice) * 100;

    // Guard against extreme values
    if (isNaN(roi) || !isFinite(roi)) {
      return 0;
    }

    return Math.round(roi * Math.pow(10, CONFIG.PRECISION.PERCENTAGE)) /
      Math.pow(10, CONFIG.PRECISION.PERCENTAGE);
  }

  /**
   * Estimate time horizon based on retirement status and market conditions
   */
  static estimateTimeHorizon(
    retirementStatus?: string,
    urgency?: string,
  ): string {
    // Quick flips for urgent opportunities
    if (urgency === "urgent") return CONFIG.TIME_HORIZONS.URGENT;

    // Retirement-based estimates
    if (retirementStatus === "retired") return CONFIG.TIME_HORIZONS.RETIRED;
    if (retirementStatus === "retiring_soon") {
      return CONFIG.TIME_HORIZONS.RETIRING_SOON;
    }

    // Active sets - longer hold
    return CONFIG.TIME_HORIZONS.ACTIVE;
  }

  /**
   * Calculate complete value metrics for a product
   */
  static calculateValueMetrics(
    currentPrice: number,
    inputs: IntrinsicValueInputs,
    urgency?: string,
  ): ValueMetrics {
    // Validate current price
    this.validatePrice(currentPrice, "currentPrice");

    const intrinsicValue = this.calculateIntrinsicValue(inputs);
    const targetPrice = this.calculateTargetPrice(intrinsicValue);
    const marginOfSafety = this.calculateMarginOfSafety(
      currentPrice,
      intrinsicValue,
    );
    const expectedROI = this.calculateExpectedROI(currentPrice, intrinsicValue);
    const timeHorizon = this.estimateTimeHorizon(
      inputs.retirementStatus,
      urgency,
    );

    return {
      currentPrice,
      targetPrice,
      intrinsicValue,
      marginOfSafety,
      expectedROI,
      timeHorizon,
    };
  }

  /**
   * Determine if a product is a good buy based on value investing principles
   */
  static isGoodBuy(
    marginOfSafety: number,
    minMarginOfSafety: number = CONFIG.MARGIN_OF_SAFETY.MINIMUM * 100,
  ): boolean {
    return marginOfSafety >= minMarginOfSafety;
  }

  /**
   * Get value investing rating
   */
  static getValueRating(marginOfSafety: number): {
    rating: string;
    color: string;
  } {
    const config = getValueRatingConfig(marginOfSafety);
    return {
      rating: config.rating,
      color: config.color,
    };
  }
}
