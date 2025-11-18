/**
 * DataQualityValidator - Pabrai-style "Circle of Competence" Data Quality Gates
 *
 * Philosophy: Only calculate intrinsic value when we have sufficient data to be confident.
 * Better to say "INSUFFICIENT DATA" than to give a false sense of precision.
 *
 * Inspired by Mohnish Pabrai's principle: Only invest within your circle of competence.
 */

import type {
  EnrichedBricklinkData,
  EnrichedWorldBricksData,
} from "./types.ts";

export interface DataQualityResult {
  /** Can we proceed with valuation? */
  canCalculate: boolean;
  /** Overall data quality score (0-100) */
  qualityScore: number;
  /** Confidence level: HIGH (80-100), MEDIUM (50-79), LOW (0-49) */
  confidenceLevel: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT";
  /** What critical data is missing? */
  missingCriticalData: string[];
  /** What optional data is missing? */
  missingOptionalData: string[];
  /** Detailed breakdown by category */
  breakdown: {
    pricingData: { score: number; issues: string[] };
    salesData: { score: number; issues: string[] };
    marketData: { score: number; issues: string[] };
    productData: { score: number; issues: string[] };
  };
  /** Human-readable explanation */
  explanation: string;
}

export class DataQualityValidator {
  /**
   * Validate if we have sufficient data to calculate intrinsic value
   */
  static validate(
    bricklinkData: EnrichedBricklinkData | null,
    worldBricksData: EnrichedWorldBricksData | null,
  ): DataQualityResult {
    const missingCriticalData: string[] = [];
    const missingOptionalData: string[] = [];

    // Validate pricing data
    const pricingValidation = this.validatePricingData(
      bricklinkData,
      worldBricksData,
    );
    if (pricingValidation.critical.length > 0) {
      missingCriticalData.push(...pricingValidation.critical);
    }
    missingOptionalData.push(...pricingValidation.optional);

    // Validate sales data
    const salesValidation = this.validateSalesData(bricklinkData);
    if (salesValidation.critical.length > 0) {
      missingCriticalData.push(...salesValidation.critical);
    }
    missingOptionalData.push(...salesValidation.optional);

    // Validate market data
    const marketValidation = this.validateMarketData(bricklinkData);
    if (marketValidation.critical.length > 0) {
      missingCriticalData.push(...marketValidation.critical);
    }
    missingOptionalData.push(...marketValidation.optional);

    // Validate product data
    const productValidation = this.validateProductData(worldBricksData);
    if (productValidation.critical.length > 0) {
      missingCriticalData.push(...productValidation.critical);
    }
    missingOptionalData.push(...productValidation.optional);

    // Calculate scores
    const pricingScore = pricingValidation.score;
    const salesScore = salesValidation.score;
    const marketScore = marketValidation.score;
    const productScore = productValidation.score;

    // Weighted overall quality score
    const qualityScore = Math.round(
      pricingScore * 0.30 + // Pricing is critical (30%)
        salesScore * 0.35 + // Sales history is most critical (35%)
        marketScore * 0.25 + // Market depth is important (25%)
        productScore * 0.10, // Product data is helpful (10%)
    );

    // Determine if we can calculate
    const canCalculate = missingCriticalData.length === 0;

    // Determine confidence level
    let confidenceLevel: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT";
    if (!canCalculate) {
      confidenceLevel = "INSUFFICIENT";
    } else if (qualityScore >= 80) {
      confidenceLevel = "HIGH";
    } else if (qualityScore >= 50) {
      confidenceLevel = "MEDIUM";
    } else {
      confidenceLevel = "LOW";
    }

    // Generate explanation
    const explanation = this.generateExplanation(
      canCalculate,
      qualityScore,
      missingCriticalData,
      missingOptionalData,
    );

    return {
      canCalculate,
      qualityScore,
      confidenceLevel,
      missingCriticalData,
      missingOptionalData,
      breakdown: {
        pricingData: {
          score: pricingScore,
          issues: [...pricingValidation.critical, ...pricingValidation.optional],
        },
        salesData: {
          score: salesScore,
          issues: [...salesValidation.critical, ...salesValidation.optional],
        },
        marketData: {
          score: marketScore,
          issues: [...marketValidation.critical, ...marketValidation.optional],
        },
        productData: {
          score: productScore,
          issues: [...productValidation.critical, ...productValidation.optional],
        },
      },
      explanation,
    };
  }

  /**
   * Validate pricing data availability
   */
  private static validatePricingData(
    bricklinkData: EnrichedBricklinkData | null,
    worldBricksData: EnrichedWorldBricksData | null,
  ): { score: number; critical: string[]; optional: string[] } {
    const critical: string[] = [];
    const optional: string[] = [];
    let score = 0;

    // We need EITHER MSRP OR BrickLink pricing
    const hasMsrp = worldBricksData?.msrp != null &&
      worldBricksData.msrp > 0;
    const hasBricklinkPricing = bricklinkData?.avgPrice != null &&
      bricklinkData.avgPrice > 0;

    if (!hasMsrp && !hasBricklinkPricing) {
      critical.push("No base value available (need MSRP or BrickLink pricing)");
    } else {
      score += 40; // Base value available

      if (hasMsrp) {
        score += 30; // MSRP is preferred
      } else {
        optional.push("MSRP not available (using BrickLink prices instead)");
      }
    }

    // Historical pricing (optional but valuable)
    if (
      bricklinkData?.priceHistory && bricklinkData.priceHistory.length >= 3
    ) {
      score += 20; // Good price history
    } else if (
      bricklinkData?.priceHistory && bricklinkData.priceHistory.length > 0
    ) {
      score += 10; // Some price history
      optional.push("Limited price history (less than 3 months)");
    } else {
      optional.push("No price history available (cannot assess volatility)");
    }

    // Min/Max pricing for range
    if (bricklinkData?.minPrice && bricklinkData?.maxPrice) {
      score += 10;
    } else {
      optional.push("No min/max pricing (cannot assess price range)");
    }

    return { score: Math.min(100, score), critical, optional };
  }

  /**
   * Validate sales data availability - MOST CRITICAL for value investing
   */
  private static validateSalesData(
    bricklinkData: EnrichedBricklinkData | null,
  ): { score: number; critical: string[]; optional: string[] } {
    const critical: string[] = [];
    const optional: string[] = [];
    let score = 0;

    // Must have SOME sales data
    if (!bricklinkData) {
      critical.push("No BrickLink data available");
      return { score: 0, critical, optional };
    }

    const hasSalesVolume = bricklinkData.totalQty != null &&
      bricklinkData.totalQty > 0;
    const hasSalesCount = bricklinkData.timesSold != null &&
      bricklinkData.timesSold > 0;

    if (!hasSalesVolume && !hasSalesCount) {
      critical.push(
        "No sales data available (need sales history to assess demand)",
      );
    } else {
      score += 50; // Basic sales data exists

      // Sales velocity (critical for liquidity assessment)
      if (bricklinkData.salesVelocity != null) {
        score += 30;
      } else {
        critical.push("No sales velocity data (cannot assess liquidity)");
      }

      // Sales consistency (how many data points?)
      if (bricklinkData.timesSold != null && bricklinkData.timesSold >= 10) {
        score += 20; // Good sample size
      } else if (
        bricklinkData.timesSold != null && bricklinkData.timesSold >= 3
      ) {
        score += 10; // Minimal sample
        optional.push("Limited sales history (less than 10 transactions)");
      } else {
        optional.push(
          "Very limited sales history (cannot assess consistency)",
        );
      }
    }

    return { score: Math.min(100, score), critical, optional };
  }

  /**
   * Validate market depth data
   */
  private static validateMarketData(
    bricklinkData: EnrichedBricklinkData | null,
  ): { score: number; critical: string[]; optional: string[] } {
    const critical: string[] = [];
    const optional: string[] = [];
    let score = 0;

    if (!bricklinkData) {
      critical.push("No market data available");
      return { score: 0, critical, optional };
    }

    // Available quantity (critical for saturation analysis)
    if (
      bricklinkData.availableQty != null && bricklinkData.availableQty >= 0
    ) {
      score += 50;
    } else {
      critical.push(
        "No available quantity data (cannot assess market saturation)",
      );
    }

    // Number of sellers (important for competition assessment)
    if (bricklinkData.totalLots != null && bricklinkData.totalLots > 0) {
      score += 30;
    } else {
      optional.push("No seller count data (cannot assess competition)");
    }

    // Price distribution (helpful for volatility)
    if (bricklinkData.minPrice && bricklinkData.maxPrice) {
      score += 20;
    } else {
      optional.push("No price range data (cannot assess price stability)");
    }

    return { score: Math.min(100, score), critical, optional };
  }

  /**
   * Validate product metadata
   */
  private static validateProductData(
    worldBricksData: EnrichedWorldBricksData | null,
  ): { score: number; critical: string[]; optional: string[] } {
    const critical: string[] = [];
    const optional: string[] = [];
    let score = 50; // Product data is less critical

    if (!worldBricksData) {
      optional.push("No WorldBricks data (missing theme, retirement status)");
      return { score: 50, critical, optional }; // Not critical, default score
    }

    // Retirement status (helpful for value projection)
    if (worldBricksData.status) {
      score += 20;
    } else {
      optional.push("Retirement status unknown");
    }

    // Theme (helpful for theme multiplier)
    if (worldBricksData.theme) {
      score += 15;
    } else {
      optional.push("Theme unknown");
    }

    // Parts count (helpful for PPD calculation)
    if (worldBricksData.pieces != null && worldBricksData.pieces > 0) {
      score += 15;
    } else {
      optional.push("Parts count unknown");
    }

    return { score: Math.min(100, score), critical, optional };
  }

  /**
   * Generate human-readable explanation
   */
  private static generateExplanation(
    canCalculate: boolean,
    qualityScore: number,
    missingCriticalData: string[],
    missingOptionalData: string[],
  ): string {
    if (!canCalculate) {
      return `INSUFFICIENT DATA TO VALUE. Missing critical data: ${
        missingCriticalData.join(
          ", ",
        )
      }. We cannot calculate intrinsic value without this information.`;
    }

    if (qualityScore >= 80) {
      return `HIGH CONFIDENCE (${qualityScore}/100). We have comprehensive data to value this product accurately.`;
    } else if (qualityScore >= 50) {
      const warnings = missingOptionalData.length > 0
        ? ` Note: ${missingOptionalData.slice(0, 2).join("; ")}.`
        : "";
      return `MEDIUM CONFIDENCE (${qualityScore}/100). We have sufficient data to value this product, but some data is missing.${warnings}`;
    } else {
      return `LOW CONFIDENCE (${qualityScore}/100). Data quality is poor. Missing: ${
        missingOptionalData.slice(
          0,
          3,
        ).join(", ")
      }. Use this valuation with caution.`;
    }
  }

  /**
   * Helper: Get minimum required data quality score to show recommendations
   */
  static getMinimumQualityThreshold(): number {
    return 50; // Require at least MEDIUM confidence
  }

  /**
   * Helper: Should we show this valuation to users?
   */
  static shouldDisplayValuation(result: DataQualityResult): boolean {
    return result.canCalculate &&
      result.qualityScore >= this.getMinimumQualityThreshold();
  }
}
