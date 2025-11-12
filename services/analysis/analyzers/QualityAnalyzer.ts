/**
 * QualityAnalyzer - Analyzes product and seller quality signals
 * Focuses on: ratings, reviews, seller trust, brand reputation
 */

import { BaseAnalyzer } from "./BaseAnalyzer.ts";
import type { AnalysisScore, QualityData } from "../types.ts";

export class QualityAnalyzer extends BaseAnalyzer<QualityData> {
  constructor() {
    super(
      "Quality Analyzer",
      "Evaluates product quality, ratings, and seller trustworthiness",
    );
  }

  async analyze(data: QualityData): Promise<AnalysisScore | null> {
    // Prerequisite check: Need at least ratings OR trust signals
    const hasRatings = data.avgStarRating !== undefined &&
      data.ratingCount !== undefined;
    const hasTrustSignals = data.isPreferredSeller !== undefined ||
      data.isServiceByShopee !== undefined || data.isMart !== undefined;
    const hasBrandData = data.brand !== undefined;
    const hasMetadata = data.legoSetNumber !== undefined ||
      data.theme !== undefined;

    if (!hasRatings && !hasTrustSignals && !hasBrandData && !hasMetadata) {
      return null; // Skip analysis - insufficient quality data
    }

    const scores: Array<{ score: number; weight: number }> = [];
    const reasons: string[] = [];
    const dataPoints: Record<string, unknown> = {};

    // 1. Product ratings analysis
    if (
      data.avgStarRating !== undefined && data.ratingCount !== undefined
    ) {
      const ratingScore = this.analyzeRatings(
        data.avgStarRating,
        data.ratingCount,
        data.ratingDistribution,
      );
      scores.push({ score: ratingScore, weight: 0.4 });

      dataPoints.avgStarRating = data.avgStarRating;
      dataPoints.ratingCount = data.ratingCount;

      if (data.avgStarRating >= 4.5) {
        reasons.push(
          `Excellent ratings (${
            data.avgStarRating.toFixed(1)
          }/5 from ${data.ratingCount} reviews)`,
        );
      } else if (data.avgStarRating >= 4.0) {
        reasons.push(
          `Good ratings (${
            data.avgStarRating.toFixed(1)
          }/5 from ${data.ratingCount} reviews)`,
        );
      } else if (data.avgStarRating >= 3.5) {
        reasons.push(
          `Average ratings (${data.avgStarRating.toFixed(1)}/5)`,
        );
      } else if (data.avgStarRating < 3.5) {
        reasons.push(
          `Below average ratings (${data.avgStarRating.toFixed(1)}/5)`,
        );
      }

      // Warn about low review count
      if (data.ratingCount < 10) {
        reasons.push("Limited reviews available");
      }
    }

    // 2. Seller trust signals
    const trustScore = this.analyzeSellerTrust(
      data.isPreferredSeller,
      data.isServiceByShopee,
      data.isMart,
    );
    scores.push({ score: trustScore, weight: 0.3 });

    const trustSignals: string[] = [];
    if (data.isPreferredSeller) {
      trustSignals.push("Preferred Seller");
      dataPoints.isPreferredSeller = true;
    }
    if (data.isServiceByShopee) {
      trustSignals.push("Serviced by Shopee");
      dataPoints.isServiceByShopee = true;
    }
    if (data.isMart) {
      trustSignals.push("Shopee Mall");
      dataPoints.isMart = true;
    }

    if (trustSignals.length > 0) {
      reasons.push(`Trusted seller (${trustSignals.join(", ")})`);
    }

    // 3. Brand authenticity (LEGO official)
    if (data.brand) {
      const brandScore = this.analyzeBrand(data.brand);
      scores.push({ score: brandScore, weight: 0.2 });

      dataPoints.brand = data.brand;

      if (data.brand.toLowerCase().includes("lego")) {
        reasons.push("Official LEGO product");
      }
    }

    // 4. Set metadata quality
    if (data.legoSetNumber && data.theme) {
      scores.push({ score: 80, weight: 0.1 }); // Bonus for having proper metadata

      dataPoints.legoSetNumber = data.legoSetNumber;
      dataPoints.theme = data.theme;

      // Premium themes get slight bonus
      const premiumThemes = [
        "star wars",
        "harry potter",
        "marvel",
        "dc",
        "technic",
        "creator expert",
      ];
      if (
        premiumThemes.some((t) => data.theme!.toLowerCase().includes(t))
      ) {
        reasons.push(`Popular ${data.theme} theme`);
      }
    }

    // Calculate final score
    const finalScore = scores.length > 0 ? this.weightedAverage(scores) : 50; // Neutral if no data

    // Calculate confidence based on data availability
    const confidence = this.calculateConfidence([
      data.avgStarRating,
      data.ratingCount,
      data.brand,
      data.legoSetNumber,
      data.isPreferredSeller,
    ]);

    return {
      value: Math.round(finalScore),
      confidence,
      reasoning: reasons.length > 0
        ? this.formatReasoning(reasons)
        : "Insufficient quality data for analysis.",
      dataPoints,
    };
  }

  /**
   * Score product ratings and review quality
   */
  private analyzeRatings(
    avgRating: number,
    reviewCount: number,
    distribution?: Record<string, number>,
  ): number {
    // Rating score (0-5 stars)
    let ratingScore = (avgRating / 5) * 100; // Convert to 0-100

    // Adjust based on review count (confidence)
    // Low review counts reduce the score
    if (reviewCount < 5) {
      ratingScore *= 0.5; // 50% penalty for very few reviews
    } else if (reviewCount < 20) {
      ratingScore *= 0.7; // 30% penalty for few reviews
    } else if (reviewCount < 50) {
      ratingScore *= 0.85; // 15% penalty for moderate reviews
    } else if (reviewCount < 100) {
      ratingScore *= 0.95; // 5% penalty for decent reviews
    }
    // 100+ reviews = no penalty

    // Analyze distribution if available (detect fake reviews)
    if (distribution) {
      const totalReviews = Object.values(distribution).reduce(
        (sum, count) => sum + count,
        0,
      );
      if (totalReviews > 0) {
        const fiveStarRatio = (distribution["5"] || 0) / totalReviews;
        const oneStarRatio = (distribution["1"] || 0) / totalReviews;

        // Suspicious if >90% five stars or very polarized
        if (fiveStarRatio > 0.9 && reviewCount > 20) {
          ratingScore *= 0.9; // Slight penalty for suspicious uniformity
        }

        // Mixed reviews are actually more trustworthy
        if (fiveStarRatio < 0.8 && oneStarRatio < 0.1 && avgRating >= 4.0) {
          ratingScore *= 1.05; // Bonus for realistic distribution
        }
      }
    }

    return Math.min(100, ratingScore);
  }

  /**
   * Score seller trust signals
   */
  private analyzeSellerTrust(
    isPreferred?: boolean,
    isServiceByShopee?: boolean,
    isMart?: boolean,
  ): number {
    let score = 40; // Base score

    // Each trust signal adds value
    if (isPreferred) score += 20; // Preferred seller badge
    if (isServiceByShopee) score += 20; // Shopee fulfillment
    if (isMart) score += 20; // Shopee Mall (most trusted)

    return Math.min(100, score);
  }

  /**
   * Score brand authenticity
   */
  private analyzeBrand(brand: string): number {
    const brandLower = brand.toLowerCase();

    // Official LEGO brand is best
    if (brandLower === "lego" || brandLower.includes("lego")) {
      return 100;
    }

    // Known third-party LEGO sellers
    if (brandLower.includes("brick") || brandLower.includes("block")) {
      return 60; // Potentially legitimate
    }

    // Generic or unknown brands
    return 40; // Lower score for unverified brands
  }
}
