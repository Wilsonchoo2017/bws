import type {
  IntrinsicValueInputs,
  ValueMetricsInDollars,
} from "../../types/value-investing.ts";
import {
  getValueRatingConfig,
  VALUE_INVESTING_CONFIG as CONFIG,
} from "./ValueInvestingConfig.ts";
import type { Cents } from "../../types/price.ts";

// Strategy-specific margin of safety configurations
export const STRATEGY_MARGINS = {
  "Investment Focus": { margin: 0.25, description: "Conservative long-term" },
  "Quick Flip": { margin: 0.10, description: "Aggressive near-market" },
  "Bargain Hunter": { margin: 0.35, description: "Very conservative" },
} as const;

export type StrategyType = keyof typeof STRATEGY_MARGINS;

/**
 * ValueCalculator implements value investing principles inspired by
 * Warren Buffett and Mohnish Pabrai - finding quality assets trading
 * below their intrinsic value.
 *
 * REFACTORED with:
 * - Input validation for resilience
 * - Centralized configuration
 * - Defensive programming against NaN/null/undefined
 *
 * ⚠️ IMPORTANT PRICE UNIT CONVENTION:
 * This calculator works EXCLUSIVELY in CENTS (integer currency unit) for all calculations.
 * All input prices must be in CENTS, and all output prices are in CENTS.
 *
 * When interfacing with this calculator:
 * - FROM database (cents) → pass directly to calculator
 * - TO API (cents) → return directly (no conversion needed)
 * - Display layer → convert from cents to dollars for formatting only
 *
 * This design choice:
 * ✓ Eliminates floating point precision errors entirely
 * ✓ Matches database storage (cents as integers)
 * ✓ All calculations use integer math with rounding
 * ✓ Percentages applied as: (cents * percent) / 100
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
   * Calculate liquidity multiplier based on sales velocity and days between sales
   * High liquidity = easier to sell = premium (up to 1.10x)
   * Low liquidity = harder to sell = discount (down to 0.60x)
   * ENHANCED: Stricter penalties for dead/very slow inventory
   */
  private static calculateLiquidityMultiplier(
    salesVelocity?: number,
    avgDaysBetweenSales?: number,
  ): number {
    const config = CONFIG.INTRINSIC_VALUE.LIQUIDITY_MULTIPLIER;

    // No data = use default (1.0 = no adjustment)
    if (
      (salesVelocity === undefined || salesVelocity === null) &&
      (avgDaysBetweenSales === undefined || avgDaysBetweenSales === null)
    ) {
      return config.DEFAULT;
    }

    // Prefer sales velocity if available, otherwise use days between sales
    let liquidityScore = 50; // Default to neutral

    if (
      salesVelocity !== undefined && salesVelocity !== null && salesVelocity >= 0
    ) {
      // Map sales velocity to 0-100 score with enhanced tiers
      if (salesVelocity >= config.VELOCITY_HIGH) {
        liquidityScore = 90; // Very high liquidity
      } else if (salesVelocity >= config.VELOCITY_MEDIUM) {
        // Linear interpolation between medium and high
        liquidityScore = 65 + ((salesVelocity - config.VELOCITY_MEDIUM) /
              (config.VELOCITY_HIGH - config.VELOCITY_MEDIUM)) * 25;
      } else if (salesVelocity >= config.VELOCITY_LOW) {
        // Linear interpolation between low and medium
        liquidityScore = 40 + ((salesVelocity - config.VELOCITY_LOW) /
              (config.VELOCITY_MEDIUM - config.VELOCITY_LOW)) * 25;
      } else if (salesVelocity >= config.VELOCITY_DEAD) {
        // Linear interpolation between dead and low
        liquidityScore = 15 + ((salesVelocity - config.VELOCITY_DEAD) /
              (config.VELOCITY_LOW - config.VELOCITY_DEAD)) * 25;
      } else {
        // Dead inventory (< 0.01 sales/day = < 1 sale per 100 days)
        liquidityScore = Math.max(0, (salesVelocity / config.VELOCITY_DEAD) * 15);
      }
    } else if (
      avgDaysBetweenSales !== undefined && avgDaysBetweenSales !== null
    ) {
      // Map days between sales to 0-100 score (inverse relationship)
      if (avgDaysBetweenSales <= config.DAYS_FAST) {
        liquidityScore = 90; // Very high liquidity
      } else if (avgDaysBetweenSales <= config.DAYS_MEDIUM) {
        // Linear interpolation between fast and medium
        liquidityScore = 65 + (1 - (avgDaysBetweenSales - config.DAYS_FAST) /
                (config.DAYS_MEDIUM - config.DAYS_FAST)) * 25;
      } else if (avgDaysBetweenSales <= config.DAYS_SLOW) {
        // Linear interpolation between medium and slow
        liquidityScore = 40 + (1 - (avgDaysBetweenSales - config.DAYS_MEDIUM) /
                (config.DAYS_SLOW - config.DAYS_MEDIUM)) * 25;
      } else if (avgDaysBetweenSales <= config.DAYS_VERY_SLOW) {
        // Linear interpolation between slow and very slow
        liquidityScore = 15 + (1 - (avgDaysBetweenSales - config.DAYS_SLOW) /
                (config.DAYS_VERY_SLOW - config.DAYS_SLOW)) * 25;
      } else {
        // Very slow (> 180 days between sales)
        liquidityScore = Math.max(
          0,
          15 * (config.DAYS_VERY_SLOW / avgDaysBetweenSales),
        );
      }
    }

    // Convert 0-100 score to multiplier range (0.60 - 1.10)
    const range = config.MAX - config.MIN;
    const multiplier = config.MIN + (liquidityScore / 100) * range;

    return Math.max(config.MIN, Math.min(config.MAX, multiplier));
  }

  /**
   * Calculate volatility discount based on price coefficient of variation
   * High volatility = higher risk = discount
   * Stable pricing = low risk = minimal discount
   */
  private static calculateVolatilityDiscount(
    priceVolatility?: number,
  ): number {
    const config = CONFIG.INTRINSIC_VALUE.VOLATILITY_DISCOUNT;

    // No data = no discount (benefit of doubt)
    if (
      priceVolatility === undefined || priceVolatility === null ||
      priceVolatility < 0
    ) {
      return 1.0;
    }

    // Apply risk-adjusted discount
    // discount = volatility × risk_aversion_coefficient
    // Capped at MAX_DISCOUNT (12%)
    const discount = Math.min(
      priceVolatility * config.RISK_AVERSION_COEFFICIENT,
      config.MAX_DISCOUNT,
    );

    return 1.0 - discount;
  }

  /**
   * Calculate market saturation discount
   * High supply + low sales = oversaturated market = discount
   * ENHANCED: More aggressive penalties for extreme oversaturation
   * CRITICAL: Prevents overvaluing sets with no real buyers
   */
  private static calculateSaturationDiscount(
    availableQty?: number,
    availableLots?: number,
    salesVelocity?: number,
  ): number {
    const config = CONFIG.INTRINSIC_VALUE.SATURATION_PENALTY;

    // No data = no penalty (benefit of doubt)
    if (
      (availableQty === undefined || availableQty === null) &&
      (availableLots === undefined || availableLots === null)
    ) {
      return config.MAX;
    }

    let saturationScore = 0; // 0 = healthy, 100 = saturated

    // Factor 1: Quantity available (30% weight, reduced from 40%)
    if (
      availableQty !== undefined && availableQty !== null && availableQty > 0
    ) {
      if (availableQty >= config.QTY_EXTREME) {
        saturationScore += 30; // Extreme oversupply
      } else if (availableQty >= config.QTY_HIGH) {
        // Linear interpolation between high and extreme
        saturationScore += 22 + ((availableQty - config.QTY_HIGH) /
              (config.QTY_EXTREME - config.QTY_HIGH)) * 8;
      } else if (availableQty >= config.QTY_MEDIUM) {
        // Linear interpolation between medium and high
        saturationScore += 12 + ((availableQty - config.QTY_MEDIUM) /
              (config.QTY_HIGH - config.QTY_MEDIUM)) * 10;
      } else if (availableQty >= config.QTY_LOW) {
        // Linear interpolation between low and medium
        saturationScore += ((availableQty - config.QTY_LOW) /
          (config.QTY_MEDIUM - config.QTY_LOW)) * 12;
      }
      // else: healthy supply, no points
    }

    // Factor 2: Number of competing sellers (20% weight, reduced from 30%)
    if (
      availableLots !== undefined && availableLots !== null && availableLots > 0
    ) {
      if (availableLots >= config.LOTS_EXTREME) {
        saturationScore += 20; // Extreme seller count
      } else if (availableLots >= config.LOTS_HIGH) {
        // Linear interpolation between high and extreme
        saturationScore += 15 + ((availableLots - config.LOTS_HIGH) /
              (config.LOTS_EXTREME - config.LOTS_HIGH)) * 5;
      } else if (availableLots >= config.LOTS_MEDIUM) {
        saturationScore += 8 + ((availableLots - config.LOTS_MEDIUM) /
              (config.LOTS_HIGH - config.LOTS_MEDIUM)) * 7;
      } else if (availableLots >= config.LOTS_LOW) {
        saturationScore += ((availableLots - config.LOTS_LOW) /
          (config.LOTS_MEDIUM - config.LOTS_LOW)) * 8;
      }
    }

    // Factor 3: Velocity-to-supply ratio (50% weight, increased from 30%)
    // This is the MOST IMPORTANT indicator of dead inventory
    if (
      salesVelocity !== undefined && salesVelocity !== null &&
      availableQty !== undefined && availableQty !== null &&
      availableQty > 0
    ) {
      const velocityRatio = salesVelocity / availableQty;

      if (velocityRatio <= config.POOR_RATIO) {
        saturationScore += 50; // Inventory not moving AT ALL
      } else if (velocityRatio < config.HEALTHY_RATIO) {
        // Linear interpolation
        saturationScore += 50 * (1 - (velocityRatio - config.POOR_RATIO) /
            (config.HEALTHY_RATIO - config.POOR_RATIO));
      }
      // else: healthy turnover, no points
    }

    // Convert saturation score (0-100) to discount multiplier (0.50-1.0)
    const range = config.MAX - config.MIN;
    const discount = config.MAX - (saturationScore / 100) * range;

    return Math.max(config.MIN, Math.min(config.MAX, discount));
  }

  /**
   * Calculate zero sales penalty
   * CRITICAL: Items with ZERO sales get heavily penalized
   * This prevents overvaluing dead inventory that nobody is buying
   *
   * Returns a severe discount multiplier (0.50x default) when:
   * - Item has zero sales in the observation period
   * - Observation period is long enough (90+ days)
   * - Optionally compounds with low demand score
   */
  private static calculateZeroSalesPenalty(
    timesSold?: number,
    demandScore?: number,
  ): number {
    const config = CONFIG.INTRINSIC_VALUE.ZERO_SALES_PENALTY;

    // No data = no penalty (benefit of doubt)
    if (timesSold === undefined || timesSold === null) {
      return 1.0;
    }

    // Has sales = no penalty
    if (timesSold >= config.MIN_SALES_THRESHOLD) {
      return 1.0;
    }

    // ZERO SALES DETECTED - apply base penalty
    let penalty = config.MULTIPLIER; // 0.50 = 50% discount

    // Compound with low demand score if applicable
    // If item has zero sales AND low demand, it's truly dead inventory
    if (
      demandScore !== undefined &&
      demandScore !== null &&
      demandScore < config.LOW_DEMAND_THRESHOLD
    ) {
      // Multiplicative compounding: 0.50 × 0.60 = 0.30 (70% total discount)
      penalty = penalty * config.COMPOUND_MULTIPLIER;
    }

    return penalty;
  }

  /**
   * Calculate time-decayed retirement multiplier
   * Appreciation accelerates over years after retirement
   *
   * CRITICAL: Demand-gated - retirement premium only applies with real demand
   * A retired set with no buyers is just old inventory!
   */
  private static calculateRetirementMultiplier(
    retirementStatus?: string,
    yearsPostRetirement?: number,
    demandScore?: number,
  ): number {
    const config = CONFIG.INTRINSIC_VALUE;

    // Active or retiring soon - simple multipliers
    if (retirementStatus === "retiring_soon") {
      return config.RETIREMENT_MULTIPLIERS.RETIRING_SOON; // 8%
    } else if (retirementStatus !== "retired") {
      return config.RETIREMENT_MULTIPLIERS.ACTIVE; // 1.0
    }

    // RETIRED STATUS - Apply demand gating
    // Check if demand meets minimum threshold for retirement premium
    const hasSufficientDemand = demandScore !== undefined &&
      demandScore !== null &&
      demandScore >= config.RETIREMENT_TIME_DECAY.MIN_DEMAND_FOR_PREMIUM;

    if (!hasSufficientDemand) {
      // Low/no demand: Cap premium at 2% regardless of retirement age
      // Being retired doesn't matter if nobody wants it!
      return config.RETIREMENT_TIME_DECAY.LOW_DEMAND_MAX_PREMIUM;
    }

    // Sufficient demand: Apply REALISTIC J-CURVE appreciation
    if (
      yearsPostRetirement !== undefined && yearsPostRetirement !== null &&
      yearsPostRetirement >= 0
    ) {
      // Realistic J-curve: dip, stabilize, then appreciate
      if (yearsPostRetirement < 1) {
        return config.RETIREMENT_TIME_DECAY.YEAR_0_1; // 0.95x (market flooded)
      } else if (yearsPostRetirement < 2) {
        return config.RETIREMENT_TIME_DECAY.YEAR_1_2; // 1.00x (baseline)
      } else if (yearsPostRetirement < 5) {
        return config.RETIREMENT_TIME_DECAY.YEAR_2_5; // 1.15x (genuine appreciation)
      } else if (yearsPostRetirement < 10) {
        return config.RETIREMENT_TIME_DECAY.YEAR_5_10; // 1.40x (scarcity premium)
      } else {
        return config.RETIREMENT_TIME_DECAY.YEAR_10_PLUS; // 2.00x (vintage)
      }
    } else {
      // No time data - use conservative baseline
      return config.RETIREMENT_MULTIPLIERS.RETIRED; // 1.15x legacy
    }
  }

  /**
   * Calculate theme-based multiplier
   * Not all LEGO themes appreciate equally
   */
  private static calculateThemeMultiplier(theme?: string): number {
    if (!theme) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS.DEFAULT;
    }

    // Normalize theme name (case-insensitive, trim)
    const normalizedTheme = theme.trim();

    // Check for exact match first
    if (normalizedTheme in CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS[
        normalizedTheme as keyof typeof CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS
      ];
    }

    // Partial matching for common variants
    const themeLower = normalizedTheme.toLowerCase();
    if (themeLower.includes("star wars")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["Star Wars"];
    }
    if (themeLower.includes("harry potter")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["Harry Potter"];
    }
    if (themeLower.includes("architecture")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["Architecture"];
    }
    if (themeLower.includes("creator")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["Creator Expert"];
    }
    if (themeLower.includes("technic")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["Technic"];
    }
    if (themeLower.includes("ideas")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["Ideas"];
    }
    if (themeLower.includes("city")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["City"];
    }
    if (themeLower.includes("friends")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["Friends"];
    }
    if (themeLower.includes("duplo")) {
      return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS["Duplo"];
    }

    // Default for unknown themes
    return CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS.DEFAULT;
  }

  /**
   * Calculate Parts-Per-Dollar (PPD) quality score
   * Higher PPD = better brick value
   */
  private static calculatePPDScore(
    partsCount?: number,
    msrp?: number,
  ): number {
    if (!partsCount || !msrp || msrp <= 0) {
      return 1.0; // Neutral if no data
    }

    // Convert cents to dollars for PPD calculation (thresholds are calibrated for dollars)
    const ppd = partsCount / (msrp / 100);
    const config = CONFIG.INTRINSIC_VALUE.PARTS_PER_DOLLAR;

    // Convert PPD to multiplier (0.9-1.1 range)
    if (ppd >= config.EXCELLENT) {
      return 1.10; // Excellent value
    } else if (ppd >= config.GOOD) {
      return 1.05; // Good value
    } else if (ppd >= config.FAIR) {
      return 1.00; // Fair value
    } else {
      return 0.95; // Poor value
    }
  }

  /**
   * Calculate Price-to-Retail (P/R) ratio
   * Filters bubble-priced sets
   * Returns null if ratio exceeds maximum acceptable threshold
   */
  static calculatePriceToRetailRatio(
    marketPrice?: number,
    msrp?: number,
  ): { ratio: number; status: string } | null {
    if (!marketPrice || !msrp || msrp <= 0) {
      return null; // Can't calculate
    }

    const ratio = marketPrice / msrp;
    const config = CONFIG.INTRINSIC_VALUE.PRICE_TO_RETAIL;

    let status: string;
    if (ratio <= config.GOOD_DEAL) {
      status = "Good Deal";
    } else if (ratio <= config.FAIR) {
      status = "Fair";
    } else if (ratio <= config.EXPENSIVE) {
      status = "Expensive";
    } else if (ratio <= config.BUBBLE) {
      status = "Bubble";
    } else {
      status = "Extreme Bubble";
    }

    return { ratio, status };
  }

  /**
   * Calculate intrinsic value using FUNDAMENTAL VALUE APPROACH
   * 1. Base value = MSRP/Retail (replacement cost) - NOT market price
   * 2. Apply multipliers for retirement, quality, demand, theme, PPD
   * 3. Apply discounts for risk (liquidity, volatility, saturation, zero sales)
   *
   * CRITICAL FIX: Using MSRP as base avoids circular reasoning
   * Market price is what you PAY, intrinsic value is what it's WORTH
   *
   * Calculation steps:
   * 1. Base value (MSRP > Retail > Bricklink discounted)
   * 2. Quality multipliers (retirement, theme, PPD, quality, demand)
   * 3. Liquidity multiplier (sales velocity, time between sales)
   * 4. Risk discounts (volatility, saturation, zero sales penalty)
   *
   * ENHANCED: Zero sales penalty heavily punishes dead inventory
   *
   * @returns Intrinsic value in CENTS (Cents branded type)
   */
  static calculateIntrinsicValue(inputs: IntrinsicValueInputs): Cents {
    // Validate inputs
    this.validatePrice(inputs.bricklinkAvgPrice, "bricklinkAvgPrice");
    this.validatePrice(inputs.bricklinkMaxPrice, "bricklinkMaxPrice");
    this.validateScore(inputs.demandScore, "demandScore");
    this.validateScore(inputs.qualityScore, "qualityScore");

    const {
      msrp,
      currentRetailPrice,
      bricklinkAvgPrice,
      bricklinkMaxPrice,
      retirementStatus,
      yearsPostRetirement,
      salesVelocity,
      avgDaysBetweenSales,
      timesSold,
      priceVolatility,
      availableQty,
      availableLots,
      theme,
      partsCount,
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

    // CRITICAL FIX: Base value = MSRP/Retail (replacement cost), NOT market price
    // This avoids circular reasoning - market price is what you PAY, not intrinsic WORTH
    let baseValue = 0;

    if (msrp && msrp > 0) {
      // Best case: We have MSRP (original retail price)
      baseValue = msrp;
    } else if (currentRetailPrice && currentRetailPrice > 0) {
      // Second best: Current retail price (for active sets)
      baseValue = currentRetailPrice;
    } else if (bricklinkAvgPrice && bricklinkMaxPrice) {
      // Fallback: Use conservative Bricklink estimate
      // Apply 30% discount to account for speculation premium
      baseValue = (bricklinkAvgPrice *
          CONFIG.INTRINSIC_VALUE.BASE_WEIGHTS.AVG_PRICE +
        bricklinkMaxPrice * CONFIG.INTRINSIC_VALUE.BASE_WEIGHTS.MAX_PRICE) *
        0.70;
    } else if (bricklinkAvgPrice) {
      baseValue = bricklinkAvgPrice * 0.70; // 30% discount
    } else if (bricklinkMaxPrice) {
      baseValue = bricklinkMaxPrice * 0.50; // 50% discount (very conservative)
    } else {
      // No data - cannot calculate intrinsic value
      return 0 as Cents;
    }

    // DEMAND-GATED retirement multiplier (CRITICAL: demand required for premium)
    // Passes demandScore to gate retirement premium - no demand = no premium!
    const retirementMultiplier = this.calculateRetirementMultiplier(
      retirementStatus,
      yearsPostRetirement,
      inputs.demandScore, // Pass raw score for demand gating
    );

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

    // Liquidity multiplier (0.85-1.10 based on sales velocity/days between sales)
    const liquidityMultiplier = this.calculateLiquidityMultiplier(
      salesVelocity,
      avgDaysBetweenSales,
    );

    // Volatility discount (risk-adjusted, penalizes high volatility)
    const volatilityDiscount = this.calculateVolatilityDiscount(
      priceVolatility,
    );

    // SATURATION discount (CRITICAL: oversupply kills value)
    // High qty available + many sellers + low velocity = saturated market
    const saturationDiscount = this.calculateSaturationDiscount(
      availableQty,
      availableLots,
      salesVelocity,
    );

    // NEW: Theme-based multiplier (not all themes appreciate equally)
    const themeMultiplier = this.calculateThemeMultiplier(theme);

    // NEW: Parts-per-dollar quality score
    const ppdScore = this.calculatePPDScore(partsCount, msrp);

    // CRITICAL: Zero sales penalty (dead inventory detection)
    // Items with zero sales get heavily penalized
    const zeroSalesPenalty = this.calculateZeroSalesPenalty(
      timesSold,
      inputs.demandScore,
    );

    // Calculate intrinsic value with all factors
    // Structure: Base × Positive Multipliers × Risk Discounts
    const intrinsicValue = baseValue *
      retirementMultiplier * // Time-based appreciation
      themeMultiplier * // Theme quality
      ppdScore * // Brick value quality
      qualityMultiplier * // Product quality
      demandMultiplier * // Market demand
      liquidityMultiplier * // Ease of selling
      volatilityDiscount * // Price stability
      saturationDiscount * // Market oversupply
      zeroSalesPenalty; // Dead inventory penalty (CRITICAL)

    // Guard against NaN or negative values
    if (isNaN(intrinsicValue) || intrinsicValue < 0) {
      console.warn(
        "[ValueCalculator] Calculated invalid intrinsic value:",
        { intrinsicValue, inputs },
      );
      return 0 as Cents;
    }

    // Return as integer cents (already in cents, just ensure it's an integer)
    return Math.round(intrinsicValue) as Cents;
  }

  /**
   * Calculate target buy price (price at which you should buy)
   * Using margin of safety principle - buy at a discount to intrinsic value
   *
   * Enhanced with strategy-specific margins and availability/demand adjustments
   *
   * @returns Target price in CENTS (Cents branded type)
   */
  static calculateTargetPrice(
    intrinsicValue: Cents,
    options: {
      strategy?: StrategyType;
      availabilityScore?: number;
      demandScore?: number;
      desiredMarginOfSafety?: number;
    } = {},
  ): Cents {
    // Validate inputs
    if (
      typeof intrinsicValue !== "number" || isNaN(intrinsicValue) ||
      intrinsicValue <= 0
    ) {
      return 0 as Cents;
    }

    let marginOfSafety: number;

    // Use strategy-specific margin if provided
    if (options.strategy && STRATEGY_MARGINS[options.strategy]) {
      marginOfSafety = STRATEGY_MARGINS[options.strategy].margin;
    } else if (
      typeof options.desiredMarginOfSafety === "number" &&
      !isNaN(options.desiredMarginOfSafety) &&
      options.desiredMarginOfSafety >= 0 &&
      options.desiredMarginOfSafety < 1
    ) {
      marginOfSafety = options.desiredMarginOfSafety;
    } else {
      marginOfSafety = CONFIG.MARGIN_OF_SAFETY.DEFAULT;
    }

    // Adjust margin based on availability (retiring soon = higher acceptable price)
    if (
      typeof options.availabilityScore === "number" &&
      options.availabilityScore > 80
    ) {
      // High availability score means urgent/retiring soon - reduce margin by up to 5%
      const urgencyAdjustment = ((options.availabilityScore - 80) / 20) * 0.05;
      marginOfSafety = Math.max(0.05, marginOfSafety - urgencyAdjustment);
    }

    // Adjust margin based on demand (high liquidity = can afford smaller margin)
    if (typeof options.demandScore === "number" && options.demandScore > 70) {
      // High demand means easier to resell - can reduce margin slightly
      const demandAdjustment = ((options.demandScore - 70) / 30) * 0.03;
      marginOfSafety = Math.max(0.05, marginOfSafety - demandAdjustment);
    } else if (
      typeof options.demandScore === "number" && options.demandScore < 40
    ) {
      // Low demand means harder to resell - increase margin for safety
      const demandAdjustment = ((40 - options.demandScore) / 40) * 0.05;
      marginOfSafety = Math.min(0.50, marginOfSafety + demandAdjustment);
    }

    const targetPrice = intrinsicValue * (1 - marginOfSafety);
    return Math.round(targetPrice * Math.pow(10, CONFIG.PRECISION.PRICE)) /
      Math.pow(10, CONFIG.PRECISION.PRICE) as Cents;
  }

  /**
   * Calculate margin of safety percentage
   * Positive = buying below intrinsic value (good!)
   * Negative = paying above intrinsic value (bad!)
   */
  static calculateMarginOfSafety(
    currentPrice: Cents,
    intrinsicValue: Cents,
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
   * Calculate realized value after transaction costs
   * UPDATED: More realistic costs including returns and damage
   * Real-world costs: selling fees, shipping, packaging, returns
   *
   * @returns Realized value in CENTS (Cents branded type)
   */
  static calculateRealizedValue(
    intrinsicValue: Cents,
    estimatedWeight: number = 2, // pounds, default estimate
  ): Cents {
    // Validate input
    if (
      typeof intrinsicValue !== "number" || isNaN(intrinsicValue) ||
      intrinsicValue <= 0
    ) {
      return 0 as Cents;
    }

    const costs = CONFIG.TRANSACTION_COSTS;

    // 1. Subtract selling fees (percentage of sale price)
    const afterFees = intrinsicValue * (1 - costs.SELLING_FEE_RATE);

    // 2. Subtract shipping costs (base + per-pound)
    const shippingCost = costs.SHIPPING_BASE +
      (estimatedWeight * costs.SHIPPING_PER_POUND);

    // 3. Subtract packaging costs
    const packagingCost = costs.PACKAGING_COST;

    // 4. Account for returns/damage (percentage)
    const afterReturns = afterFees * (1 - costs.RETURN_DAMAGE_RATE);

    // Total realized value
    const realizedValue = afterReturns - shippingCost - packagingCost;

    // Guard against negative values
    return Math.max(0, realizedValue) as Cents;
  }

  /**
   * Calculate annualized holding costs
   * Includes storage, capital cost, and degradation risk
   */
  static calculateHoldingCosts(
    value: number,
    holdingPeriodYears: number,
  ): number {
    if (value <= 0 || holdingPeriodYears <= 0) {
      return 0;
    }

    const costs = CONFIG.TRANSACTION_COSTS;

    // Annual holding cost rate
    const annualRate = costs.STORAGE_COST_ANNUAL +
      costs.CAPITAL_COST_ANNUAL +
      costs.DEGRADATION_RISK_ANNUAL;

    // Total holding costs over period
    return value * annualRate * holdingPeriodYears;
  }

  /**
   * Calculate expected ROI based on buying at current price
   * and selling at intrinsic value
   * NEW: Returns both theoretical and realized ROI (after transaction costs)
   */
  static calculateExpectedROI(
    currentPrice: Cents,
    intrinsicValue: Cents,
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
   * Calculate realistic expected ROI accounting for transaction costs
   * More accurate projection of actual profit
   */
  static calculateRealizedROI(
    currentPrice: Cents,
    intrinsicValue: Cents,
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

    // Calculate realized value after transaction costs
    const realizedValue = this.calculateRealizedValue(intrinsicValue);

    // ROI based on realized value (what you actually get)
    const roi = ((realizedValue - currentPrice) / currentPrice) * 100;

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
   * Includes both theoretical and realized (post-transaction cost) metrics
   *
   * @returns ValueMetricsInDollars (all prices in CENTS despite the name)
   */
  static calculateValueMetrics(
    currentPrice: Cents,
    inputs: IntrinsicValueInputs,
    urgency?: string,
  ): ValueMetricsInDollars {
    // Validate current price
    this.validatePrice(currentPrice, "currentPrice");

    const intrinsicValue = this.calculateIntrinsicValue(inputs);
    const realizedValue = this.calculateRealizedValue(intrinsicValue);
    const targetPrice = this.calculateTargetPrice(intrinsicValue);
    const marginOfSafety = this.calculateMarginOfSafety(
      currentPrice,
      intrinsicValue,
    );
    const expectedROI = this.calculateExpectedROI(currentPrice, intrinsicValue);
    const realizedROI = this.calculateRealizedROI(currentPrice, intrinsicValue);
    const timeHorizon = this.estimateTimeHorizon(
      inputs.retirementStatus,
      urgency,
    );

    return {
      currentPrice,
      targetPrice,
      intrinsicValue,
      realizedValue,
      marginOfSafety,
      expectedROI,
      realizedROI,
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

  /**
   * Calculate recommended buy price with detailed reasoning
   * Integrates strategy, demand, and availability factors
   */
  static calculateRecommendedBuyPrice(
    inputs: IntrinsicValueInputs,
    options: {
      strategy?: StrategyType;
      availabilityScore?: number;
      demandScore?: number;
    } = {},
  ): {
    price: Cents;
    reasoning: string;
    confidence: number;
    breakdown?: {
      intrinsicValue: Cents;
      baseMargin: number;
      adjustedMargin: number;
      marginAdjustments: Array<{ reason: string; value: number }>;
      inputs: {
        msrp?: Cents;
        bricklinkAvgPrice?: Cents;
        bricklinkMaxPrice?: Cents;
        retirementStatus?: string;
        demandScore?: number;
        qualityScore?: number;
        availabilityScore?: number;
      };
    };
  } | null {
    const intrinsicValue = this.calculateIntrinsicValue(inputs);

    if (intrinsicValue === 0) {
      return null; // Insufficient data
    }

    // Calculate margin of safety with detailed tracking
    const strategy = options.strategy || "Investment Focus";
    const strategyConfig = STRATEGY_MARGINS[strategy];
    const baseMargin: number = strategyConfig.margin;
    let adjustedMargin: number = baseMargin;
    const marginAdjustments: Array<{ reason: string; value: number }> = [];

    // Track availability adjustment
    if (
      typeof options.availabilityScore === "number" &&
      options.availabilityScore > 80
    ) {
      const urgencyAdjustment = ((options.availabilityScore - 80) / 20) * 0.05;
      adjustedMargin = Math.max(0.05, adjustedMargin - urgencyAdjustment);
      marginAdjustments.push({
        reason: `High urgency (availability score ${options.availabilityScore})`,
        value: -urgencyAdjustment,
      });
    }

    // Track demand adjustment
    if (typeof options.demandScore === "number" && options.demandScore > 70) {
      const demandAdjustment = ((options.demandScore - 70) / 30) * 0.03;
      const newMargin = Math.max(0.05, adjustedMargin - demandAdjustment);
      const actualAdjustment = adjustedMargin - newMargin;
      adjustedMargin = newMargin;
      marginAdjustments.push({
        reason: `High demand/liquidity (demand score ${options.demandScore})`,
        value: -actualAdjustment,
      });
    } else if (
      typeof options.demandScore === "number" && options.demandScore < 40
    ) {
      const demandAdjustment = ((40 - options.demandScore) / 40) * 0.05;
      const newMargin = Math.min(0.50, adjustedMargin + demandAdjustment);
      const actualAdjustment = newMargin - adjustedMargin;
      adjustedMargin = newMargin;
      marginAdjustments.push({
        reason: `Low demand/liquidity (demand score ${options.demandScore})`,
        value: actualAdjustment,
      });
    }

    const targetPrice = intrinsicValue * (1 - adjustedMargin);
    // Round to integer cents
    const roundedTargetPrice = Math.round(targetPrice) as Cents;

    // Calculate confidence based on data availability
    let dataPoints = 0;
    let availablePoints = 0;

    // Check pricing data availability
    availablePoints += 2;
    if (inputs.bricklinkAvgPrice) dataPoints++;
    if (inputs.bricklinkMaxPrice) dataPoints++;

    // Check quality/demand scores
    availablePoints += 2;
    if (inputs.demandScore !== undefined) dataPoints++;
    if (inputs.qualityScore !== undefined) dataPoints++;

    const confidence = Math.round((dataPoints / availablePoints) * 100) / 100;

    // Build reasoning
    const reasoningParts: string[] = [];

    reasoningParts.push(
      `${strategy} strategy (${strategyConfig.description}, ${
        Math.round(strategyConfig.margin * 100)
      }% margin base)`,
    );

    if (inputs.bricklinkAvgPrice) {
      reasoningParts.push(
        `Based on Bricklink resale value of $${
          (inputs.bricklinkAvgPrice / 100).toFixed(2)
        }`,
      );
    }

    if (inputs.retirementStatus === "retiring_soon") {
      reasoningParts.push("Adjusted for retirement urgency");
    } else if (inputs.retirementStatus === "retired") {
      reasoningParts.push("Premium for retired set");
    }

    if (options.demandScore !== undefined) {
      if (options.demandScore > 70) {
        reasoningParts.push("High liquidity increases acceptable price");
      } else if (options.demandScore < 40) {
        reasoningParts.push("Low demand requires safety margin");
      }
    }

    if (
      options.availabilityScore !== undefined && options.availabilityScore > 80
    ) {
      reasoningParts.push("Urgent window justifies higher entry price");
    }

    const reasoning = reasoningParts.join(". ") + ".";

    return {
      price: roundedTargetPrice,
      reasoning,
      confidence,
      breakdown: {
        intrinsicValue,
        baseMargin,
        adjustedMargin,
        marginAdjustments,
        inputs: {
          msrp: inputs.msrp,
          bricklinkAvgPrice: inputs.bricklinkAvgPrice,
          bricklinkMaxPrice: inputs.bricklinkMaxPrice,
          retirementStatus: inputs.retirementStatus,
          demandScore: inputs.demandScore,
          qualityScore: inputs.qualityScore,
          availabilityScore: options.availabilityScore,
        },
      },
    };
  }
}
