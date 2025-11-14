import { Handlers, PageProps } from "$fresh/server.ts";
import { Head } from "$fresh/runtime.ts";
import { db } from "../db/client.ts";
import { bricklinkItems, products } from "../db/schema.ts";
import { and, eq, gt, isNotNull, or, sql } from "drizzle-orm";
import { AnalysisService } from "../services/analysis/AnalysisService.ts";
import { ValueInvestingService } from "../services/value-investing/ValueInvestingService.ts";
import type { ValueInvestingProduct } from "../types/value-investing.ts";
import ValueInvestingDashboard from "../islands/ValueInvestingDashboard.tsx";
import { globalCache } from "../services/cache/CacheService.ts";

interface BuyPageData {
  products: ValueInvestingProduct[];
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
          // Step 1: Fetch all active products with Bricklink data
          const allProducts = await db
            .select({
              id: products.id,
              source: products.source,
              productId: products.productId,
              name: products.name,
              brand: products.brand,
              currency: products.currency,
              price: products.price,
              priceMin: products.priceMin,
              priceMax: products.priceMax,
              priceBeforeDiscount: products.priceBeforeDiscount,
              image: products.image,
              images: products.images,
              localImagePath: products.localImagePath,
              localImages: products.localImages,
              imageDownloadedAt: products.imageDownloadedAt,
              imageDownloadStatus: products.imageDownloadStatus,
              legoSetNumber: products.legoSetNumber,
              watchStatus: products.watchStatus,
              unitsSold: products.unitsSold,
              lifetimeSold: products.lifetimeSold,
              liked_count: products.liked_count,
              commentCount: products.commentCount,
              view_count: products.view_count,
              avgStarRating: products.avgStarRating,
              ratingCount: products.ratingCount,
              stockInfoSummary: products.stockInfoSummary,
              stockType: products.stockType,
              currentStock: products.currentStock,
              isAdult: products.isAdult,
              isMart: products.isMart,
              isPreferred: products.isPreferred,
              isServiceByShopee: products.isServiceByShopee,
              shopId: products.shopId,
              shopName: products.shopName,
              shopLocation: products.shopLocation,
              sku: products.sku,
              categoryNumber: products.categoryNumber,
              categoryName: products.categoryName,
              ageRange: products.ageRange,
              rawData: products.rawData,
              tags: products.tags,
              createdAt: products.createdAt,
              updatedAt: products.updatedAt,
            })
            .from(products)
            .innerJoin(
              bricklinkItems,
              eq(
                sql`'S-' || ${products.legoSetNumber}`,
                bricklinkItems.itemId,
              ),
            )
            .where(
              and(
                eq(products.watchStatus, "active"),
                gt(products.price, 0),
                isNotNull(products.legoSetNumber),
                // Ensure Bricklink has pricing data (at least one field must be populated)
                or(
                  isNotNull(bricklinkItems.sixMonthNew),
                  isNotNull(bricklinkItems.sixMonthUsed),
                  isNotNull(bricklinkItems.currentNew),
                  isNotNull(bricklinkItems.currentUsed),
                ),
              ),
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

          console.info("[BuyPage] Processing summary:", {
            totalProducts: stats.totalProducts,
            includedOpportunities: stats.includedOpportunities,
            skipped: stats.skipped,
          });

          return {
            products: opportunities,
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
              />
            )}
        </div>
      </div>
    </>
  );
}
