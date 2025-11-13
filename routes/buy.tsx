import { Handlers, PageProps } from "$fresh/server.ts";
import { Head } from "$fresh/runtime.ts";
import { db } from "../db/client.ts";
import { products } from "../db/schema.ts";
import { eq, sql } from "drizzle-orm";
import { AnalysisService } from "../services/analysis/AnalysisService.ts";
import { ValueCalculator } from "../services/value-investing/ValueCalculator.ts";
import type {
  IntrinsicValueInputs,
  ValueInvestingProduct,
} from "../types/value-investing.ts";
import ValueInvestingDashboard from "../islands/ValueInvestingDashboard.tsx";
import { globalCache } from "../services/cache/CacheService.ts";

interface BuyPageData {
  products: ValueInvestingProduct[];
  strategies: string[];
  error?: string;
}

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
function isValidProduct(product: any): boolean {
  return !!(
    product.productId &&
    product.name &&
    product.price !== null &&
    product.price > 0 &&
    product.image &&
    product.currency
  );
}

// Cache key for value investing opportunities
const CACHE_KEY = "value-investing:opportunities";
const CACHE_TTL = 300000; // 5 minutes

export const handler: Handlers<BuyPageData> = {
  async GET(_req, ctx) {
    const startTime = performance.now();

    try {
      // Try to get from cache first
      const cachedData = await globalCache.getOrCompute<BuyPageData>(
        CACHE_KEY,
        async () => {
          const skippedReasons = {
            invalidProduct: 0,
            noAnalysis: 0,
            nullScore: 0,
            notBuyable: 0,
            noMarginOfSafety: 0,
            calculationError: 0,
          };

          // Step 1: Fetch all active products
          const allProducts = await db
            .select()
            .from(products)
            .where(
              sql`${products.watchStatus} = 'active' AND ${products.price} > 0`,
            )
            .limit(100); // Limit for performance

          if (allProducts.length === 0) {
            return {
              products: [],
              strategies: [],
              error: "No active products found",
            };
          }

          // Step 2: Analyze products using AnalysisService
          const analysisService = new AnalysisService();
          const productIds = allProducts.map((p) => p.productId);
          const analysisResults = await analysisService.analyzeProducts(
            productIds,
          );

          // Step 3: Transform products with value investing metrics
          const valueInvestingProducts: ValueInvestingProduct[] = [];

      for (const product of allProducts) {
        // Validate product has required fields
        if (!isValidProduct(product)) {
          skippedReasons.invalidProduct++;
          console.debug(
            `[BuyPage] Skipped product ${product.id}: missing required fields`,
          );
          continue;
        }

        const analysis = analysisResults.get(product.productId);

        // Skip products without analysis or with null scores
        if (!analysis) {
          skippedReasons.noAnalysis++;
          console.debug(
            `[BuyPage] Skipped ${product.productId}: no analysis`,
          );
          continue;
        }

        if (
          analysis.overall.value === null ||
          analysis.overall.value === 0
        ) {
          skippedReasons.nullScore++;
          console.debug(
            `[BuyPage] Skipped ${product.productId}: null/zero score`,
          );
          continue;
        }

        // Only include buy opportunities
        if (
          analysis.action !== "strong_buy" && analysis.action !== "buy"
        ) {
          skippedReasons.notBuyable++;
          continue;
        }

        // Prepare intrinsic value inputs from analysis
        // Use safe type guard for retirement status
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

        // Calculate value metrics with error handling
        let valueMetrics;
        try {
          valueMetrics = ValueCalculator.calculateValueMetrics(
            product.price,
            intrinsicValueInputs,
            analysis.urgency,
          );
        } catch (error) {
          skippedReasons.calculationError++;
          console.warn(
            `[BuyPage] Failed to calculate metrics for ${product.productId}:`,
            error instanceof Error ? error.message : error,
          );
          continue;
        }

        // Only include products with positive margin of safety
        if (valueMetrics.marginOfSafety <= 0) {
          skippedReasons.noMarginOfSafety++;
          continue;
        }

        // Build ValueInvestingProduct
        const valueProduct: ValueInvestingProduct = {
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
          unitsSold: product.unitsSold || undefined,
          lifetimeSold: product.lifetimeSold || undefined,
          currentStock: product.currentStock || undefined,
          avgStarRating: product.avgStarRating || undefined,
        };

        valueInvestingProducts.push(valueProduct);
      }

          // Step 4: Get unique strategies
          const strategies = Array.from(
            new Set(valueInvestingProducts.map((p) => p.strategy)),
          ).filter((s) => s !== "Unknown");

          // Log processing summary
          console.info("[BuyPage] Processing summary:", {
            totalProducts: allProducts.length,
            includedOpportunities: valueInvestingProducts.length,
            skipped: skippedReasons,
            strategies: strategies.length,
          });

          return {
            products: valueInvestingProducts,
            strategies,
          };
        },
        CACHE_TTL,
      );

      // Log performance metrics
      const duration = performance.now() - startTime;
      const cacheStats = globalCache.getStats();

      console.info("[BuyPage] Request completed:", {
        durationMs: Math.round(duration),
        productCount: cachedData.products.length,
        cacheStats,
      });

      return ctx.render(cachedData);
    } catch (error) {
      console.error("[BuyPage] Error fetching value investing data:", {
        error: error instanceof Error ? error.message : "Unknown error",
        stack: error instanceof Error ? error.stack : undefined,
        timestamp: new Date().toISOString(),
      });

      return ctx.render({
        products: [],
        strategies: [],
        error: error instanceof Error
          ? error.message
          : "Failed to load value investing opportunities. Please try again later.",
      });
    }
  },
};

export default function BuyPage({ data }: PageProps<BuyPageData>) {
  return (
    <>
      <Head>
        <title>Buy - Value Investing Dashboard</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="max-w-7xl mx-auto">
          {data.error
            ? (
              <div class="alert alert-error">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  class="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>{data.error}</span>
              </div>
            )
            : (
              <ValueInvestingDashboard
                products={data.products}
                strategies={data.strategies}
              />
            )}
        </div>
      </div>
    </>
  );
}
