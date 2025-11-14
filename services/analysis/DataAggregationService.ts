/**
 * DataAggregationService - Aggregates data from multiple repositories
 * Single Responsibility: Data fetching and transformation only
 * Depends on repository abstractions (Dependency Inversion Principle)
 */

import type {
  BricklinkItem,
  BrickrankerRetirementItem,
  Product,
  RedditSearchResult,
} from "../../db/schema.ts";

import type {
  AvailabilityData,
  DemandData,
  PricingData,
  ProductAnalysisInput,
  QualityData,
} from "./types.ts";
import { asCents, type Cents } from "../../types/price.ts";
import { asBaseSetNumber, toBricklinkItemId } from "../../types/lego-set.ts";

import type {
  IBricklinkRepository,
  IProductRepository,
  IRedditRepository,
  IRetirementRepository,
  IWorldBricksRepository,
  PastSalesStatistics,
  WorldBricksSet,
} from "./repositories/IRepository.ts";

import { BricklinkDataValidator } from "../bricklink/BricklinkDataValidator.ts";

export class DataAggregationService {
  constructor(
    private productRepo: IProductRepository,
    private bricklinkRepo: IBricklinkRepository,
    private redditRepo: IRedditRepository,
    private retirementRepo: IRetirementRepository,
    private worldBricksRepo: IWorldBricksRepository,
  ) {}

  /**
   * Aggregate all data needed for product analysis
   */
  async aggregateProductData(productId: string): Promise<ProductAnalysisInput> {
    // Fetch base product data
    const product = await this.productRepo.findByProductId(productId);
    if (!product) {
      throw new Error(`Product not found: ${productId}`);
    }

    // Fetch related data in parallel (only if LEGO set number exists)
    const [
      bricklinkData,
      redditData,
      retirementData,
      worldBricksData,
      pastSalesStats,
    ] = await Promise.all([
      product.legoSetNumber
        ? this.bricklinkRepo.findByLegoSetNumber(product.legoSetNumber)
        : Promise.resolve(null),
      product.legoSetNumber
        ? this.redditRepo.findByLegoSetNumber(product.legoSetNumber)
        : Promise.resolve(null),
      product.legoSetNumber
        ? this.retirementRepo.findByLegoSetNumber(product.legoSetNumber)
        : Promise.resolve(null),
      product.legoSetNumber
        ? this.worldBricksRepo.findBySetNumber(product.legoSetNumber)
        : Promise.resolve(null),
      product.legoSetNumber
        ? this.bricklinkRepo.getPastSalesStatistics(
          toBricklinkItemId(asBaseSetNumber(product.legoSetNumber)),
        )
        : Promise.resolve(null),
    ]);

    // Validate Bricklink data completeness (prerequisite for recommendations)
    const validation = BricklinkDataValidator.validateCompleteness(
      bricklinkData,
    );
    if (!validation.isComplete) {
      throw new Error(
        `Complete Bricklink sales data is required for analysis. ${validation.message}. Product: ${product.name} (${productId})`,
      );
    }

    // Build analysis input using pure transformation functions
    return {
      productId: product.productId,
      name: product.name || "Unknown Product",
      pricing: this.buildPricingData(product, bricklinkData),
      demand: this.buildDemandData(
        product,
        bricklinkData,
        redditData,
        pastSalesStats,
      ),
      availability: this.buildAvailabilityData(
        product,
        retirementData,
        worldBricksData,
      ),
      quality: this.buildQualityData(product, retirementData, worldBricksData),
    };
  }

  /**
   * Aggregate data for multiple products (BATCH OPERATION)
   * Solves N+1 query problem by fetching all related data in 4 queries instead of 4*N
   * @param products - Array of products to aggregate data for
   * @returns Map of productId -> ProductAnalysisInput
   */
  async aggregateProductsData(
    products: Product[],
  ): Promise<Map<string, ProductAnalysisInput>> {
    if (products.length === 0) return new Map();

    // Extract all unique LEGO set numbers
    const legoSetNumbers = products
      .map((p) => p.legoSetNumber)
      .filter((n): n is string => n !== null);

    const uniqueSetNumbers = Array.from(new Set(legoSetNumbers));

    // Convert set numbers to Bricklink item IDs for past sales
    const bricklinkItemIds = uniqueSetNumbers.map((num) =>
      toBricklinkItemId(asBaseSetNumber(num))
    );

    // Batch fetch all related data in parallel (5 queries instead of 5*N!)
    const [
      bricklinkMap,
      redditMap,
      retirementMap,
      worldBricksMap,
      pastSalesMap,
    ] = await Promise.all([
      this.bricklinkRepo.findByLegoSetNumbers(uniqueSetNumbers),
      this.redditRepo.findByLegoSetNumbers(uniqueSetNumbers),
      this.retirementRepo.findByLegoSetNumbers(uniqueSetNumbers),
      this.worldBricksRepo.findBySetNumbers(uniqueSetNumbers),
      this.bricklinkRepo.getPastSalesStatisticsBatch(bricklinkItemIds),
    ]);

    console.info(
      `[DataAggregationService] Batch aggregation complete:`,
      {
        products: products.length,
        uniqueSetNumbers: uniqueSetNumbers.length,
        bricklinkHits: bricklinkMap.size,
        redditHits: redditMap.size,
        retirementHits: retirementMap.size,
        worldBricksHits: worldBricksMap.size,
        pastSalesHits: pastSalesMap.size,
      },
    );

    // Validate Bricklink data completeness for all products FIRST
    const incompleteProducts: Array<
      { productId: string; name: string; message: string }
    > = [];

    for (const product of products) {
      const bricklinkData = product.legoSetNumber
        ? bricklinkMap.get(product.legoSetNumber) || null
        : null;

      const validation = BricklinkDataValidator.validateCompleteness(
        bricklinkData,
      );
      if (!validation.isComplete) {
        incompleteProducts.push({
          productId: product.productId,
          name: product.name || "Unknown Product",
          message: validation.message || "Missing Bricklink data",
        });
      }
    }

    // If any products have incomplete data, throw error with details
    if (incompleteProducts.length > 0) {
      const errorMessage =
        `Complete Bricklink sales data is required for analysis. ${incompleteProducts.length} of ${products.length} products have incomplete data:\n${
          incompleteProducts.map((p) =>
            `- ${p.name} (${p.productId}): ${p.message}`
          ).join("\n")
        }`;
      throw new Error(errorMessage);
    }

    // Build analysis input for each product
    const resultMap = new Map<string, ProductAnalysisInput>();

    for (const product of products) {
      // Look up related data from maps (O(1) instead of O(N) queries)
      const bricklinkData = product.legoSetNumber
        ? bricklinkMap.get(product.legoSetNumber) || null
        : null;
      const redditData = product.legoSetNumber
        ? redditMap.get(product.legoSetNumber) || null
        : null;
      const retirementData = product.legoSetNumber
        ? retirementMap.get(product.legoSetNumber) || null
        : null;
      const worldBricksData = product.legoSetNumber
        ? worldBricksMap.get(product.legoSetNumber) || null
        : null;
      const pastSalesStats = product.legoSetNumber
        ? pastSalesMap.get(
          toBricklinkItemId(asBaseSetNumber(product.legoSetNumber)),
        ) || null
        : null;

      const analysisInput: ProductAnalysisInput = {
        productId: product.productId,
        name: product.name || "Unknown Product",
        pricing: this.buildPricingData(product, bricklinkData),
        demand: this.buildDemandData(
          product,
          bricklinkData,
          redditData,
          pastSalesStats,
        ),
        availability: this.buildAvailabilityData(
          product,
          retirementData,
          worldBricksData,
        ),
        quality: this.buildQualityData(
          product,
          retirementData,
          worldBricksData,
        ),
      };

      resultMap.set(product.productId, analysisInput);
    }

    return resultMap;
  }

  /**
   * Build pricing data from product and Bricklink sources
   * Pure function - no side effects
   */
  private buildPricingData(
    product: Product,
    bricklinkData: BricklinkItem | null,
  ): PricingData {
    const currentPriceCents = this.safeNumber(product.price);
    const originalPriceCents = this.safeNumber(product.priceBeforeDiscount);

    return {
      currentRetailPrice: currentPriceCents !== undefined
        ? asCents(currentPriceCents)
        : undefined,
      originalRetailPrice: originalPriceCents !== undefined
        ? asCents(originalPriceCents)
        : undefined,
      discountPercentage: this.calculateDiscountPercentage(
        currentPriceCents,
        originalPriceCents,
      ),
      bricklink: bricklinkData
        ? this.normalizeBricklinkPricing(bricklinkData)
        : undefined,
    };
  }

  /**
   * Build demand data from multiple sources
   * Pure function - no side effects
   */
  private buildDemandData(
    product: Product,
    bricklinkData: BricklinkItem | null,
    redditData: RedditSearchResult | null,
    pastSalesStats: PastSalesStatistics | null,
  ): DemandData {
    // Base data from product and PRIMARY Bricklink pricing data
    const baseData: DemandData = {
      unitsSold: this.safeNumber(product.unitsSold),
      lifetimeSold: this.safeNumber(product.lifetimeSold),
      viewCount: this.safeNumber(product.view_count),
      likedCount: this.safeNumber(product.liked_count),
      commentCount: this.safeNumber(product.commentCount),
      // PRIMARY: Extract Bricklink pricing data for demand analysis
      ...this.extractBricklinkPricingForDemand(bricklinkData),
      // Legacy metrics
      bricklinkTimesSold: bricklinkData
        ? this.extractBricklinkTimesSold(bricklinkData)
        : undefined,
      bricklinkTotalQty: bricklinkData
        ? this.extractBricklinkTotalQty(bricklinkData)
        : undefined,
      ...this.normalizeRedditData(redditData),
    };

    // Add market-driven metrics from past sales statistics
    if (pastSalesStats && pastSalesStats.totalTransactions > 0) {
      const newMetrics = pastSalesStats.new;
      const usedMetrics = pastSalesStats.used;

      // Calculate weighted metrics (70% new, 30% used for investment focus)
      const totalWeight = newMetrics.transactionCount +
        usedMetrics.transactionCount;
      const newWeight = totalWeight > 0
        ? newMetrics.transactionCount / totalWeight
        : 0;

      return {
        ...baseData,
        // Total metrics
        bricklinkPastSalesCount: pastSalesStats.totalTransactions,

        // Liquidity & Velocity (weighted average with preference for 'new')
        bricklinkSalesVelocity: this.weightedAverage(
          newMetrics.salesVelocity,
          usedMetrics.salesVelocity,
          0.7, // 70% weight for new
        ),
        bricklinkAvgDaysBetweenSales: this.weightedAverage(
          newMetrics.avgDaysBetweenSales,
          usedMetrics.avgDaysBetweenSales,
          0.7,
        ),

        // Recent activity (combine new and used)
        bricklinkRecentSales30d: newMetrics.recent30d + usedMetrics.recent30d,
        bricklinkRecentSales60d: newMetrics.recent60d + usedMetrics.recent60d,
        bricklinkRecentSales90d: newMetrics.recent90d + usedMetrics.recent90d,

        // Price metrics (prefer new condition for investment)
        bricklinkAvgPrice: newMetrics.transactionCount > 0
          ? newMetrics.avgPrice
          : usedMetrics.avgPrice,
        bricklinkMedianPrice: newMetrics.transactionCount > 0
          ? newMetrics.medianPrice
          : usedMetrics.medianPrice,
        bricklinkPriceVolatility: newMetrics.transactionCount > 0
          ? newMetrics.volatilityIndex
          : usedMetrics.volatilityIndex,

        // Trend analysis (prefer new condition trends)
        bricklinkPriceTrend: newMetrics.transactionCount > 5
          ? newMetrics.trends.last90Days.direction
          : usedMetrics.trends.last90Days.direction,
        bricklinkPriceMomentum: newMetrics.transactionCount > 5
          ? newMetrics.trends.last90Days.momentum
          : usedMetrics.trends.last90Days.momentum,
        bricklinkPriceChangePercent: newMetrics.transactionCount > 5
          ? newMetrics.trends.last90Days.percentChange
          : usedMetrics.trends.last90Days.percentChange,
        bricklinkVolumeTrend: newMetrics.transactionCount > 5
          ? newMetrics.trends.last90Days.volumeTrend
          : usedMetrics.trends.last90Days.volumeTrend,

        // Market strength indicators (prefer new condition)
        bricklinkRSI: pastSalesStats.rsi.new ?? pastSalesStats.rsi.used ??
          undefined,

        // Condition weighting
        bricklinkNewConditionWeight: newWeight,
      };
    }

    return baseData;
  }

  /**
   * Build availability data
   * Pure function - no side effects
   * UPDATED: Now includes WorldBricks data for year released/retired
   */
  private buildAvailabilityData(
    product: Product,
    retirementData: BrickrankerRetirementItem | null,
    worldBricksData: WorldBricksSet | null,
  ): AvailabilityData {
    // Prefer WorldBricks for year data (more accurate)
    const yearReleased = worldBricksData?.yearReleased ||
      retirementData?.yearReleased ||
      undefined;

    const yearRetired = worldBricksData?.yearRetired || undefined;

    return {
      currentStock: this.safeNumber(product.currentStock),
      stockType: product.stockType?.toString(),
      retiringSoon: retirementData?.retiringSoon || false,
      expectedRetirementDate: retirementData?.expectedRetirementDate
        ? this.parseRetirementDate(retirementData.expectedRetirementDate)
        : undefined,
      yearReleased,
      yearRetired, // NEW: Official retirement year from WorldBricks
      daysUntilRetirement: retirementData
        ? this.calculateDaysUntilRetirement(retirementData)
        : undefined,
      isActive: true,
      source: product.source,
    };
  }

  /**
   * Build quality data
   * Pure function - no side effects
   * UPDATED: Now includes WorldBricks parts count
   */
  private buildQualityData(
    product: Product,
    retirementData: BrickrankerRetirementItem | null,
    worldBricksData: WorldBricksSet | null,
  ): QualityData {
    return {
      avgStarRating: this.safeNumber(product.avgStarRating)
        ? this.safeNumber(product.avgStarRating)! / 10
        : undefined,
      ratingCount: this.extractRatingCount(product.ratingCount),
      ratingDistribution: this.extractRatingDistribution(product.ratingCount),
      isPreferredSeller: product.isPreferred || undefined,
      isServiceByShopee: product.isServiceByShopee || undefined,
      isMart: product.isMart || undefined,
      shopLocation: product.shopLocation || undefined,
      brand: product.brand || undefined,
      theme: retirementData?.theme || undefined,
      legoSetNumber: product.legoSetNumber || undefined,
      partsCount: worldBricksData?.partsCount || undefined, // NEW: For PPD calculation
    };
  }

  // ============================================================================
  // Pure Helper Functions (no side effects, easily testable)
  // ============================================================================

  private safeNumber(
    value: number | bigint | null | undefined,
  ): number | undefined {
    if (value === null || value === undefined) return undefined;
    if (typeof value === "bigint") return Number(value);
    if (typeof value === "number") return value;
    return undefined;
  }

  private safeNumberInDollars(
    value: number | bigint | null | undefined,
  ): number | undefined {
    const cents = this.safeNumber(value);
    return cents !== undefined ? cents / 100 : undefined;
  }

  private calculateDiscountPercentage(
    price: number | undefined,
    priceBeforeDiscount: number | undefined,
  ): number | undefined {
    if (!price || !priceBeforeDiscount || priceBeforeDiscount <= price) {
      return undefined;
    }
    return ((priceBeforeDiscount - price) / priceBeforeDiscount) * 100;
  }

  private normalizeBricklinkPricing(item: BricklinkItem): {
    current: {
      newAvg?: Cents;
      newMin?: Cents;
      newMax?: Cents;
      usedAvg?: Cents;
      usedMin?: Cents;
      usedMax?: Cents;
    };
    sixMonth: {
      newAvg?: Cents;
      newMin?: Cents;
      newMax?: Cents;
      usedAvg?: Cents;
      usedMin?: Cents;
      usedMax?: Cents;
    };
  } {
    const parseBox = (box: unknown): {
      newAvg?: Cents;
      newMin?: Cents;
      newMax?: Cents;
    } => {
      if (!box || typeof box !== "object") return {};
      const b = box as Record<string, string>;
      return {
        newAvg: this.parsePrice(b.avgPrice),
        newMin: this.parsePrice(b.minPrice),
        newMax: this.parsePrice(b.maxPrice),
      };
    };

    return {
      current: {
        ...parseBox(item.currentNew),
        usedAvg: this.parsePrice(
          (item.currentUsed as Record<string, string> | null)?.avgPrice,
        ),
        usedMin: this.parsePrice(
          (item.currentUsed as Record<string, string> | null)?.minPrice,
        ),
        usedMax: this.parsePrice(
          (item.currentUsed as Record<string, string> | null)?.maxPrice,
        ),
      },
      sixMonth: {
        ...parseBox(item.sixMonthNew),
        usedAvg: this.parsePrice(
          (item.sixMonthUsed as Record<string, string> | null)?.avgPrice,
        ),
        usedMin: this.parsePrice(
          (item.sixMonthUsed as Record<string, string> | null)?.minPrice,
        ),
        usedMax: this.parsePrice(
          (item.sixMonthUsed as Record<string, string> | null)?.maxPrice,
        ),
      },
    };
  }

  private parsePrice(priceStr: string | undefined | null): Cents | undefined {
    if (!priceStr) return undefined;
    const cleaned = priceStr.replace(/[^0-9.]/g, "");
    const parsed = parseFloat(cleaned);
    // Bricklink prices are in dollars, convert to cents
    return isNaN(parsed) ? undefined : asCents(Math.round(parsed * 100));
  }

  private extractBricklinkTimesSold(item: BricklinkItem): number | undefined {
    const box = item.currentNew as Record<string, string> | null;
    if (!box?.timesSold) return undefined;
    const parsed = parseInt(box.timesSold.replace(/,/g, ""), 10);
    return isNaN(parsed) ? undefined : parsed;
  }

  private extractBricklinkTotalQty(item: BricklinkItem): number | undefined {
    const box = item.currentNew as Record<string, string> | null;
    if (!box?.totalQty) return undefined;
    const parsed = parseInt(box.totalQty.replace(/,/g, ""), 10);
    return isNaN(parsed) ? undefined : parsed;
  }

  /**
   * Extract Bricklink pricing data for demand analysis
   * Treats market pricing as PRIMARY demand signal
   */
  private extractBricklinkPricingForDemand(
    item: BricklinkItem | null,
  ): Partial<DemandData> {
    if (!item) {
      return {};
    }

    const parsePrice = (
      priceObj: Record<string, unknown> | null,
      key: string,
    ) => {
      if (!priceObj || typeof priceObj !== "object") return undefined;
      const value = priceObj[key];
      if (!value || typeof value !== "object") return undefined;
      const valueObj = value as Record<string, unknown>;
      return typeof valueObj.amount === "number" ? valueObj.amount : undefined;
    };

    const parseNumber = (value: unknown): number | undefined => {
      if (value === null || value === undefined) return undefined;
      if (typeof value === "number") return value;
      if (typeof value === "string") {
        const parsed = Number(value.replace(/,/g, ""));
        return isNaN(parsed) ? undefined : parsed;
      }
      return undefined;
    };

    const currentNew = item.currentNew as Record<string, unknown> | null;
    const sixMonthNew = item.sixMonthNew as Record<string, unknown> | null;

    return {
      // Current market data (indicates active supply/demand)
      bricklinkCurrentNewAvg: parsePrice(currentNew, "avg_price"),
      bricklinkCurrentNewMin: parsePrice(currentNew, "min_price"),
      bricklinkCurrentNewMax: parsePrice(currentNew, "max_price"),
      bricklinkCurrentNewQty: parseNumber(currentNew?.total_qty),
      bricklinkCurrentNewLots: parseNumber(currentNew?.total_lots),

      // Historical data (indicates market trends)
      bricklinkSixMonthNewAvg: parsePrice(sixMonthNew, "avg_price"),
      bricklinkSixMonthNewMin: parsePrice(sixMonthNew, "min_price"),
      bricklinkSixMonthNewMax: parsePrice(sixMonthNew, "max_price"),
      bricklinkSixMonthNewTimesSold: parseNumber(sixMonthNew?.times_sold),
      bricklinkSixMonthNewQty: parseNumber(sixMonthNew?.total_qty),
    };
  }

  private normalizeRedditData(
    data: RedditSearchResult | null,
  ): Partial<DemandData> {
    if (!data) return {};

    const posts = (data.posts as Array<Record<string, unknown>>) || [];
    const totalScore = posts.reduce(
      (sum, post) => sum + (typeof post.score === "number" ? post.score : 0),
      0,
    );
    const totalComments = posts.reduce(
      (sum, post) =>
        sum + (typeof post.num_comments === "number" ? post.num_comments : 0),
      0,
    );

    return {
      redditPosts: data.totalPosts || 0,
      redditTotalScore: totalScore,
      redditTotalComments: totalComments,
      redditAverageScore: posts.length > 0 ? totalScore / posts.length : 0,
    };
  }

  private extractRatingCount(ratingCount: unknown): number | undefined {
    if (!ratingCount || typeof ratingCount !== "object") return undefined;
    try {
      const counts = ratingCount as Record<string, number>;
      const total = Object.values(counts).reduce((sum, count) => {
        const num = typeof count === "number" ? count : 0;
        return sum + num;
      }, 0);
      return total > 0 ? total : undefined;
    } catch {
      return undefined;
    }
  }

  private extractRatingDistribution(
    ratingCount: unknown,
  ): Record<string, number> | undefined {
    if (!ratingCount || typeof ratingCount !== "object") return undefined;
    return ratingCount as Record<string, number>;
  }

  private parseRetirementDate(dateStr: string): Date | undefined {
    try {
      const date = new Date(dateStr);
      return isNaN(date.getTime()) ? undefined : date;
    } catch {
      return undefined;
    }
  }

  private calculateDaysUntilRetirement(
    item: BrickrankerRetirementItem,
  ): number | undefined {
    if (!item.expectedRetirementDate) return undefined;

    const retirementDate = this.parseRetirementDate(
      item.expectedRetirementDate,
    );
    if (!retirementDate) return undefined;

    const now = new Date();
    const diff = retirementDate.getTime() - now.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    return days > 0 ? days : undefined;
  }

  /**
   * Calculate weighted average of two values
   * @param value1 - First value
   * @param value2 - Second value
   * @param weight1 - Weight for first value (0-1), weight2 will be (1 - weight1)
   */
  private weightedAverage(
    value1: number,
    value2: number,
    weight1: number,
  ): number {
    const weight2 = 1 - weight1;
    return value1 * weight1 + value2 * weight2;
  }
}
