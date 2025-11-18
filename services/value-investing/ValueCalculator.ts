import type {
  IntrinsicValueInputs,
  ValueMetricsInDollars,
} from "../../types/value-investing.ts";
import {
  getValueRatingConfig,
  VALUE_INVESTING_CONFIG as CONFIG,
} from "./ValueInvestingConfig.ts";
import type { Cents } from "../../types/price.ts";
import {
  DealQualityCalculator,
  type DealQualityMetrics,
} from "./DealQualityCalculator.ts";
import {
  DataQualityValidator,
  type DataQualityResult,
} from "./DataQualityValidator.ts";

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
      salesVelocity !== undefined && salesVelocity !== null &&
      salesVelocity >= 0
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
        liquidityScore = Math.max(
          0,
          (salesVelocity / config.VELOCITY_DEAD) * 15,
        );
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
   * CONTEXT-AWARE: Volatility meaning depends on retirement status and price direction
   *
   * For RETIRED sets with RISING prices:
   *   - High volatility = collector frenzy / appreciation phase (GOOD)
   *   - No penalty applied
   *
   * For RETIRED sets with FALLING prices:
   *   - High volatility = sellers panicking / market uncertainty (BAD)
   *   - Heavy penalty (15% discount)
   *
   * For ACTIVE/NEW sets:
   *   - High volatility = unstable pricing / market noise (BAD)
   *   - Standard penalty (original formula)
   */
  private static calculateVolatilityDiscount(
    priceVolatility?: number,
    retirementStatus?: string,
    yearsPostRetirement?: number,
    priceTrend?: number, // Positive = rising, negative = falling
  ): number {
    const config = CONFIG.INTRINSIC_VALUE.VOLATILITY_DISCOUNT;

    // No data = no discount (benefit of doubt)
    if (
      priceVolatility === undefined || priceVolatility === null ||
      priceVolatility < 0
    ) {
      return 1.0;
    }

    // CONTEXT-AWARE LOGIC for retired sets
    const isRetired = retirementStatus === "retired";
    const isMatured = yearsPostRetirement !== undefined && yearsPostRetirement >= 2;

    if (isRetired && isMatured) {
      // For mature retired sets, interpret volatility in context of price direction

      if (priceTrend !== undefined && priceTrend > 0) {
        // RISING PRICES + HIGH VOLATILITY = Collector demand / appreciation phase
        // This is GOOD volatility - don't penalize
        // Example: Architecture sets during appreciation phase often have 50-100% volatility
        if (priceVolatility > 0.30) {
          return 1.0; // No penalty for high volatility during bull runs
        } else {
          return 1.0; // Low volatility is also fine
        }
      } else if (priceTrend !== undefined && priceTrend < 0) {
        // FALLING PRICES + HIGH VOLATILITY = Sellers panicking / market dump
        // This is BAD volatility - heavy penalty
        if (priceVolatility > 0.30) {
          return 0.85; // 15% discount for volatile falling prices
        } else {
          return 0.95; // 5% discount for stable falling prices
        }
      }
    }

    // DEFAULT: For active sets or when no trend data, use original risk-adjusted formula
    // High volatility in active/new sets = unstable pricing = risk
    const discount = Math.min(
      priceVolatility * config.RISK_AVERSION_COEFFICIENT,
      config.MAX_DISCOUNT,
    );

    return 1.0 - discount;
  }

  /**
   * Calculate market saturation discount using "Months of Inventory" approach
   *
   * Philosophy: How many months would it take to sell all available inventory?
   * - <3 months = undersupplied (premium) - scarcity drives value up
   * - 3-12 months = healthy (neutral) - balanced market
   * - 12-24 months = oversupplied (discount) - too much inventory suppresses price
   * - >24 months = dead inventory (heavy discount) - reject these deals
   *
   * CRITICAL: This is a clearer, more intuitive measure than abstract "saturation scores"
   * Aligns with Pabrai's principle: Focus on clear, understandable metrics
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

    // Calculate months of inventory
    const monthsOfInventory = this.calculateMonthsOfInventory(
      availableQty,
      salesVelocity,
    );

    let saturationDiscount = 1.0; // Start with no discount

    if (monthsOfInventory !== null) {
      // Primary driver: Months of inventory (70% weight)
      if (monthsOfInventory > 24) {
        // Dead inventory: >24 months to sell through
        saturationDiscount = 0.50; // 50% discount - REJECT these deals
      } else if (monthsOfInventory > 12) {
        // Oversupplied: 12-24 months inventory
        // Linear interpolation from 1.0 (at 12 months) to 0.50 (at 24 months)
        const excessMonths = monthsOfInventory - 12;
        const discountFactor = excessMonths / 12; // 0 to 1
        saturationDiscount = 1.0 - (discountFactor * 0.50); // 1.0 to 0.50
      } else if (monthsOfInventory > 3) {
        // Healthy: 3-12 months inventory
        // Neutral zone with slight adjustment
        // At 3 months: 1.0 (neutral)
        // At 12 months: 1.0 (neutral)
        saturationDiscount = 1.0; // No discount in healthy range
      } else if (monthsOfInventory > 1) {
        // Low inventory: 1-3 months
        // Slight premium for scarcity (but not too much - could just be low demand)
        const scarcityFactor = (3 - monthsOfInventory) / 2; // 0 to 1
        saturationDiscount = 1.0 + (scarcityFactor * 0.05); // 1.0 to 1.05 (5% premium)
      } else if (monthsOfInventory <= 1) {
        // Very scarce: <1 month inventory
        // Moderate premium (but verify demand is real!)
        saturationDiscount = 1.05; // 5% premium max
      }
    } else {
      // No velocity data - fall back to seller count + absolute quantity
      let saturationScore = 0; // 0 = healthy, 100 = saturated

      // Factor 1: Absolute quantity (40% weight)
      if (
        availableQty !== undefined && availableQty !== null && availableQty > 0
      ) {
        if (availableQty >= config.QTY_EXTREME) {
          saturationScore += 40; // Extreme oversupply
        } else if (availableQty >= config.QTY_HIGH) {
          saturationScore += 30 + ((availableQty - config.QTY_HIGH) /
                (config.QTY_EXTREME - config.QTY_HIGH)) * 10;
        } else if (availableQty >= config.QTY_MEDIUM) {
          saturationScore += 15 + ((availableQty - config.QTY_MEDIUM) /
                (config.QTY_HIGH - config.QTY_MEDIUM)) * 15;
        } else if (availableQty >= config.QTY_LOW) {
          saturationScore += ((availableQty - config.QTY_LOW) /
            (config.QTY_MEDIUM - config.QTY_LOW)) * 15;
        }
      }

      // Factor 2: Number of competing sellers (30% weight)
      if (
        availableLots !== undefined && availableLots !== null &&
        availableLots > 0
      ) {
        if (availableLots >= config.LOTS_EXTREME) {
          saturationScore += 30; // Extreme seller count
        } else if (availableLots >= config.LOTS_HIGH) {
          saturationScore += 22 + ((availableLots - config.LOTS_HIGH) /
                (config.LOTS_EXTREME - config.LOTS_HIGH)) * 8;
        } else if (availableLots >= config.LOTS_MEDIUM) {
          saturationScore += 12 + ((availableLots - config.LOTS_MEDIUM) /
                (config.LOTS_HIGH - config.LOTS_MEDIUM)) * 10;
        } else if (availableLots >= config.LOTS_LOW) {
          saturationScore += ((availableLots - config.LOTS_LOW) /
            (config.LOTS_MEDIUM - config.LOTS_LOW)) * 12;
        }
      }

      // Convert saturation score (0-100) to discount multiplier (0.50-1.0)
      const range = config.MAX - config.MIN;
      saturationDiscount = config.MAX - (saturationScore / 100) * range;
    }

    return Math.max(config.MIN, Math.min(config.MAX, saturationDiscount));
  }

  /**
   * Helper: Calculate months of inventory at current sales rate
   * Returns null if cannot be calculated (no velocity data)
   */
  private static calculateMonthsOfInventory(
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
    if (salesVelocity === 0) return 999; // Not selling = infinite inventory (treat as dead)

    // Sales velocity is in units/day
    const monthlyVelocity = salesVelocity * 30;

    if (monthlyVelocity === 0) return 999; // Not selling

    const monthsOfInventory = availableQty / monthlyVelocity;

    // Cap at 999 to avoid infinity issues
    return Math.min(999, Math.round(monthsOfInventory * 10) / 10);
  }

  /**
   * PABRAI'S "TOO HARD PILE" - Hard gate rejection criteria
   * Implements strict data quality and market condition thresholds
   * Returns rejection reason if set should be rejected, null if acceptable
   *
   * Philosophy: Only invest in sets you can confidently value with acceptable risk
   */
  private static checkHardGateRejection(
    inputs: IntrinsicValueInputs,
  ): { shouldReject: boolean; reason: string; category: string } | null {
    const demandScore = this.safeScore(inputs.demandScore, 50);
    const qualityScore = this.safeScore(inputs.qualityScore, 50);

    // GATE 1: Minimum Quality/Demand Threshold
    // Sets with scores <40 are too uncertain to value confidently
    if (qualityScore < 40) {
      return {
        shouldReject: true,
        reason: `Quality score too low (${qualityScore.toFixed(0)}/100, minimum 40/100) - insufficient data for confident valuation`,
        category: "INSUFFICIENT_DATA",
      };
    }

    if (demandScore < 40) {
      return {
        shouldReject: true,
        reason: `Demand score too low (${demandScore.toFixed(0)}/100, minimum 40/100) - insufficient market demand`,
        category: "INSUFFICIENT_DEMAND",
      };
    }

    // GATE 2: Dead Inventory Gate (Sales Velocity)
    // Less than 1 sale per month = illiquid asset
    if (
      inputs.salesVelocity !== undefined &&
      inputs.salesVelocity !== null &&
      inputs.salesVelocity < 0.033
    ) {
      return {
        shouldReject: true,
        reason: `Sales velocity too low (${(inputs.salesVelocity * 30).toFixed(2)} sales/month, minimum 1/month) - illiquid market`,
        category: "DEAD_INVENTORY",
      };
    }

    // GATE 3: Market Oversaturation Gate (Months of Inventory)
    // >24 months of inventory = will take years to sell
    const monthsOfInventory = this.calculateMonthsOfInventory(
      inputs.availableQty,
      inputs.salesVelocity,
    );

    if (monthsOfInventory !== null && monthsOfInventory > 24) {
      return {
        shouldReject: true,
        reason: `Market oversaturated (${monthsOfInventory.toFixed(1)} months of inventory, maximum 24 months) - excessive supply`,
        category: "OVERSATURATED",
      };
    }

    // GATE 4: Value Trap Detection (Falling Knife + Oversupply)
    // Declining prices + high inventory = value trap
    if (
      inputs.priceDecline !== undefined &&
      inputs.priceDecline > 0.15 && // >15% price decline
      monthsOfInventory !== null &&
      monthsOfInventory > 12 // >12 months inventory
    ) {
      return {
        shouldReject: true,
        reason: `Value trap detected: prices declining ${(inputs.priceDecline * 100).toFixed(1)}% with ${monthsOfInventory.toFixed(1)} months inventory - falling knife`,
        category: "VALUE_TRAP",
      };
    }

    // All gates passed - set is acceptable for valuation
    return null;
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
   * Calculate scarcity multiplier based on TRUE scarcity (supply vs demand)
   * CRITICAL FIX: Separated from "availability score" which conflates urgency
   *
   * TRUE SCARCITY = Low supply relative to demand
   * - availableQty: Total units for sale
   * - availableLots: Number of sellers
   * - salesVelocity: How fast units are selling
   *
   * This is DIFFERENT from retirement urgency (time pressure to buy)
   */
  private static calculateScarcityMultiplier(
    availableQty?: number,
    availableLots?: number,
    salesVelocity?: number,
  ): number {
    // No data = no adjustment (neutral)
    if (
      (availableQty === undefined || availableQty === null) &&
      (availableLots === undefined || availableLots === null)
    ) {
      return 1.0;
    }

    // Calculate months of inventory (supply ÷ demand rate)
    const monthsOfInventory = this.calculateMonthsOfInventory(
      availableQty,
      salesVelocity,
    );

    let scarcityScore = 50; // Default to neutral

    // PRIMARY: Months of inventory (if available)
    if (monthsOfInventory !== null) {
      if (monthsOfInventory < 1) {
        scarcityScore = 95; // Extremely scarce (<1 month supply)
      } else if (monthsOfInventory < 3) {
        scarcityScore = 80; // Very scarce (1-3 months)
      } else if (monthsOfInventory < 6) {
        scarcityScore = 65; // Moderately scarce (3-6 months)
      } else if (monthsOfInventory < 12) {
        scarcityScore = 50; // Neutral (6-12 months)
      } else if (monthsOfInventory < 24) {
        scarcityScore = 35; // Abundant (12-24 months)
      } else {
        scarcityScore = 20; // Oversupplied (>24 months)
      }
    } else {
      // FALLBACK: Use absolute quantities (less accurate)
      let qtyScore = 50;
      let lotsScore = 50;

      if (availableQty !== undefined && availableQty !== null) {
        if (availableQty === 0) {
          qtyScore = 100; // Out of stock = maximum scarcity
        } else if (availableQty < 10) {
          qtyScore = 90; // Very low quantity
        } else if (availableQty < 50) {
          qtyScore = 70; // Low quantity
        } else if (availableQty < 200) {
          qtyScore = 50; // Moderate
        } else if (availableQty < 500) {
          qtyScore = 30; // High quantity
        } else {
          qtyScore = 10; // Extremely high quantity
        }
      }

      if (availableLots !== undefined && availableLots !== null) {
        if (availableLots < 5) {
          lotsScore = 90; // Few sellers = scarce
        } else if (availableLots < 15) {
          lotsScore = 70; // Moderate seller count
        } else if (availableLots < 30) {
          lotsScore = 50; // Many sellers
        } else if (availableLots < 50) {
          lotsScore = 30; // Very competitive
        } else {
          lotsScore = 10; // Oversaturated
        }
      }

      // Average the scores
      scarcityScore = (qtyScore + lotsScore) / 2;
    }

    // Convert scarcity score (0-100) to multiplier (0.95-1.10)
    // High scarcity (score 100) = 1.10× multiplier
    // Low scarcity (score 0) = 0.95× multiplier
    const scarcityMultiplier = 0.95 + (scarcityScore / 100) * 0.15;

    return Math.max(0.95, Math.min(1.10, scarcityMultiplier));
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
   * Apply sanity bounds to prevent extreme valuations
   * Prevents multiplicative compounding from creating unrealistic values
   *
   * Buffett principle: "If it seems too good to be true, it probably is"
   *
   * Bounds: 0.30× to 3.50× of base value (MSRP/retail)
   * - Min 0.30×: Even junk sets don't drop to <30% of MSRP
   * - Max 3.50×: Very few sets exceed 3.5× MSRP (even vintage Architecture)
   */
  private static applySanityBounds(
    calculatedValue: number,
    baseValue: number,
  ): { boundedValue: Cents; wasAdjusted: boolean; adjustment: string } {
    if (baseValue <= 0) {
      return {
        boundedValue: calculatedValue as Cents,
        wasAdjusted: false,
        adjustment: "",
      };
    }

    const config = CONFIG.INTRINSIC_VALUE.SANITY_BOUNDS;
    const minAllowed = baseValue * config.MIN_MULTIPLIER; // 0.30× base
    const maxAllowed = baseValue * config.MAX_MULTIPLIER; // 3.50× base

    let boundedValue = calculatedValue;
    let wasAdjusted = false;
    let adjustment = "";

    if (calculatedValue < minAllowed) {
      boundedValue = minAllowed;
      wasAdjusted = true;
      const originalMultiplier = (calculatedValue / baseValue).toFixed(2);
      adjustment =
        `Capped at minimum ${config.MIN_MULTIPLIER}× base value (was ${originalMultiplier}×). Even poor-quality sets retain some value.`;
    } else if (calculatedValue > maxAllowed) {
      boundedValue = maxAllowed;
      wasAdjusted = true;
      const originalMultiplier = (calculatedValue / baseValue).toFixed(2);
      adjustment =
        `Capped at maximum ${config.MAX_MULTIPLIER}× base value (was ${originalMultiplier}×). Extreme valuations likely due to compounding multipliers.`;
    }

    return {
      boundedValue: Math.round(boundedValue) as Cents,
      wasAdjusted,
      adjustment,
    };
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
   * ENHANCED: Sanity bounds prevent extreme valuations (0.30× - 3.50× base)
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

    // Volatility discount (context-aware: retired+rising=good, retired+falling=bad, active=risk)
    const volatilityDiscount = this.calculateVolatilityDiscount(
      priceVolatility,
      retirementStatus,
      yearsPostRetirement,
      inputs.priceTrend,
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

    // NEW: Scarcity multiplier (TRUE scarcity based on supply vs demand)
    // CRITICAL FIX: Now uses availableQty/Lots/Velocity instead of urgency score
    const scarcityMultiplier = this.calculateScarcityMultiplier(
      availableQty,
      availableLots,
      salesVelocity,
    );

    // CRITICAL: Zero sales penalty (dead inventory detection)
    // Items with zero sales get heavily penalized
    const zeroSalesPenalty = this.calculateZeroSalesPenalty(
      timesSold,
      inputs.demandScore,
    );

    // Calculate intrinsic value with all factors
    // Structure: Base × Positive Multipliers × Risk Discounts
    const calculatedValue = baseValue *
      retirementMultiplier * // Time-based appreciation
      themeMultiplier * // Theme quality
      ppdScore * // Brick value quality
      qualityMultiplier * // Product quality
      demandMultiplier * // Market demand
      scarcityMultiplier * // Scarcity premium (inverse of availability)
      liquidityMultiplier * // Ease of selling
      volatilityDiscount * // Price stability
      saturationDiscount * // Market oversupply
      zeroSalesPenalty; // Dead inventory penalty (CRITICAL)

    // Guard against NaN or negative values
    if (isNaN(calculatedValue) || calculatedValue < 0) {
      console.warn(
        "[ValueCalculator] Calculated invalid intrinsic value:",
        { calculatedValue, inputs },
      );
      return 0 as Cents;
    }

    // Apply sanity bounds to prevent extreme valuations (0.30× - 3.50× base)
    const { boundedValue } = this.applySanityBounds(calculatedValue, baseValue);

    // Return as integer cents (already in cents, just ensure it's an integer)
    return boundedValue;
  }

  /**
   * Calculate intrinsic value WITH detailed breakdown for transparency
   * Shows step-by-step how each factor affects the final value
   *
   * ENHANCED: Includes Pabrai-style data quality validation
   * Will return 0 if data quality is insufficient (refuse to calculate with bad data)
   *
   * @returns Object containing intrinsic value, breakdown, and data quality assessment
   */
  static calculateIntrinsicValueWithBreakdown(
    inputs: IntrinsicValueInputs,
  ): {
    intrinsicValue: Cents;
    breakdown: import("../../types/value-investing.ts").IntrinsicValueBreakdown;
    dataQuality?: DataQualityResult;
  } {
    // CRITICAL: Validate data quality FIRST (Pabrai approach)
    // Convert inputs to the format expected by DataQualityValidator
    const bricklinkData = {
      avgPrice: inputs.bricklinkAvgPrice,
      minPrice: undefined, // Not in inputs
      maxPrice: inputs.bricklinkMaxPrice,
      totalQty: inputs.timesSold, // Approximation
      timesSold: inputs.timesSold,
      totalLots: inputs.availableLots,
      salesVelocity: inputs.salesVelocity,
      priceHistory: [], // Not in inputs, but validator will handle
      availableQty: inputs.availableQty,
      priceVolatility: inputs.priceVolatility,
    };

    const worldBricksData = {
      msrp: inputs.msrp,
      status: inputs.retirementStatus,
      theme: inputs.theme,
      pieces: inputs.partsCount,
      yearRetired: inputs.retirementStatus === "retired"
        ? (inputs.yearReleased ? inputs.yearReleased + 3 : undefined)
        : undefined,
    };

    const dataQuality = DataQualityValidator.validate(
      // deno-lint-ignore no-explicit-any
      bricklinkData as any,
      // deno-lint-ignore no-explicit-any
      worldBricksData as any,
    );

    // Pabrai approach: Refuse to calculate if data quality is insufficient
    if (!dataQuality.canCalculate) {
      console.warn(
        "[ValueCalculator] Insufficient data quality to calculate intrinsic value:",
        dataQuality.explanation,
      );

      // Return 0 with explanation
      return {
        intrinsicValue: 0 as Cents,
        breakdown: {
          baseValue: 0 as Cents,
          baseValueSource: "none",
          baseValueExplanation: dataQuality.explanation,
          qualityMultipliers: {
            retirement: { value: 1.0, explanation: "", applied: false },
            quality: { value: 1.0, score: 0, explanation: "" },
            demand: { value: 1.0, score: 0, explanation: "" },
            theme: {
              value: 1.0,
              themeName: "",
              explanation: "Insufficient data",
            },
            partsPerDollar: { value: 1.0, explanation: "Insufficient data" },
            scarcity: {
              value: 1.0,
              score: 0,
              explanation: "Insufficient data",
              applied: false,
            },
          },
          riskDiscounts: {
            liquidity: { value: 1.0, explanation: "", applied: false },
            volatility: { value: 1.0, explanation: "", applied: false },
            saturation: { value: 1.0, explanation: "", applied: false },
            zeroSales: { value: 1.0, explanation: "", applied: false },
          },
          intermediateValues: {
            afterQualityMultipliers: 0 as Cents,
            afterRiskDiscounts: 0 as Cents,
          },
          finalIntrinsicValue: 0 as Cents,
          totalMultiplier: 0,
        },
        dataQuality,
      };
    }

    // HARD GATE REJECTION: Check Pabrai "Too Hard Pile" criteria
    // Refuse to calculate if set fails minimum quality/demand/liquidity thresholds
    const rejection = this.checkHardGateRejection(inputs);
    if (rejection) {
      console.warn(
        "[ValueCalculator] Hard gate rejection:",
        rejection.reason,
      );

      // Return 0 with rejection explanation
      return {
        intrinsicValue: 0 as Cents,
        breakdown: {
          baseValue: 0 as Cents,
          baseValueSource: "none",
          baseValueExplanation: `REJECTED - ${rejection.reason}`,
          qualityMultipliers: {
            retirement: { value: 1.0, explanation: rejection.reason, applied: false },
            quality: { value: 1.0, score: this.safeScore(inputs.qualityScore, 50), explanation: rejection.category === "INSUFFICIENT_DATA" ? rejection.reason : "" },
            demand: { value: 1.0, score: this.safeScore(inputs.demandScore, 50), explanation: rejection.category === "INSUFFICIENT_DEMAND" ? rejection.reason : "" },
            theme: {
              value: 1.0,
              themeName: "",
              explanation: "Set rejected - valuation not performed",
            },
            partsPerDollar: { value: 1.0, explanation: "Set rejected - valuation not performed" },
            scarcity: {
              value: 1.0,
              score: 0,
              explanation: "Set rejected - valuation not performed",
              applied: false,
            },
          },
          riskDiscounts: {
            liquidity: { value: 1.0, explanation: rejection.category === "DEAD_INVENTORY" ? rejection.reason : "", applied: false },
            volatility: { value: 1.0, explanation: "", applied: false },
            saturation: { value: 1.0, explanation: rejection.category === "OVERSATURATED" ? rejection.reason : "", applied: false },
            zeroSales: { value: 1.0, explanation: rejection.category === "VALUE_TRAP" ? rejection.reason : "", applied: false },
          },
          intermediateValues: {
            afterQualityMultipliers: 0 as Cents,
            afterRiskDiscounts: 0 as Cents,
          },
          finalIntrinsicValue: 0 as Cents,
          totalMultiplier: 0,
          // Add rejection metadata
          rejection: {
            rejected: true,
            reason: rejection.reason,
            category: rejection.category as "INSUFFICIENT_DATA" | "INSUFFICIENT_DEMAND" | "DEAD_INVENTORY" | "OVERSATURATED" | "VALUE_TRAP",
          },
        },
        dataQuality,
      };
    }

    // Validate inputs (legacy validation for type checking)
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

    // 1. DETERMINE BASE VALUE
    let baseValue = 0;
    let baseValueSource: "msrp" | "currentRetail" | "bricklink" | "none" =
      "none";
    let baseValueExplanation = "";

    if (msrp && msrp > 0) {
      baseValue = msrp;
      baseValueSource = "msrp";
      baseValueExplanation =
        `Using MSRP as base value (original retail price: MYR ${
          (msrp / 100).toFixed(2)
        })`;
    } else if (currentRetailPrice && currentRetailPrice > 0) {
      baseValue = currentRetailPrice;
      baseValueSource = "currentRetail";
      baseValueExplanation = `Using current retail price as base value: MYR ${
        (currentRetailPrice / 100).toFixed(2)
      }`;
    } else if (bricklinkAvgPrice && bricklinkMaxPrice) {
      baseValue = (bricklinkAvgPrice *
          CONFIG.INTRINSIC_VALUE.BASE_WEIGHTS.AVG_PRICE +
        bricklinkMaxPrice * CONFIG.INTRINSIC_VALUE.BASE_WEIGHTS.MAX_PRICE) *
        0.70;
      baseValueSource = "bricklink";
      baseValueExplanation =
        `Using BrickLink market prices with 30% discount: MYR ${
          (baseValue / 100).toFixed(2)
        }`;
    } else if (bricklinkAvgPrice) {
      baseValue = bricklinkAvgPrice * 0.70;
      baseValueSource = "bricklink";
      baseValueExplanation =
        `Using BrickLink avg price with 30% discount: MYR ${
          (baseValue / 100).toFixed(2)
        }`;
    } else if (bricklinkMaxPrice) {
      baseValue = bricklinkMaxPrice * 0.50;
      baseValueSource = "bricklink";
      baseValueExplanation =
        `Using BrickLink max price with 50% discount: MYR ${
          (baseValue / 100).toFixed(2)
        }`;
    } else {
      baseValueExplanation = "No pricing data available";
    }

    // 2. CALCULATE ALL MULTIPLIERS
    const retirementMultiplier = this.calculateRetirementMultiplier(
      retirementStatus,
      yearsPostRetirement,
      inputs.demandScore,
    );

    const qualityRange = CONFIG.INTRINSIC_VALUE.QUALITY_MULTIPLIER.MAX -
      CONFIG.INTRINSIC_VALUE.QUALITY_MULTIPLIER.MIN;
    const qualityMultiplier = CONFIG.INTRINSIC_VALUE.QUALITY_MULTIPLIER.MIN +
      (qualityScore / 100) * qualityRange;

    const demandRange = CONFIG.INTRINSIC_VALUE.DEMAND_MULTIPLIER.MAX -
      CONFIG.INTRINSIC_VALUE.DEMAND_MULTIPLIER.MIN;
    const demandMultiplier = CONFIG.INTRINSIC_VALUE.DEMAND_MULTIPLIER.MIN +
      (demandScore / 100) * demandRange;

    const themeMultiplier = this.calculateThemeMultiplier(theme);
    const ppdScore = this.calculatePPDScore(partsCount, msrp);
    const scarcityMultiplier = this.calculateScarcityMultiplier(
      availableQty,
      availableLots,
      salesVelocity,
    );
    const liquidityMultiplier = this.calculateLiquidityMultiplier(
      salesVelocity,
      avgDaysBetweenSales,
    );
    const volatilityDiscount = this.calculateVolatilityDiscount(
      priceVolatility,
      retirementStatus,
      yearsPostRetirement,
      inputs.priceTrend,
    );
    const saturationDiscount = this.calculateSaturationDiscount(
      availableQty,
      availableLots,
      salesVelocity,
    );
    const zeroSalesPenalty = this.calculateZeroSalesPenalty(
      timesSold,
      inputs.demandScore,
    );

    // 3. BUILD EXPLANATIONS
    const retirementExplanation = this.getRetirementExplanation(
      retirementStatus,
      yearsPostRetirement,
      inputs.demandScore,
      retirementMultiplier,
    );

    const qualityExplanation = this.getQualityExplanation(
      qualityScore,
      qualityMultiplier,
    );

    const demandExplanation = this.getDemandExplanation(
      demandScore,
      demandMultiplier,
    );

    const themeExplanation = this.getThemeExplanation(
      theme,
      themeMultiplier,
    );

    const ppdExplanation = this.getPPDExplanation(
      partsCount,
      msrp,
      ppdScore,
    );

    const scarcityExplanation = this.getScarcityExplanation(
      availableQty,
      availableLots,
      salesVelocity,
      scarcityMultiplier,
    );

    const liquidityExplanation = this.getLiquidityExplanation(
      salesVelocity,
      avgDaysBetweenSales,
      liquidityMultiplier,
    );

    const volatilityExplanation = this.getVolatilityExplanation(
      priceVolatility,
      volatilityDiscount,
    );

    const saturationExplanation = this.getSaturationExplanation(
      availableQty,
      availableLots,
      salesVelocity,
      saturationDiscount,
    );

    const zeroSalesExplanation = this.getZeroSalesExplanation(
      timesSold,
      inputs.demandScore,
      zeroSalesPenalty,
    );

    // 4. CALCULATE INTERMEDIATE VALUES
    const afterQualityMultipliers = Math.round(
      baseValue *
        retirementMultiplier *
        themeMultiplier *
        ppdScore *
        qualityMultiplier *
        demandMultiplier *
        scarcityMultiplier,
    ) as Cents;

    const calculatedValue = afterQualityMultipliers *
      liquidityMultiplier *
      volatilityDiscount *
      saturationDiscount *
      zeroSalesPenalty;

    // Apply sanity bounds to prevent extreme valuations
    const {
      boundedValue: finalIntrinsicValue,
      wasAdjusted: sanityBoundsApplied,
      adjustment: sanityBoundsExplanation,
    } = this.applySanityBounds(calculatedValue, baseValue);

    const totalMultiplier = baseValue > 0 ? finalIntrinsicValue / baseValue : 0;

    // 5. BUILD BREAKDOWN OBJECT
    const breakdown:
      import("../../types/value-investing.ts").IntrinsicValueBreakdown = {
        baseValue: baseValue as Cents,
        baseValueSource,
        baseValueExplanation,
        qualityMultipliers: {
          retirement: {
            value: retirementMultiplier,
            explanation: retirementExplanation,
            applied: retirementMultiplier !== 1.0,
          },
          quality: {
            value: qualityMultiplier,
            score: qualityScore,
            explanation: qualityExplanation,
          },
          demand: {
            value: demandMultiplier,
            score: demandScore,
            explanation: demandExplanation,
          },
          theme: {
            value: themeMultiplier,
            themeName: theme || "Not specified",
            explanation: themeExplanation,
          },
          partsPerDollar: {
            value: ppdScore,
            ppdValue: partsCount && msrp && msrp > 0
              ? partsCount / (msrp / 100)
              : undefined,
            explanation: ppdExplanation,
          },
          scarcity: {
            value: scarcityMultiplier,
            score: this.calculateMonthsOfInventory(availableQty, salesVelocity) !== null
              ? 100 - Math.min(100, (this.calculateMonthsOfInventory(availableQty, salesVelocity)! / 24) * 100)
              : 50, // If months available, convert to 0-100 score, otherwise neutral
            explanation: scarcityExplanation,
            applied: scarcityMultiplier !== 1.0,
          },
        },
        riskDiscounts: {
          liquidity: {
            value: liquidityMultiplier,
            explanation: liquidityExplanation,
            applied: liquidityMultiplier !== 1.0,
          },
          volatility: {
            value: volatilityDiscount,
            volatilityPercent: priceVolatility
              ? priceVolatility * 100
              : undefined,
            explanation: volatilityExplanation,
            applied: volatilityDiscount !== 1.0,
          },
          saturation: {
            value: saturationDiscount,
            explanation: saturationExplanation,
            applied: saturationDiscount !== 1.0,
          },
          zeroSales: {
            value: zeroSalesPenalty,
            explanation: zeroSalesExplanation,
            applied: zeroSalesPenalty !== 1.0,
          },
        },
        intermediateValues: {
          afterQualityMultipliers,
          afterRiskDiscounts: finalIntrinsicValue,
        },
        finalIntrinsicValue,
        totalMultiplier,
        // Add sanity bounds information if applied
        ...(sanityBoundsApplied && {
          sanityBoundsAdjustment: {
            applied: true,
            explanation: sanityBoundsExplanation,
            originalValue: Math.round(calculatedValue) as Cents,
            boundedValue: finalIntrinsicValue,
          },
        }),
      };

    return {
      intrinsicValue: finalIntrinsicValue,
      breakdown,
      dataQuality, // Include data quality assessment
    };
  }

  /**
   * Generate explanation for retirement multiplier
   */
  private static getRetirementExplanation(
    retirementStatus?: string,
    yearsPostRetirement?: number,
    demandScore?: number,
    multiplier?: number,
  ): string {
    if (retirementStatus === "retiring_soon") {
      return `Set is retiring soon (+${
        ((multiplier! - 1) * 100).toFixed(0)
      }% premium)`;
    } else if (retirementStatus !== "retired") {
      return "Set is active (no retirement premium)";
    }

    const hasSufficientDemand = demandScore !== undefined &&
      demandScore >= CONFIG.INTRINSIC_VALUE.RETIREMENT_TIME_DECAY
          .MIN_DEMAND_FOR_PREMIUM;

    if (!hasSufficientDemand) {
      return `Retired but low demand (${
        demandScore?.toFixed(0) || "unknown"
      }/100) - limited premium (+${((multiplier! - 1) * 100).toFixed(0)}%)`;
    }

    if (
      yearsPostRetirement !== undefined && yearsPostRetirement !== null &&
      yearsPostRetirement >= 0
    ) {
      if (yearsPostRetirement < 1) {
        return `Retired <1 year ago - market flooded (${
          ((multiplier! - 1) * 100).toFixed(0)
        }% change)`;
      } else if (yearsPostRetirement < 2) {
        return `Retired 1-2 years ago - stabilizing (${
          ((multiplier! - 1) * 100).toFixed(0)
        }% change)`;
      } else if (yearsPostRetirement < 5) {
        return `Retired 2-5 years ago - appreciating (+${
          ((multiplier! - 1) * 100).toFixed(0)
        }%)`;
      } else if (yearsPostRetirement < 10) {
        return `Retired 5-10 years ago - scarcity premium (+${
          ((multiplier! - 1) * 100).toFixed(0)
        }%)`;
      } else {
        return `Retired 10+ years ago - vintage (+${
          ((multiplier! - 1) * 100).toFixed(0)
        }%)`;
      }
    }

    return `Retired with sufficient demand (+${
      ((multiplier! - 1) * 100).toFixed(0)
    }% premium)`;
  }

  private static getQualityExplanation(
    score: number,
    multiplier: number,
  ): string {
    const effect = ((multiplier - 1) * 100).toFixed(1);
    const sign = multiplier >= 1 ? "+" : "";
    return `Quality score ${
      score.toFixed(0)
    }/100 (${sign}${effect}% adjustment)`;
  }

  private static getDemandExplanation(
    score: number,
    multiplier: number,
  ): string {
    const effect = ((multiplier - 1) * 100).toFixed(1);
    const sign = multiplier >= 1 ? "+" : "";
    return `Demand score ${
      score.toFixed(0)
    }/100 (${sign}${effect}% adjustment)`;
  }

  private static getThemeExplanation(
    theme: string | undefined,
    multiplier: number,
  ): string {
    if (!theme || multiplier === 1.0) {
      return "No theme premium applied";
    }
    const effect = ((multiplier - 1) * 100).toFixed(0);
    const sign = multiplier >= 1 ? "+" : "";
    return `${theme} theme (${sign}${effect}% adjustment)`;
  }

  private static getPPDExplanation(
    partsCount: number | undefined,
    msrp: number | undefined,
    multiplier: number,
  ): string {
    if (!partsCount || !msrp || msrp <= 0) {
      return "No parts-per-dollar data available";
    }
    const ppd = partsCount / (msrp / 100);
    const effect = ((multiplier - 1) * 100).toFixed(0);
    const sign = multiplier >= 1 ? "+" : "";
    return `${ppd.toFixed(1)} parts/dollar (${sign}${effect}% adjustment)`;
  }

  private static getScarcityExplanation(
    availableQty: number | undefined,
    availableLots: number | undefined,
    salesVelocity: number | undefined,
    multiplier: number,
  ): string {
    if (multiplier === 1.0) {
      return "No scarcity data - neutral adjustment";
    }

    const effect = ((multiplier - 1) * 100).toFixed(1);
    const sign = multiplier >= 1 ? "+" : "";

    // Calculate months of inventory for context
    const monthsOfInventory = this.calculateMonthsOfInventory(
      availableQty,
      salesVelocity,
    );

    const details: string[] = [];

    if (monthsOfInventory !== null) {
      details.push(`${monthsOfInventory.toFixed(1)} months of inventory`);

      if (monthsOfInventory < 3) {
        details.push("(SCARCE - low supply vs demand)");
      } else if (monthsOfInventory < 12) {
        details.push("(balanced supply/demand)");
      } else {
        details.push("(oversupplied)");
      }
    } else {
      if (availableQty !== undefined) details.push(`${availableQty} units`);
      if (availableLots !== undefined) details.push(`${availableLots} sellers`);
    }

    if (details.length === 0) {
      return `Scarcity adjustment: ${sign}${effect}%`;
    }

    return `Market supply: ${details.join(" ")} (${sign}${effect}% scarcity premium)`;
  }

  private static getLiquidityExplanation(
    salesVelocity: number | undefined,
    avgDaysBetweenSales: number | undefined,
    multiplier: number,
  ): string {
    if (multiplier === 1.0) {
      return "No liquidity data - neutral adjustment";
    }
    const effect = ((multiplier - 1) * 100).toFixed(1);
    const sign = multiplier >= 1 ? "+" : "";

    if (salesVelocity !== undefined) {
      return `Sales velocity: ${
        salesVelocity.toFixed(2)
      }/day (${sign}${effect}% adjustment)`;
    } else if (avgDaysBetweenSales !== undefined) {
      return `Avg ${
        avgDaysBetweenSales.toFixed(1)
      } days between sales (${sign}${effect}% adjustment)`;
    }

    return `Liquidity adjustment: ${sign}${effect}%`;
  }

  private static getVolatilityExplanation(
    priceVolatility: number | undefined,
    discount: number,
  ): string {
    if (discount === 1.0 || !priceVolatility) {
      return "No price volatility - stable pricing";
    }
    const effect = ((1 - discount) * 100).toFixed(1);
    return `Price volatility ${
      (priceVolatility * 100).toFixed(1)
    }% (${effect}% discount)`;
  }

  private static getSaturationExplanation(
    availableQty: number | undefined,
    availableLots: number | undefined,
    _salesVelocity: number | undefined,
    discount: number,
  ): string {
    if (discount === 1.0) {
      return "No market saturation detected - healthy supply";
    }
    const effect = ((1 - discount) * 100).toFixed(1);

    const details: string[] = [];
    if (availableQty) details.push(`${availableQty} units available`);
    if (availableLots) details.push(`${availableLots} sellers`);

    if (details.length > 0) {
      return `Market saturation: ${details.join(", ")} (${effect}% discount)`;
    }

    return `Market saturation detected (${effect}% discount)`;
  }

  private static getZeroSalesExplanation(
    timesSold: number | undefined,
    demandScore: number | undefined,
    penalty: number,
  ): string {
    if (penalty === 1.0) {
      return timesSold !== undefined && timesSold > 0
        ? `${timesSold} sales recorded - no penalty`
        : "Sufficient sales activity - no penalty";
    }

    const effect = ((1 - penalty) * 100).toFixed(0);
    if (timesSold === 0 || timesSold === undefined) {
      if (demandScore !== undefined && demandScore < 30) {
        return `Zero sales + low demand (${effect}% penalty for dead inventory)`;
      }
      return `Zero sales recorded (${effect}% penalty)`;
    }

    return `Very low sales activity (${effect}% penalty)`;
  }

  /**
   * Calculate target buy price (price at which you should buy)
   * Using margin of safety principle - buy at a discount to intrinsic value
   *
   * Enhanced with:
   * - Strategy-specific margins
   * - Confidence-aware margins (Buffett principle: bigger margin when uncertain)
   * - Availability/demand adjustments
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
      dataQualityScore?: number; // 0-100 score from DataQualityValidator
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

    // CRITICAL: Confidence-aware margin (Buffett principle)
    // Lower confidence = require bigger margin of safety
    if (
      typeof options.dataQualityScore === "number" &&
      !isNaN(options.dataQualityScore)
    ) {
      if (options.dataQualityScore >= 80) {
        marginOfSafety = CONFIG.MARGIN_OF_SAFETY.HIGH_CONFIDENCE; // 20%
      } else if (options.dataQualityScore >= 50) {
        marginOfSafety = CONFIG.MARGIN_OF_SAFETY.MEDIUM_CONFIDENCE; // 30%
      } else {
        marginOfSafety = CONFIG.MARGIN_OF_SAFETY.LOW_CONFIDENCE; // 40%
      }
    } else if (options.strategy && STRATEGY_MARGINS[options.strategy]) {
      // Use strategy-specific margin if provided (legacy)
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
   * ENHANCED: Confidence-aware minimum margins
   *
   * @param marginOfSafety - Current margin of safety (percentage, e.g., 25 = 25%)
   * @param dataQualityScore - Optional data quality score (0-100)
   * @param minMarginOfSafety - Override minimum margin (percentage)
   */
  static isGoodBuy(
    marginOfSafety: number,
    dataQualityScore?: number,
    minMarginOfSafety?: number,
  ): boolean {
    // Determine minimum required margin based on confidence
    let requiredMargin: number;

    if (minMarginOfSafety !== undefined) {
      // User-specified minimum
      requiredMargin = minMarginOfSafety;
    } else if (dataQualityScore !== undefined) {
      // Confidence-aware minimum
      if (dataQualityScore >= 80) {
        requiredMargin = CONFIG.MARGIN_OF_SAFETY.HIGH_CONFIDENCE * 100; // 20%
      } else if (dataQualityScore >= 50) {
        requiredMargin = CONFIG.MARGIN_OF_SAFETY.MEDIUM_CONFIDENCE * 100; // 30%
      } else {
        requiredMargin = CONFIG.MARGIN_OF_SAFETY.LOW_CONFIDENCE * 100; // 40%
      }
    } else {
      // Default minimum
      requiredMargin = CONFIG.MARGIN_OF_SAFETY.MINIMUM * 100; // 20%
    }

    return marginOfSafety >= requiredMargin;
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
      // Include detailed calculation breakdown
      calculationBreakdown?:
        import("../../types/value-investing.ts").IntrinsicValueBreakdown;
      // Rejection information (if applicable)
      rejection?: {
        rejected: boolean;
        reason: string;
        category: string;
      };
    };
  } | null {
    // Calculate intrinsic value WITH breakdown for transparency
    const { intrinsicValue, breakdown: calculationBreakdown } = this
      .calculateIntrinsicValueWithBreakdown(inputs);

    // Check if rejected by hard gates
    if (intrinsicValue === 0) {
      // Return null, but the rejection info is in calculationBreakdown
      // The caller should check calculationBreakdown.rejection for details
      return null;
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
        reason:
          `High urgency (availability score ${options.availabilityScore})`,
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
        // Include detailed calculation breakdown
        calculationBreakdown,
      },
    };
  }

  /**
   * Calculate deal quality metrics
   * Compares current retail price against market price and intrinsic value
   */
  static calculateDealQuality(
    inputs: IntrinsicValueInputs,
    intrinsicValue: Cents,
  ): DealQualityMetrics | null {
    // Need at least current retail price and one comparison point
    if (!inputs.currentRetailPrice) {
      return null;
    }

    const calculator = new DealQualityCalculator();

    return calculator.calculateDealQuality({
      currentRetailPrice: inputs.currentRetailPrice,
      originalRetailPrice: inputs.originalRetailPrice,
      bricklinkMarketPrice: inputs.bricklinkAvgPrice,
      intrinsicValue: intrinsicValue,
      msrp: inputs.msrp,
    });
  }
}
