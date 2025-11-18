/**
 * IntrinsicValueInputMapper - Centralized data transformation
 *
 * ELIMINATES DUPLICATION by consolidating all transformations from:
 * - RecommendationEngine (lines 184-212)
 * - ValueInvestingService (lines 146-221)
 * - Various other services
 *
 * SOLID Principles:
 * - Single Responsibility: Only maps data to IntrinsicValueInputs
 * - Open/Closed: Easy to extend with new mappings
 * - Dependency Inversion: Depends on abstract interfaces
 *
 * DRY Principle:
 * - Single source of truth for all value input transformations
 * - Eliminates scattered mapping logic
 */

import type { IntrinsicValueInputs } from "../../../types/value-investing.ts";
import type { Cents } from "../../../types/price.ts";

/**
 * Source data for mapping
 * Flexible interface that accepts data from various sources
 */
export interface ValueInputSourceData {
  // Pricing data
  pricing?: {
    msrp?: Cents;
    originalRetailPrice?: Cents;
    currentRetailPrice?: Cents;
    bricklinkCurrentNewAvg?: Cents;
    bricklinkCurrentNewMax?: Cents;
    bricklinkSixMonthNewAvg?: Cents;
    historicalPrices?: Cents[];
  };

  // Retirement data
  retirement?: {
    status?: "active" | "retiring_soon" | "retired";
    yearsPostRetirement?: number;
    yearReleased?: number;
    yearRetired?: number;
  };

  // Market/demand data
  market?: {
    salesVelocity?: number;
    avgDaysBetweenSales?: number;
    timesSold?: number;
    priceVolatility?: number;
    priceDecline?: number;
    priceTrend?: number;
    availableQty?: number;
    availableLots?: number;
  };

  // Quality/product data
  product?: {
    theme?: string;
    partsCount?: number;
  };

  // Pre-calculated scores (from analyzers/scorers)
  scores?: {
    demandScore?: number;
    qualityScore?: number;
    availabilityScore?: number;
  };
}

/**
 * Mapping options
 */
export interface MappingOptions {
  /**
   * Prefer certain data sources over others
   */
  preferMsrpOverRetail?: boolean; // Default: true

  /**
   * Include optional fields even if undefined
   */
  includeOptionalFields?: boolean; // Default: false

  /**
   * Fallback values for missing critical data
   */
  fallbacks?: Partial<IntrinsicValueInputs>;
}

/**
 * IntrinsicValueInputMapper - Pure mapping service
 * No side effects, deterministic transformations
 */
export class IntrinsicValueInputMapper {
  /**
   * Map source data to IntrinsicValueInputs
   *
   * This is the PRIMARY mapping function used throughout the codebase
   */
  static map(
    source: ValueInputSourceData,
    options: MappingOptions = {},
  ): IntrinsicValueInputs {
    const {
      preferMsrpOverRetail = true,
      includeOptionalFields = false,
      fallbacks = {},
    } = options;

    // Build the mapped object
    const mapped: IntrinsicValueInputs = {};

    // ===== PRICING MAPPING =====
    if (source.pricing) {
      const { pricing } = source;

      // MSRP (highest priority for intrinsic value)
      if (pricing.msrp !== undefined) {
        mapped.msrp = pricing.msrp;
      } else if (pricing.originalRetailPrice !== undefined && preferMsrpOverRetail) {
        mapped.msrp = pricing.originalRetailPrice;
      }

      // Current retail price
      if (pricing.currentRetailPrice !== undefined) {
        mapped.currentRetailPrice = pricing.currentRetailPrice;
      }

      // Original retail price (for deal quality analysis)
      if (pricing.originalRetailPrice !== undefined) {
        mapped.originalRetailPrice = pricing.originalRetailPrice;
      }

      // BrickLink pricing (for comparison, not base value)
      if (pricing.bricklinkCurrentNewAvg !== undefined || includeOptionalFields) {
        mapped.bricklinkAvgPrice = pricing.bricklinkCurrentNewAvg;
      }

      if (pricing.bricklinkCurrentNewMax !== undefined || includeOptionalFields) {
        mapped.bricklinkMaxPrice = pricing.bricklinkCurrentNewMax;
      }

      // Historical prices for volatility analysis
      if (pricing.historicalPrices && pricing.historicalPrices.length > 0) {
        mapped.historicalPriceData = pricing.historicalPrices;
      }
    }

    // ===== RETIREMENT MAPPING =====
    if (source.retirement) {
      const { retirement } = source;

      if (retirement.status) {
        mapped.retirementStatus = retirement.status;
      }

      if (retirement.yearsPostRetirement !== undefined) {
        mapped.yearsPostRetirement = retirement.yearsPostRetirement;
      }

      if (retirement.yearReleased !== undefined) {
        mapped.yearReleased = retirement.yearReleased;
      }
    }

    // ===== MARKET/DEMAND MAPPING =====
    if (source.market) {
      const { market } = source;

      // Liquidity metrics
      if (market.salesVelocity !== undefined || includeOptionalFields) {
        mapped.salesVelocity = market.salesVelocity;
      }

      if (market.avgDaysBetweenSales !== undefined || includeOptionalFields) {
        mapped.avgDaysBetweenSales = market.avgDaysBetweenSales;
      }

      if (market.timesSold !== undefined || includeOptionalFields) {
        mapped.timesSold = market.timesSold;
      }

      // Volatility metrics
      if (market.priceVolatility !== undefined || includeOptionalFields) {
        mapped.priceVolatility = market.priceVolatility;
      }

      if (market.priceDecline !== undefined || includeOptionalFields) {
        mapped.priceDecline = market.priceDecline;
      }

      if (market.priceTrend !== undefined || includeOptionalFields) {
        mapped.priceTrend = market.priceTrend;
      }

      // Saturation metrics
      if (market.availableQty !== undefined || includeOptionalFields) {
        mapped.availableQty = market.availableQty;
      }

      if (market.availableLots !== undefined || includeOptionalFields) {
        mapped.availableLots = market.availableLots;
      }
    }

    // ===== PRODUCT/QUALITY MAPPING =====
    if (source.product) {
      const { product } = source;

      if (product.theme) {
        mapped.theme = product.theme;
      }

      if (product.partsCount !== undefined) {
        mapped.partsCount = product.partsCount;
      }
    }

    // ===== SCORES MAPPING =====
    if (source.scores) {
      const { scores } = source;

      if (scores.demandScore !== undefined) {
        mapped.demandScore = scores.demandScore;
      }

      if (scores.qualityScore !== undefined) {
        mapped.qualityScore = scores.qualityScore;
      }

      if (scores.availabilityScore !== undefined) {
        mapped.availabilityScore = scores.availabilityScore;
      }
    }

    // ===== APPLY FALLBACKS =====
    return { ...fallbacks, ...mapped };
  }

  /**
   * Map from legacy ProductAnalysisInput format
   * Commonly used in RecommendationEngine
   */
  static fromAnalysisInput(input: {
    pricing: {
      originalRetailPrice?: Cents;
      currentRetailPrice?: Cents;
      bricklink?: {
        current: {
          newAvg?: Cents;
          newMax?: Cents;
        };
      };
    };
    demand: {
      bricklinkSalesVelocity?: number;
      bricklinkAvgDaysBetweenSales?: number;
      bricklinkSixMonthNewTimesSold?: number;
      bricklinkTimesSold?: number;
      bricklinkPriceVolatility?: number;
      bricklinkCurrentNewQty?: number;
      bricklinkCurrentNewLots?: number;
    };
    availability: {
      yearReleased?: number;
    };
    quality: {
      theme?: string;
      partsCount?: number;
    };
  }, scores?: {
    demandScore?: number;
    qualityScore?: number;
    availabilityScore?: number;
  }, retirement?: {
    status?: "active" | "retiring_soon" | "retired";
    yearsPostRetirement?: number;
  }): IntrinsicValueInputs {
    return this.map({
      pricing: {
        msrp: input.pricing.originalRetailPrice,
        originalRetailPrice: input.pricing.originalRetailPrice,
        currentRetailPrice: input.pricing.currentRetailPrice,
        bricklinkCurrentNewAvg: input.pricing.bricklink?.current.newAvg,
        bricklinkCurrentNewMax: input.pricing.bricklink?.current.newMax,
      },
      retirement: {
        status: retirement?.status,
        yearsPostRetirement: retirement?.yearsPostRetirement,
        yearReleased: input.availability.yearReleased,
      },
      market: {
        salesVelocity: input.demand.bricklinkSalesVelocity,
        avgDaysBetweenSales: input.demand.bricklinkAvgDaysBetweenSales,
        timesSold: input.demand.bricklinkSixMonthNewTimesSold || input.demand.bricklinkTimesSold,
        priceVolatility: input.demand.bricklinkPriceVolatility,
        availableQty: input.demand.bricklinkCurrentNewQty,
        availableLots: input.demand.bricklinkCurrentNewLots,
      },
      product: {
        theme: input.quality.theme,
        partsCount: input.quality.partsCount,
      },
      scores: scores,
    });
  }

  /**
   * Validate that critical fields are present
   * Returns validation result with missing fields
   */
  static validate(inputs: IntrinsicValueInputs): {
    isValid: boolean;
    missingCritical: string[];
    missingOptional: string[];
  } {
    const missingCritical: string[] = [];
    const missingOptional: string[] = [];

    // Critical: At least one base value source
    if (!inputs.msrp && !inputs.currentRetailPrice && !inputs.bricklinkAvgPrice) {
      missingCritical.push("pricing (need msrp, currentRetailPrice, or bricklinkAvgPrice)");
    }

    // Optional but recommended
    if (!inputs.demandScore) missingOptional.push("demandScore");
    if (!inputs.qualityScore) missingOptional.push("qualityScore");
    if (!inputs.salesVelocity && !inputs.avgDaysBetweenSales) {
      missingOptional.push("liquidity metrics");
    }
    if (!inputs.availableQty && !inputs.availableLots) {
      missingOptional.push("saturation metrics");
    }

    return {
      isValid: missingCritical.length === 0,
      missingCritical,
      missingOptional,
    };
  }
}
