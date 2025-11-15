/**
 * DataValidator Service
 *
 * Sanitizes and validates input data for DemandCalculator and QualityCalculator
 * Handles edge cases:
 * - Negative values
 * - Extreme outliers (bubble pricing)
 * - Missing/null data
 * - Invalid ranges
 *
 * Principles:
 * - Fail gracefully: return sanitized data or null, never throw
 * - Conservative bounds: reject extreme outliers to prevent score manipulation
 * - Document decisions: explain why data was rejected/clamped
 */

import type { DemandCalculatorInput } from "./DemandCalculator.ts";
import type { QualityCalculatorInput } from "./QualityCalculator.ts";

/**
 * Validation result with sanitized data and warnings
 */
export interface ValidationResult<T> {
  isValid: boolean;
  data: T | null;
  warnings: string[];
}

/**
 * Validation configuration
 */
const VALIDATION_CONFIG = {
  // Sales velocity bounds (transactions per day)
  SALES_VELOCITY: {
    MIN: 0,
    MAX: 10, // > 10 sales/day is unrealistic for LEGO aftermarket
  },

  // Time sold bounds
  TIMES_SOLD: {
    MIN: 0,
    MAX: 10000, // > 10k sales in 180 days is suspicious
  },

  // Observation period bounds (days)
  OBSERVATION_DAYS: {
    MIN: 7, // Need at least 1 week of data
    MAX: 730, // 2 years max
  },

  // Price bounds (cents)
  PRICE: {
    MIN: 100, // $1 minimum
    MAX: 10000000, // $100k maximum (UCS sets can be expensive)
  },

  // Availability bounds
  AVAILABLE_LOTS: {
    MIN: 0,
    MAX: 5000, // > 5000 sellers is unrealistic
  },

  AVAILABLE_QTY: {
    MIN: 0,
    MAX: 50000, // > 50k units is unrealistic
  },

  // Parts count bounds
  PARTS_COUNT: {
    MIN: 1,
    MAX: 20000, // Largest sets ~11k pieces, allow buffer
  },

  // MSRP bounds (cents)
  MSRP: {
    MIN: 100, // $1 minimum
    MAX: 10000000, // $100k maximum
  },
};

export class DataValidator {
  /**
   * Validate and sanitize DemandCalculator input
   */
  static validateDemandInput(
    input: DemandCalculatorInput,
  ): ValidationResult<DemandCalculatorInput> {
    const warnings: string[] = [];
    const sanitized: Partial<DemandCalculatorInput> = {};

    // Validate timesSold
    if (input.timesSold !== undefined && input.timesSold !== null) {
      if (input.timesSold < VALIDATION_CONFIG.TIMES_SOLD.MIN) {
        warnings.push(`timesSold=${input.timesSold} is negative, clamping to 0`);
        sanitized.timesSold = 0;
      } else if (input.timesSold > VALIDATION_CONFIG.TIMES_SOLD.MAX) {
        warnings.push(
          `timesSold=${input.timesSold} exceeds maximum (${VALIDATION_CONFIG.TIMES_SOLD.MAX}), rejecting as outlier`,
        );
        // Don't include timesSold in sanitized data
      } else {
        sanitized.timesSold = input.timesSold;
      }
    }

    // Validate observationDays
    if (input.observationDays !== undefined && input.observationDays !== null) {
      if (input.observationDays < VALIDATION_CONFIG.OBSERVATION_DAYS.MIN) {
        warnings.push(
          `observationDays=${input.observationDays} is too short (min ${VALIDATION_CONFIG.OBSERVATION_DAYS.MIN}), rejecting`,
        );
        return { isValid: false, data: null, warnings };
      } else if (input.observationDays > VALIDATION_CONFIG.OBSERVATION_DAYS.MAX) {
        warnings.push(
          `observationDays=${input.observationDays} exceeds maximum (${VALIDATION_CONFIG.OBSERVATION_DAYS.MAX}), clamping`,
        );
        sanitized.observationDays = VALIDATION_CONFIG.OBSERVATION_DAYS.MAX;
      } else {
        sanitized.observationDays = input.observationDays;
      }
    }

    // Validate salesVelocity
    if (input.salesVelocity !== undefined && input.salesVelocity !== null) {
      if (input.salesVelocity < VALIDATION_CONFIG.SALES_VELOCITY.MIN) {
        warnings.push(`salesVelocity=${input.salesVelocity} is negative, clamping to 0`);
        sanitized.salesVelocity = 0;
      } else if (input.salesVelocity > VALIDATION_CONFIG.SALES_VELOCITY.MAX) {
        warnings.push(
          `salesVelocity=${input.salesVelocity} exceeds maximum (${VALIDATION_CONFIG.SALES_VELOCITY.MAX}), rejecting as outlier`,
        );
        // Don't include salesVelocity in sanitized data
      } else {
        sanitized.salesVelocity = input.salesVelocity;
      }
    }

    // Validate prices
    const priceFields = ["currentPrice", "firstPrice", "lastPrice"] as const;
    for (const field of priceFields) {
      const value = input[field];
      if (value !== undefined && value !== null) {
        if (value < VALIDATION_CONFIG.PRICE.MIN) {
          warnings.push(`${field}=${value} is below minimum ($${VALIDATION_CONFIG.PRICE.MIN / 100}), rejecting`);
          // Don't include in sanitized data
        } else if (value > VALIDATION_CONFIG.PRICE.MAX) {
          warnings.push(
            `${field}=${value} exceeds maximum ($${VALIDATION_CONFIG.PRICE.MAX / 100}), rejecting as bubble pricing`,
          );
          // Don't include in sanitized data
        } else {
          sanitized[field] = value;
        }
      }
    }

    // Validate availableLots
    if (input.availableLots !== undefined && input.availableLots !== null) {
      if (input.availableLots < VALIDATION_CONFIG.AVAILABLE_LOTS.MIN) {
        warnings.push(`availableLots=${input.availableLots} is negative, clamping to 0`);
        sanitized.availableLots = 0;
      } else if (input.availableLots > VALIDATION_CONFIG.AVAILABLE_LOTS.MAX) {
        warnings.push(
          `availableLots=${input.availableLots} exceeds maximum (${VALIDATION_CONFIG.AVAILABLE_LOTS.MAX}), clamping`,
        );
        sanitized.availableLots = VALIDATION_CONFIG.AVAILABLE_LOTS.MAX;
      } else {
        sanitized.availableLots = input.availableLots;
      }
    }

    // Validate availableQty
    if (input.availableQty !== undefined && input.availableQty !== null) {
      if (input.availableQty < VALIDATION_CONFIG.AVAILABLE_QTY.MIN) {
        warnings.push(`availableQty=${input.availableQty} is negative, clamping to 0`);
        sanitized.availableQty = 0;
      } else if (input.availableQty > VALIDATION_CONFIG.AVAILABLE_QTY.MAX) {
        warnings.push(
          `availableQty=${input.availableQty} exceeds maximum (${VALIDATION_CONFIG.AVAILABLE_QTY.MAX}), clamping`,
        );
        sanitized.availableQty = VALIDATION_CONFIG.AVAILABLE_QTY.MAX;
      } else {
        sanitized.availableQty = input.availableQty;
      }
    }

    // Check if we have enough data to proceed
    const hasMinimumData =
      sanitized.timesSold !== undefined ||
      sanitized.salesVelocity !== undefined ||
      sanitized.availableLots !== undefined;

    if (!hasMinimumData) {
      warnings.push("Insufficient data after validation: need at least timesSold, salesVelocity, or availableLots");
      return { isValid: false, data: null, warnings };
    }

    return {
      isValid: true,
      data: sanitized as DemandCalculatorInput,
      warnings,
    };
  }

  /**
   * Validate and sanitize QualityCalculator input
   */
  static validateQualityInput(
    input: QualityCalculatorInput,
  ): ValidationResult<QualityCalculatorInput> {
    const warnings: string[] = [];
    const sanitized: Partial<QualityCalculatorInput> = {};

    // Validate partsCount
    if (input.partsCount !== undefined && input.partsCount !== null) {
      if (input.partsCount < VALIDATION_CONFIG.PARTS_COUNT.MIN) {
        warnings.push(`partsCount=${input.partsCount} is below minimum (1), rejecting`);
        // Don't include in sanitized data
      } else if (input.partsCount > VALIDATION_CONFIG.PARTS_COUNT.MAX) {
        warnings.push(
          `partsCount=${input.partsCount} exceeds maximum (${VALIDATION_CONFIG.PARTS_COUNT.MAX}), rejecting as outlier`,
        );
        // Don't include in sanitized data
      } else {
        sanitized.partsCount = input.partsCount;
      }
    }

    // Validate MSRP
    if (input.msrp !== undefined && input.msrp !== null) {
      if (input.msrp < VALIDATION_CONFIG.MSRP.MIN) {
        warnings.push(`msrp=${input.msrp} is below minimum ($${VALIDATION_CONFIG.MSRP.MIN / 100}), rejecting`);
        // Don't include in sanitized data
      } else if (input.msrp > VALIDATION_CONFIG.MSRP.MAX) {
        warnings.push(
          `msrp=${input.msrp} exceeds maximum ($${VALIDATION_CONFIG.MSRP.MAX / 100}), rejecting as bubble pricing`,
        );
        // Don't include in sanitized data
      } else {
        sanitized.msrp = input.msrp;
      }
    }

    // Validate theme (just pass through, no validation needed)
    if (input.theme !== undefined && input.theme !== null) {
      sanitized.theme = input.theme;
    }

    // Validate availableLots (same as demand)
    if (input.availableLots !== undefined && input.availableLots !== null) {
      if (input.availableLots < VALIDATION_CONFIG.AVAILABLE_LOTS.MIN) {
        warnings.push(`availableLots=${input.availableLots} is negative, clamping to 0`);
        sanitized.availableLots = 0;
      } else if (input.availableLots > VALIDATION_CONFIG.AVAILABLE_LOTS.MAX) {
        warnings.push(
          `availableLots=${input.availableLots} exceeds maximum (${VALIDATION_CONFIG.AVAILABLE_LOTS.MAX}), clamping`,
        );
        sanitized.availableLots = VALIDATION_CONFIG.AVAILABLE_LOTS.MAX;
      } else {
        sanitized.availableLots = input.availableLots;
      }
    }

    // Validate availableQty (same as demand)
    if (input.availableQty !== undefined && input.availableQty !== null) {
      if (input.availableQty < VALIDATION_CONFIG.AVAILABLE_QTY.MIN) {
        warnings.push(`availableQty=${input.availableQty} is negative, clamping to 0`);
        sanitized.availableQty = 0;
      } else if (input.availableQty > VALIDATION_CONFIG.AVAILABLE_QTY.MAX) {
        warnings.push(
          `availableQty=${input.availableQty} exceeds maximum (${VALIDATION_CONFIG.AVAILABLE_QTY.MAX}), clamping`,
        );
        sanitized.availableQty = VALIDATION_CONFIG.AVAILABLE_QTY.MAX;
      } else {
        sanitized.availableQty = input.availableQty;
      }
    }

    // Validate optional fields (year released/retired, limited edition)
    if (input.yearReleased !== undefined && input.yearReleased !== null) {
      if (input.yearReleased < 1949 || input.yearReleased > new Date().getFullYear() + 1) {
        warnings.push(`yearReleased=${input.yearReleased} is invalid, rejecting`);
      } else {
        sanitized.yearReleased = input.yearReleased;
      }
    }

    if (input.yearRetired !== undefined && input.yearRetired !== null) {
      if (input.yearRetired < 1949 || input.yearRetired > new Date().getFullYear() + 10) {
        warnings.push(`yearRetired=${input.yearRetired} is invalid, rejecting`);
      } else {
        sanitized.yearRetired = input.yearRetired;
      }
    }

    if (input.limitedEdition !== undefined && input.limitedEdition !== null) {
      sanitized.limitedEdition = input.limitedEdition;
    }

    // Check if we have enough data to proceed
    const hasMinimumData = sanitized.partsCount !== undefined || sanitized.theme !== undefined;

    if (!hasMinimumData) {
      warnings.push("Insufficient data after validation: need at least partsCount or theme");
      return { isValid: false, data: null, warnings };
    }

    return {
      isValid: true,
      data: sanitized as QualityCalculatorInput,
      warnings,
    };
  }

  /**
   * Detect if price data represents a bubble (extreme outlier)
   * Returns true if prices should be rejected
   */
  static detectPriceBubble(
    currentPrice?: number,
    firstPrice?: number,
    lastPrice?: number,
  ): { isBubble: boolean; reason?: string } {
    if (!currentPrice || !firstPrice || !lastPrice) {
      return { isBubble: false };
    }

    // Check for 10x or more price increase
    if (currentPrice > firstPrice * 10) {
      return {
        isBubble: true,
        reason: `Current price (${currentPrice}) is 10x+ higher than first price (${firstPrice})`,
      };
    }

    // Check for extreme volatility (price swings > 500%)
    const priceRange = Math.max(currentPrice, firstPrice, lastPrice) -
      Math.min(currentPrice, firstPrice, lastPrice);
    const avgPrice = (currentPrice + firstPrice + lastPrice) / 3;
    const volatility = priceRange / avgPrice;

    if (volatility > 5) {
      return {
        isBubble: true,
        reason: `Extreme price volatility (${(volatility * 100).toFixed(0)}%) suggests data quality issues`,
      };
    }

    return { isBubble: false };
  }

  /**
   * Detect if supply data is realistic
   * Returns true if data should be rejected
   */
  static detectUnrealisticSupply(
    availableLots?: number,
    availableQty?: number,
  ): { isUnrealistic: boolean; reason?: string } {
    if (!availableLots || !availableQty) {
      return { isUnrealistic: false };
    }

    // Average qty per lot
    const avgQtyPerLot = availableQty / availableLots;

    // If average is > 100 units per seller, likely data error
    if (avgQtyPerLot > 100) {
      return {
        isUnrealistic: true,
        reason: `Average ${avgQtyPerLot.toFixed(0)} units per lot is unrealistic`,
      };
    }

    // If we have lots but zero qty, data error
    if (availableLots > 0 && availableQty === 0) {
      return {
        isUnrealistic: true,
        reason: "Non-zero lots but zero quantity is invalid",
      };
    }

    return { isUnrealistic: false };
  }
}
