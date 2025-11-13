import { Handlers, PageProps } from "$fresh/server.ts";
import { Head } from "$fresh/runtime.ts";
import { db } from "../db/client.ts";
import { products } from "../db/schema.ts";
import { sql } from "drizzle-orm";
import { AnalysisService } from "../services/analysis/AnalysisService.ts";
import { ValueInvestingService } from "../services/value-investing/ValueInvestingService.ts";
import type { ValueInvestingProduct } from "../types/value-investing.ts";
import ValueInvestingDashboard from "../islands/ValueInvestingDashboard.tsx";
import { globalCache } from "../services/cache/CacheService.ts";

interface BuyPageData {
  products: ValueInvestingProduct[];
  strategies: string[];
  error?: string;
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

          // Step 2: Use ValueInvestingService to get opportunities
          const analysisService = new AnalysisService();
          const valueService = new ValueInvestingService(analysisService);

          const { opportunities, stats } = await valueService
            .getValueOpportunities(allProducts);

          // Step 3: Extract unique strategies
          const strategies = valueService.extractStrategies(opportunities);

          console.info("[BuyPage] Processing summary:", {
            totalProducts: stats.totalProducts,
            includedOpportunities: stats.includedOpportunities,
            skipped: stats.skipped,
            strategies: strategies.length,
          });

          return {
            products: opportunities,
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
