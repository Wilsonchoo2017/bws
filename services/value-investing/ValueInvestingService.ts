/**
 * ValueInvestingService - Orchestrates value investing analysis
 *
 * Single Responsibility: Coordinates the value investing workflow
 * - Fetches products
 * - Runs analysis
 * - Calculates value metrics
 * - Filters opportunities
 *
 * Follows SOLID principles:
 * - SRP: Only handles value investing business logic
 * - DIP: Depends on abstractions (interfaces)
 * - OCP: Easy to extend with new strategies
 */

import type { Product } from "../../db/schema.ts";
import type { AnalysisService } from "../analysis/AnalysisService.ts";
import { ValueCalculator } from "./ValueCalculator.ts";
import type {
  IntrinsicValueInputs,
  ValueInvestingProduct,
} from "../../types/value-investing.ts";

/**
 * Type guard for retirement status
 */
function isRetirementStatus(
  value: unknown,
): value is "active" | "retiring_soon" | "retired" {
  return (
    value === "active" ||
    value === "retiring_soon" ||
    value === "retired"
  );
}

/**
 * Validate product has required fields
 */
function isValidProduct(product: Product): boolean {
  return !!(
    product.productId &&
    product.name &&
    product.price !== null &&
    product.price > 0 &&
    product.image &&
    product.currency
  );
}

interface ProcessingStats {
  totalProducts: number;
  includedOpportunities: number;
  skipped: {
    invalidProduct: number;
    noAnalysis: number;
    nullScore: number;
    notBuyable: number;
    noMarginOfSafety: number;
    calculationError: number;
  };
}

export class ValueInvestingService {
  private analysisService: AnalysisService;

  constructor(analysisService: AnalysisService) {
    this.analysisService = analysisService;
  }

  /**
   * Get value investing opportunities from a list of products
   * @param products - Products to analyze
   * @returns Value investing products and processing stats
   */
  async getValueOpportunities(
    products: Product[],
  ): Promise<{
    opportunities: ValueInvestingProduct[];
    stats: ProcessingStats;
  }> {
    const stats: ProcessingStats = {
      totalProducts: products.length,
      includedOpportunities: 0,
      skipped: {
        invalidProduct: 0,
        noAnalysis: 0,
        nullScore: 0,
        notBuyable: 0,
        noMarginOfSafety: 0,
        calculationError: 0,
      },
    };

    // Validate all products first
    const validProducts = products.filter((p) => {
      if (!isValidProduct(p)) {
        stats.skipped.invalidProduct++;
        console.debug(
          `[ValueInvestingService] Skipped product ${p.id}: invalid`,
        );
        return false;
      }
      return true;
    });

    if (validProducts.length === 0) {
      return { opportunities: [], stats };
    }

    // Run batch analysis
    const productIds = validProducts.map((p) => p.productId);
    const analysisResults = await this.analysisService.analyzeProducts(
      productIds,
    );

    // Transform to value investing products
    const opportunities: ValueInvestingProduct[] = [];

    for (const product of validProducts) {
      const valueProduct = this.transformToValueProduct(
        product,
        analysisResults,
        stats,
      );

      if (valueProduct) {
        opportunities.push(valueProduct);
      }
    }

    stats.includedOpportunities = opportunities.length;

    console.info("[ValueInvestingService] Processing complete:", {
      total: stats.totalProducts,
      included: stats.includedOpportunities,
      skipped: stats.skipped,
    });

    return { opportunities, stats };
  }

  /**
   * Transform a product to a value investing product
   * @private
   */
  private transformToValueProduct(
    product: Product,
    analysisResults: Map<string, any>,
    stats: ProcessingStats,
  ): ValueInvestingProduct | null {
    const analysis = analysisResults.get(product.productId);

    // Check analysis exists
    if (!analysis) {
      stats.skipped.noAnalysis++;
      console.debug(
        `[ValueInvestingService] Skipped ${product.productId}: no analysis`,
      );
      return null;
    }

    // Check for valid score
    if (
      analysis.overall.value === null ||
      analysis.overall.value === 0
    ) {
      stats.skipped.nullScore++;
      console.debug(
        `[ValueInvestingService] Skipped ${product.productId}: null/zero score`,
      );
      return null;
    }

    // Only include buy opportunities
    if (
      analysis.action !== "strong_buy" && analysis.action !== "buy"
    ) {
      stats.skipped.notBuyable++;
      return null;
    }

    // Build intrinsic value inputs
    const retirementStatus = analysis.dimensions?.availability
      ?.retirementStatus;
    const intrinsicValueInputs: IntrinsicValueInputs = {
      bricklinkAvgPrice: analysis.dimensions?.pricing?.bricklinkAvgPrice,
      bricklinkMaxPrice: analysis.dimensions?.pricing?.bricklinkMaxPrice,
      demandScore: analysis.dimensions?.demand?.value ?? 50,
      qualityScore: analysis.dimensions?.quality?.value ?? 50,
      retirementStatus: isRetirementStatus(retirementStatus)
        ? retirementStatus
        : undefined,
    };

    // Calculate value metrics
    let valueMetrics;
    try {
      valueMetrics = ValueCalculator.calculateValueMetrics(
        product.price,
        intrinsicValueInputs,
        analysis.urgency,
      );
    } catch (error) {
      stats.skipped.calculationError++;
      console.warn(
        `[ValueInvestingService] Failed to calculate metrics for ${product.productId}:`,
        error instanceof Error ? error.message : error,
      );
      return null;
    }

    // Only include products with positive margin of safety
    if (valueMetrics.marginOfSafety <= 0) {
      stats.skipped.noMarginOfSafety++;
      return null;
    }

    // Build value investing product
    return {
      id: product.id,
      productId: product.productId,
      name: product.name,
      image: product.image,
      legoSetNumber: product.legoSetNumber,
      source: product.source,
      brand: product.brand,
      currentPrice: product.price,
      currency: product.currency,
      valueMetrics,
      strategy: analysis.strategy || "Unknown",
      action: analysis.action,
      urgency: analysis.urgency,
      overallScore: analysis.overall.value || 0,
      risks: analysis.risks || [],
      opportunities: analysis.opportunities || [],
      unitsSold: product.unitsSold ?? undefined,
      lifetimeSold: product.lifetimeSold ?? undefined,
      currentStock: product.currentStock ?? undefined,
      avgStarRating: product.avgStarRating ?? undefined,
    };
  }

  /**
   * Extract unique strategies from opportunities
   * @param opportunities - Value investing products
   * @returns Array of unique strategy names
   */
  extractStrategies(opportunities: ValueInvestingProduct[]): string[] {
    return Array.from(
      new Set(opportunities.map((p) => p.strategy)),
    ).filter((s) => s !== "Unknown");
  }
}
