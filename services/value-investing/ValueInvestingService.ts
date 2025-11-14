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
import type { ProductRecommendation } from "../analysis/types.ts";
import type { ValueInvestingProduct } from "../../types/value-investing.ts";
import { asCents, type Cents } from "../../types/price.ts";

/**
 * Type guard for retirement status
 */
function _isRetirementStatus(
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
    product.currency &&
    product.legoSetNumber // Required to link to Bricklink data
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
    analysisResults: Map<string, ProductRecommendation>,
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

    // If recommendation already has a buy price, use it directly
    if (analysis.recommendedBuyPrice) {
      // IMPORTANT: Both product.price and analysis.recommendedBuyPrice.price are now in CENTS
      const currentPriceCents: Cents = asCents(product.price!);
      const targetPriceCents: Cents = asCents(analysis.recommendedBuyPrice.price);
      const intrinsicValueCents: Cents = analysis.recommendedBuyPrice.breakdown?.intrinsicValue
        ? asCents(analysis.recommendedBuyPrice.breakdown.intrinsicValue)
        : asCents(Math.round(analysis.recommendedBuyPrice.price / (1 - 0.25))); // Estimate intrinsic value assuming 25% margin

      const valueMetrics = {
        currentPrice: currentPriceCents,
        targetPrice: targetPriceCents,
        intrinsicValue: intrinsicValueCents,
        marginOfSafety: ((targetPriceCents - currentPriceCents) / targetPriceCents) * 100,
        expectedROI: ((targetPriceCents - currentPriceCents) / currentPriceCents) * 100,
        timeHorizon: analysis.timeHorizon || "Unknown",
      };

      return {
        id: product.id,
        productId: product.productId,
        name: product.name!,
        image: product.image!,
        legoSetNumber: product.legoSetNumber,
        source: product.source,
        brand: product.brand!,
        currentPrice: currentPriceCents,  // Now consistently in cents
        currency: product.currency || "MYR",
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

    // Fallback: try to calculate from Bricklink data if available
    // This requires fetching Bricklink data separately, so we'll skip for now
    // TODO: Implement fetching Bricklink data for products without recommendedBuyPrice
    stats.skipped.calculationError++;
    console.warn(
      `[ValueInvestingService] No recommended buy price for ${product.productId}`,
    );
    return null;
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
