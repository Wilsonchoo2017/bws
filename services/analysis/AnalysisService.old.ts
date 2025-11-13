/**
 * AnalysisService - Main service orchestrator for product analysis
 * Fetches data from database and coordinates analysis pipeline
 */

import { eq } from "drizzle-orm";
import { db } from "../../db/client.ts";
import {
  type BricklinkItem,
  bricklinkItems,
  type BrickrankerRetirementItem,
  brickrankerRetirementItems,
  type Product,
  products,
  type RedditSearchResult,
  redditSearchResults,
} from "../../db/schema.ts";

import { PricingAnalyzer } from "./analyzers/PricingAnalyzer.ts";
import { DemandAnalyzer } from "./analyzers/DemandAnalyzer.ts";
import { AvailabilityAnalyzer } from "./analyzers/AvailabilityAnalyzer.ts";
import { QualityAnalyzer } from "./analyzers/QualityAnalyzer.ts";

import { BargainHunterStrategy } from "./strategies/BargainHunterStrategy.ts";
import { InvestmentFocusStrategy } from "./strategies/InvestmentFocusStrategy.ts";
import { QuickFlipStrategy } from "./strategies/QuickFlipStrategy.ts";

import { RecommendationEngine } from "./RecommendationEngine.ts";

import type {
  AvailabilityData,
  DemandData,
  PricingData,
  ProductAnalysisInput,
  ProductRecommendation,
  QualityData,
} from "./types.ts";

export class AnalysisService {
  private recommendationEngine: RecommendationEngine;
  private defaultStrategy = "Investment Focus";

  constructor() {
    // Initialize analyzers
    const pricingAnalyzer = new PricingAnalyzer();
    const demandAnalyzer = new DemandAnalyzer();
    const availabilityAnalyzer = new AvailabilityAnalyzer();
    const qualityAnalyzer = new QualityAnalyzer();

    // Initialize strategies
    const strategies = [
      new BargainHunterStrategy(),
      new InvestmentFocusStrategy(),
      new QuickFlipStrategy(),
    ];

    // Initialize recommendation engine
    this.recommendationEngine = new RecommendationEngine(
      pricingAnalyzer,
      demandAnalyzer,
      availabilityAnalyzer,
      qualityAnalyzer,
      strategies,
    );
  }

  /**
   * Analyze a product by combining data from multiple sources
   */
  async analyzeProduct(
    productId: string,
    strategyName?: string,
  ): Promise<ProductRecommendation> {
    // Fetch product data
    const product = await db
      .select()
      .from(products)
      .where(eq(products.productId, productId))
      .limit(1);

    if (!product || product.length === 0) {
      throw new Error(`Product not found: ${productId}`);
    }

    const productData = product[0];

    // Build analysis input by combining data from various sources
    const input = await this.buildAnalysisInput(productData);

    // Run analysis with selected strategy
    const strategy = strategyName || this.defaultStrategy;
    return await this.recommendationEngine.analyze(input, strategy);
  }

  /**
   * Analyze multiple products (for batch processing)
   */
  async analyzeProducts(
    productIds: string[],
    strategyName?: string,
  ): Promise<Map<string, ProductRecommendation>> {
    const results = new Map<string, ProductRecommendation>();

    // Analyze in parallel
    const analyses = await Promise.allSettled(
      productIds.map((id) => this.analyzeProduct(id, strategyName)),
    );

    analyses.forEach((result, index) => {
      if (result.status === "fulfilled") {
        results.set(productIds[index], result.value);
      }
    });

    return results;
  }

  /**
   * Build ProductAnalysisInput from database data
   */
  private async buildAnalysisInput(
    product: Product,
  ): Promise<ProductAnalysisInput> {
    // Fetch related data in parallel
    const [bricklinkData, redditData, retirementData] = await Promise.all([
      this.fetchBricklinkData(product.legoSetNumber),
      this.fetchRedditData(product.legoSetNumber),
      this.fetchRetirementData(product.legoSetNumber),
    ]);

    // Build pricing data
    const pricing: PricingData = {
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

    // Build demand data
    const demand: DemandData = {
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

    // Build availability data
    const availability: AvailabilityData = {
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

    // Build quality data
    const quality: QualityData = {
      avgStarRating: this.safeNumber(product.avgStarRating)
        ? this.safeNumber(product.avgStarRating)! / 10
        : undefined, // Shopee stores as bigint * 10
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

    return {
      productId: product.productId,
      name: product.name || "Unknown Product",
      pricing,
      demand,
      availability,
      quality,
    };
  }

  /**
   * Fetch Bricklink data for a LEGO set
   */
  private async fetchBricklinkData(
    legoSetNumber: string | null,
  ): Promise<BricklinkItem | null> {
    if (!legoSetNumber) return null;

    try {
      // Bricklink uses "S" prefix for sets
      const itemId = `S-${legoSetNumber}`;

      const result = await db
        .select()
        .from(bricklinkItems)
        .where(eq(bricklinkItems.itemId, itemId))
        .limit(1);

      return result.length > 0 ? result[0] : null;
    } catch (error) {
      console.warn(
        `Failed to fetch Bricklink data for ${legoSetNumber}:`,
        error instanceof Error ? error.message : error,
      );
      return null;
    }
  }

  /**
   * Fetch Reddit sentiment data for a LEGO set
   */
  private async fetchRedditData(
    legoSetNumber: string | null,
  ): Promise<RedditSearchResult | null> {
    if (!legoSetNumber) return null;

    try {
      const result = await db
        .select()
        .from(redditSearchResults)
        .where(eq(redditSearchResults.legoSetNumber, legoSetNumber))
        .limit(1);

      return result.length > 0 ? result[0] : null;
    } catch (error) {
      console.warn(
        `Failed to fetch Reddit data for ${legoSetNumber}:`,
        error instanceof Error ? error.message : error,
      );
      return null;
    }
  }

  /**
   * Fetch retirement data for a LEGO set
   */
  private async fetchRetirementData(
    legoSetNumber: string | null,
  ): Promise<BrickrankerRetirementItem | null> {
    if (!legoSetNumber) return null;

    try {
      const result = await db
        .select()
        .from(brickrankerRetirementItems)
        .where(eq(brickrankerRetirementItems.setNumber, legoSetNumber))
        .limit(1);

      return result.length > 0 ? result[0] : null;
    } catch (error) {
      console.warn(
        `Failed to fetch retirement data for ${legoSetNumber}:`,
        error instanceof Error ? error.message : error,
      );
      return null;
    }
  }

  // Helper methods for data normalization

  private calculateDiscountPercentage(
    price: number | null | undefined,
    priceBeforeDiscount: number | null | undefined,
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
    // Remove currency symbols and parse
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

  private safeNumber(
    value: number | bigint | null | undefined,
  ): number | undefined {
    if (value === null || value === undefined) return undefined;
    if (typeof value === "bigint") return Number(value);
    if (typeof value === "number") return value;
    return undefined;
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
      // Handle various date formats
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
   * Get available strategies
   */
  getAvailableStrategies() {
    return this.recommendationEngine.getAvailableStrategies();
  }

  /**
   * Get analyzer information
   */
  getAnalyzerInfo() {
    return this.recommendationEngine.getAnalyzerInfo();
  }
}

// Export singleton instance
export const analysisService = new AnalysisService();
