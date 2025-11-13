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

import type {
  IBricklinkRepository,
  IProductRepository,
  IRedditRepository,
  IRetirementRepository,
} from "./repositories/IRepository.ts";

export class DataAggregationService {
  constructor(
    private productRepo: IProductRepository,
    private bricklinkRepo: IBricklinkRepository,
    private redditRepo: IRedditRepository,
    private retirementRepo: IRetirementRepository,
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
    const [bricklinkData, redditData, retirementData] = await Promise.all([
      product.legoSetNumber
        ? this.bricklinkRepo.findByLegoSetNumber(product.legoSetNumber)
        : Promise.resolve(null),
      product.legoSetNumber
        ? this.redditRepo.findByLegoSetNumber(product.legoSetNumber)
        : Promise.resolve(null),
      product.legoSetNumber
        ? this.retirementRepo.findByLegoSetNumber(product.legoSetNumber)
        : Promise.resolve(null),
    ]);

    // Build analysis input using pure transformation functions
    return {
      productId: product.productId,
      name: product.name || "Unknown Product",
      pricing: this.buildPricingData(product, bricklinkData),
      demand: this.buildDemandData(product, bricklinkData, redditData),
      availability: this.buildAvailabilityData(product, retirementData),
      quality: this.buildQualityData(product, retirementData),
    };
  }

  /**
   * Aggregate data for multiple products (BATCH OPERATION)
   * Solves N+1 query problem by fetching all related data in 3 queries instead of 3*N
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

    // Batch fetch all related data in parallel (3 queries instead of 3*N!)
    const [bricklinkMap, redditMap, retirementMap] = await Promise.all([
      this.bricklinkRepo.findByLegoSetNumbers(uniqueSetNumbers),
      this.redditRepo.findByLegoSetNumbers(uniqueSetNumbers),
      this.retirementRepo.findByLegoSetNumbers(uniqueSetNumbers),
    ]);

    console.info(
      `[DataAggregationService] Batch aggregation complete:`,
      {
        products: products.length,
        uniqueSetNumbers: uniqueSetNumbers.length,
        bricklinkHits: bricklinkMap.size,
        redditHits: redditMap.size,
        retirementHits: retirementMap.size,
      },
    );

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

      const analysisInput: ProductAnalysisInput = {
        productId: product.productId,
        name: product.name || "Unknown Product",
        pricing: this.buildPricingData(product, bricklinkData),
        demand: this.buildDemandData(product, bricklinkData, redditData),
        availability: this.buildAvailabilityData(product, retirementData),
        quality: this.buildQualityData(product, retirementData),
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
    return {
      currentRetailPrice: this.safeNumber(product.price),
      originalRetailPrice: this.safeNumber(product.priceBeforeDiscount),
      discountPercentage: this.calculateDiscountPercentage(
        this.safeNumber(product.price),
        this.safeNumber(product.priceBeforeDiscount),
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
  ): DemandData {
    return {
      unitsSold: this.safeNumber(product.unitsSold),
      lifetimeSold: this.safeNumber(product.lifetimeSold),
      viewCount: this.safeNumber(product.view_count),
      likedCount: this.safeNumber(product.liked_count),
      commentCount: this.safeNumber(product.commentCount),
      bricklinkTimesSold: bricklinkData
        ? this.extractBricklinkTimesSold(bricklinkData)
        : undefined,
      bricklinkTotalQty: bricklinkData
        ? this.extractBricklinkTotalQty(bricklinkData)
        : undefined,
      ...this.normalizeRedditData(redditData),
    };
  }

  /**
   * Build availability data
   * Pure function - no side effects
   */
  private buildAvailabilityData(
    product: Product,
    retirementData: BrickrankerRetirementItem | null,
  ): AvailabilityData {
    return {
      currentStock: this.safeNumber(product.currentStock),
      stockType: product.stockType?.toString(),
      retiringSoon: retirementData?.retiringSoon || false,
      expectedRetirementDate: retirementData?.expectedRetirementDate
        ? this.parseRetirementDate(retirementData.expectedRetirementDate)
        : undefined,
      yearReleased: retirementData?.yearReleased || undefined,
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
   */
  private buildQualityData(
    product: Product,
    retirementData: BrickrankerRetirementItem | null,
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

  private calculateDiscountPercentage(
    price: number | undefined,
    priceBeforeDiscount: number | undefined,
  ): number | undefined {
    if (!price || !priceBeforeDiscount || priceBeforeDiscount <= price) {
      return undefined;
    }
    return ((priceBeforeDiscount - price) / priceBeforeDiscount) * 100;
  }

  private normalizeBricklinkPricing(item: BricklinkItem) {
    const parseBox = (box: unknown) => {
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

  private parsePrice(priceStr: string | undefined | null): number | undefined {
    if (!priceStr) return undefined;
    const cleaned = priceStr.replace(/[^0-9.]/g, "");
    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? undefined : parsed;
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
}
