/**
 * ValueInputValidator - Unified validation for IntrinsicValueInputs
 *
 * CONSOLIDATES:
 * - IntrinsicValueInputMapper.validate() (presence checking)
 * - DataValidator (range/bound checking)
 *
 * SOLID Principles:
 * - Single Responsibility: Only validates IntrinsicValueInputs
 * - Open/Closed: Easy to extend validation rules
 *
 * DRY Principle:
 * - Single source of truth for all input validation
 * - Eliminates duplicate validation logic
 */

import type { IntrinsicValueInputs } from "../../../types/value-investing.ts";
import type { Cents } from "../../../types/price.ts";

/**
 * Validation result with sanitized data and diagnostics
 */
export interface ValidationResult {
  /** Can we proceed with calculation? */
  isValid: boolean;
  /** Sanitized/cleaned data (undefined if invalid) */
  sanitizedData?: IntrinsicValueInputs;
  /** Critical missing fields that prevent calculation */
  missingCritical: string[];
  /** Optional missing fields (reduces confidence) */
  missingOptional: string[];
  /** Warnings about sanitized/rejected data */
  warnings: string[];
}

/**
 * Validation options
 */
export interface ValidationOptions {
  /** Sanitize invalid data (clamp, reject outliers)? Default: true */
  sanitize?: boolean;
  /** Require optional fields (scores, liquidity)? Default: false */
  strictMode?: boolean;
}

/**
 * Validation bounds configuration
 */
const BOUNDS = {
  PRICE: {
    MIN: 100, // $1 minimum
    MAX: 10000000, // $100k maximum
  },
  SALES_VELOCITY: {
    MIN: 0,
    MAX: 10, // > 10 sales/day is unrealistic
  },
  AVAILABLE_LOTS: {
    MIN: 0,
    MAX: 5000,
  },
  AVAILABLE_QTY: {
    MIN: 0,
    MAX: 50000,
  },
  PARTS_COUNT: {
    MIN: 1,
    MAX: 20000, // Largest sets ~11k pieces
  },
  SCORE: {
    MIN: 0,
    MAX: 100,
  },
  YEARS_POST_RETIREMENT: {
    MIN: 0,
    MAX: 100, // Sets don't last 100+ years in circulation
  },
  YEAR: {
    MIN: 1949, // LEGO founded
    MAX: new Date().getFullYear() + 10, // Future releases
  },
} as const;

/**
 * ValueInputValidator - Pure validation service
 */
export class ValueInputValidator {
  /**
   * Validate IntrinsicValueInputs
   *
   * Returns sanitized data if valid, with diagnostics
   */
  static validate(
    inputs: IntrinsicValueInputs,
    options: ValidationOptions = {},
  ): ValidationResult {
    const { sanitize = true, strictMode = false } = options;

    const missingCritical: string[] = [];
    const missingOptional: string[] = [];
    const warnings: string[] = [];
    const sanitized: Partial<IntrinsicValueInputs> = {};

    // ===== CRITICAL VALIDATION: At least one base value source =====
    const hasPricing = this.validatePricing(
      inputs,
      sanitized,
      warnings,
      sanitize,
    );

    if (!hasPricing) {
      missingCritical.push(
        "pricing (need msrp, currentRetailPrice, or bricklinkAvgPrice)",
      );
    }

    // ===== OPTIONAL VALIDATION: Scores =====
    this.validateScores(inputs, sanitized, warnings, missingOptional, sanitize);

    // If strict mode, require scores
    if (strictMode) {
      if (!inputs.demandScore && !sanitized.demandScore) {
        missingCritical.push("demandScore (required in strict mode)");
      }
      if (!inputs.qualityScore && !sanitized.qualityScore) {
        missingCritical.push("qualityScore (required in strict mode)");
      }
    }

    // ===== OPTIONAL VALIDATION: Market/Demand Data =====
    this.validateMarketData(
      inputs,
      sanitized,
      warnings,
      missingOptional,
      sanitize,
    );

    // ===== OPTIONAL VALIDATION: Product/Quality Data =====
    this.validateProductData(
      inputs,
      sanitized,
      warnings,
      missingOptional,
      sanitize,
    );

    // ===== OPTIONAL VALIDATION: Retirement Data =====
    this.validateRetirementData(
      inputs,
      sanitized,
      warnings,
      missingOptional,
      sanitize,
    );

    // Determine if valid
    const isValid = missingCritical.length === 0;

    return {
      isValid,
      sanitizedData: isValid ? (sanitized as IntrinsicValueInputs) : undefined,
      missingCritical,
      missingOptional,
      warnings,
    };
  }

  /**
   * Validate pricing data (critical)
   * Returns true if we have at least one valid price source
   */
  private static validatePricing(
    inputs: IntrinsicValueInputs,
    sanitized: Partial<IntrinsicValueInputs>,
    warnings: string[],
    sanitize: boolean,
  ): boolean {
    let hasValidPricing = false;

    // MSRP
    if (inputs.msrp !== undefined) {
      if (this.isValidPrice(inputs.msrp)) {
        sanitized.msrp = inputs.msrp;
        hasValidPricing = true;
      } else {
        if (inputs.msrp < 0) {
          warnings.push(`msrp=${inputs.msrp} is negative, rejecting`);
        } else {
          warnings.push(
            `msrp=${inputs.msrp} exceeds maximum ($${BOUNDS.PRICE.MAX / 100}), rejecting as outlier`,
          );
        }
      }
    }

    // Current retail price
    if (inputs.currentRetailPrice !== undefined) {
      if (this.isValidPrice(inputs.currentRetailPrice)) {
        sanitized.currentRetailPrice = inputs.currentRetailPrice;
        hasValidPricing = true;
      } else {
        if (inputs.currentRetailPrice < 0) {
          warnings.push(
            `currentRetailPrice=${inputs.currentRetailPrice} is negative, rejecting`,
          );
        } else {
          warnings.push(
            `currentRetailPrice=${inputs.currentRetailPrice} exceeds maximum, rejecting`,
          );
        }
      }
    }

    // Original retail price
    if (inputs.originalRetailPrice !== undefined) {
      if (this.isValidPrice(inputs.originalRetailPrice)) {
        sanitized.originalRetailPrice = inputs.originalRetailPrice;
        // Don't set hasValidPricing - this is supplementary
      } else {
        warnings.push(`originalRetailPrice is invalid, rejecting`);
      }
    }

    // BrickLink avg price
    if (inputs.bricklinkAvgPrice !== undefined) {
      if (this.isValidPrice(inputs.bricklinkAvgPrice)) {
        sanitized.bricklinkAvgPrice = inputs.bricklinkAvgPrice;
        hasValidPricing = true;
      } else {
        warnings.push(`bricklinkAvgPrice is invalid, rejecting`);
      }
    }

    // BrickLink max price (supplementary)
    if (inputs.bricklinkMaxPrice !== undefined) {
      if (this.isValidPrice(inputs.bricklinkMaxPrice)) {
        sanitized.bricklinkMaxPrice = inputs.bricklinkMaxPrice;
      } else {
        warnings.push(`bricklinkMaxPrice is invalid, rejecting`);
      }
    }

    // Historical prices
    if (inputs.historicalPriceData && inputs.historicalPriceData.length > 0) {
      const validPrices = inputs.historicalPriceData.filter((p) =>
        this.isValidPrice(p)
      );
      if (validPrices.length > 0) {
        sanitized.historicalPriceData = validPrices;
      }
      if (validPrices.length < inputs.historicalPriceData.length) {
        warnings.push(
          `${inputs.historicalPriceData.length - validPrices.length} historical prices rejected as invalid`,
        );
      }
    }

    return hasValidPricing;
  }

  /**
   * Validate score fields (demandScore, qualityScore, availabilityScore)
   */
  private static validateScores(
    inputs: IntrinsicValueInputs,
    sanitized: Partial<IntrinsicValueInputs>,
    warnings: string[],
    missingOptional: string[],
    sanitize: boolean,
  ): void {
    const scoreFields = [
      "demandScore",
      "qualityScore",
      "availabilityScore",
    ] as const;

    for (const field of scoreFields) {
      const value = inputs[field];

      if (value === undefined) {
        missingOptional.push(field);
        continue;
      }

      if (this.isValidScore(value)) {
        sanitized[field] = value;
      } else if (sanitize) {
        // Clamp to valid range
        const clamped = Math.max(
          BOUNDS.SCORE.MIN,
          Math.min(BOUNDS.SCORE.MAX, value),
        );
        sanitized[field] = clamped;
        warnings.push(
          `${field}=${value} is out of range (0-100), clamping to ${clamped}`,
        );
      } else {
        warnings.push(`${field}=${value} is out of range (0-100)`);
      }
    }
  }

  /**
   * Validate market/demand data
   */
  private static validateMarketData(
    inputs: IntrinsicValueInputs,
    sanitized: Partial<IntrinsicValueInputs>,
    warnings: string[],
    missingOptional: string[],
    sanitize: boolean,
  ): void {
    // Sales velocity
    if (inputs.salesVelocity !== undefined) {
      if (this.isValidSalesVelocity(inputs.salesVelocity)) {
        sanitized.salesVelocity = inputs.salesVelocity;
      } else if (sanitize && inputs.salesVelocity < 0) {
        sanitized.salesVelocity = 0;
        warnings.push(
          `salesVelocity=${inputs.salesVelocity} is negative, clamping to 0`,
        );
      } else if (sanitize) {
        warnings.push(
          `salesVelocity=${inputs.salesVelocity} exceeds maximum (${BOUNDS.SALES_VELOCITY.MAX}), rejecting as unrealistic`,
        );
      } else {
        warnings.push(`salesVelocity is invalid`);
      }
    } else if (!inputs.avgDaysBetweenSales) {
      missingOptional.push("liquidity metrics (salesVelocity or avgDaysBetweenSales)");
    }

    // Times sold
    if (inputs.timesSold !== undefined) {
      if (inputs.timesSold >= 0) {
        sanitized.timesSold = inputs.timesSold;
      } else if (sanitize) {
        sanitized.timesSold = 0;
        warnings.push(`timesSold=${inputs.timesSold} is negative, clamping to 0`);
      }
    }

    // Available lots
    if (inputs.availableLots !== undefined) {
      if (this.isValidAvailability(inputs.availableLots, BOUNDS.AVAILABLE_LOTS)) {
        sanitized.availableLots = inputs.availableLots;
      } else if (sanitize && inputs.availableLots < 0) {
        sanitized.availableLots = 0;
        warnings.push(
          `availableLots=${inputs.availableLots} is negative, clamping to 0`,
        );
      } else if (sanitize) {
        sanitized.availableLots = BOUNDS.AVAILABLE_LOTS.MAX;
        warnings.push(
          `availableLots=${inputs.availableLots} exceeds maximum, clamping to ${BOUNDS.AVAILABLE_LOTS.MAX}`,
        );
      }
    } else if (!inputs.availableQty) {
      missingOptional.push("saturation metrics (availableLots or availableQty)");
    }

    // Available quantity
    if (inputs.availableQty !== undefined) {
      if (this.isValidAvailability(inputs.availableQty, BOUNDS.AVAILABLE_QTY)) {
        sanitized.availableQty = inputs.availableQty;
      } else if (sanitize && inputs.availableQty < 0) {
        sanitized.availableQty = 0;
        warnings.push(
          `availableQty=${inputs.availableQty} is negative, clamping to 0`,
        );
      } else if (sanitize) {
        sanitized.availableQty = BOUNDS.AVAILABLE_QTY.MAX;
        warnings.push(
          `availableQty=${inputs.availableQty} exceeds maximum, clamping to ${BOUNDS.AVAILABLE_QTY.MAX}`,
        );
      }
    }

    // Volatility metrics (just pass through, no strict validation)
    if (inputs.priceVolatility !== undefined) {
      sanitized.priceVolatility = inputs.priceVolatility;
    }
    if (inputs.priceDecline !== undefined) {
      sanitized.priceDecline = inputs.priceDecline;
    }
    if (inputs.priceTrend !== undefined) {
      sanitized.priceTrend = inputs.priceTrend;
    }
    if (inputs.avgDaysBetweenSales !== undefined) {
      sanitized.avgDaysBetweenSales = inputs.avgDaysBetweenSales;
    }
  }

  /**
   * Validate product/quality data
   */
  private static validateProductData(
    inputs: IntrinsicValueInputs,
    sanitized: Partial<IntrinsicValueInputs>,
    warnings: string[],
    missingOptional: string[],
    sanitize: boolean,
  ): void {
    // Theme (just pass through)
    if (inputs.theme !== undefined) {
      sanitized.theme = inputs.theme;
    }

    // Parts count
    if (inputs.partsCount !== undefined) {
      if (this.isValidPartsCount(inputs.partsCount)) {
        sanitized.partsCount = inputs.partsCount;
      } else if (sanitize && inputs.partsCount < BOUNDS.PARTS_COUNT.MIN) {
        warnings.push(
          `partsCount=${inputs.partsCount} is below minimum (${BOUNDS.PARTS_COUNT.MIN}), rejecting`,
        );
      } else if (sanitize) {
        warnings.push(
          `partsCount=${inputs.partsCount} exceeds maximum (${BOUNDS.PARTS_COUNT.MAX}), rejecting as outlier`,
        );
      }
    }
  }

  /**
   * Validate retirement data
   */
  private static validateRetirementData(
    inputs: IntrinsicValueInputs,
    sanitized: Partial<IntrinsicValueInputs>,
    warnings: string[],
    missingOptional: string[],
    sanitize: boolean,
  ): void {
    // Retirement status (just pass through)
    if (inputs.retirementStatus !== undefined) {
      sanitized.retirementStatus = inputs.retirementStatus;
    }

    // Years post retirement
    if (inputs.yearsPostRetirement !== undefined) {
      if (
        inputs.yearsPostRetirement >= BOUNDS.YEARS_POST_RETIREMENT.MIN &&
        inputs.yearsPostRetirement <= BOUNDS.YEARS_POST_RETIREMENT.MAX
      ) {
        sanitized.yearsPostRetirement = inputs.yearsPostRetirement;
      } else if (sanitize && inputs.yearsPostRetirement < 0) {
        sanitized.yearsPostRetirement = 0;
        warnings.push(
          `yearsPostRetirement=${inputs.yearsPostRetirement} is negative, clamping to 0`,
        );
      } else if (sanitize) {
        sanitized.yearsPostRetirement = BOUNDS.YEARS_POST_RETIREMENT.MAX;
        warnings.push(
          `yearsPostRetirement=${inputs.yearsPostRetirement} exceeds maximum, clamping to ${BOUNDS.YEARS_POST_RETIREMENT.MAX}`,
        );
      }
    }

    // Year released
    if (inputs.yearReleased !== undefined) {
      if (
        inputs.yearReleased >= BOUNDS.YEAR.MIN &&
        inputs.yearReleased <= BOUNDS.YEAR.MAX
      ) {
        sanitized.yearReleased = inputs.yearReleased;
      } else if (sanitize) {
        warnings.push(
          `yearReleased=${inputs.yearReleased} is invalid (${BOUNDS.YEAR.MIN}-${BOUNDS.YEAR.MAX}), rejecting`,
        );
      }
    }
  }

  /**
   * Helper: Check if price is valid
   */
  private static isValidPrice(price: Cents | number): boolean {
    return price >= BOUNDS.PRICE.MIN && price <= BOUNDS.PRICE.MAX;
  }

  /**
   * Helper: Check if score is valid (0-100)
   */
  private static isValidScore(score: number): boolean {
    return score >= BOUNDS.SCORE.MIN && score <= BOUNDS.SCORE.MAX;
  }

  /**
   * Helper: Check if sales velocity is valid
   */
  private static isValidSalesVelocity(velocity: number): boolean {
    return velocity >= BOUNDS.SALES_VELOCITY.MIN &&
      velocity <= BOUNDS.SALES_VELOCITY.MAX;
  }

  /**
   * Helper: Check if availability count is valid
   */
  private static isValidAvailability(
    value: number,
    bounds: { MIN: number; MAX: number },
  ): boolean {
    return value >= bounds.MIN && value <= bounds.MAX;
  }

  /**
   * Helper: Check if parts count is valid
   */
  private static isValidPartsCount(count: number): boolean {
    return count >= BOUNDS.PARTS_COUNT.MIN && count <= BOUNDS.PARTS_COUNT.MAX;
  }
}
