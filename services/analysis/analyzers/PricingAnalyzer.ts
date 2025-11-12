/**
 * PricingAnalyzer - Analyzes pricing data for investment opportunities
 * Focuses on: retail vs resale margins, price appreciation, discounts
 */

import { BaseAnalyzer } from "./BaseAnalyzer.ts";
import type { AnalysisScore, PricingData } from "../types.ts";

export class PricingAnalyzer extends BaseAnalyzer<PricingData> {
  constructor() {
    super(
      "Pricing Analyzer",
      "Evaluates price competitiveness, margins, and appreciation potential",
    );
  }

  async analyze(data: PricingData): Promise<AnalysisScore | null> {
    // Prerequisite check: Need at least retail price OR bricklink data
    const hasRetailData = data.currentRetailPrice !== undefined ||
      data.discountPercentage !== undefined;
    const hasBricklinkData = data.bricklink?.current.newAvg !== undefined;

    if (!hasRetailData && !hasBricklinkData) {
      return null; // Skip analysis - insufficient pricing data
    }

    const scores: Array<{ score: number; weight: number }> = [];
    const reasons: string[] = [];
    const dataPoints: Record<string, unknown> = {};

    // 1. Discount depth analysis (for retail purchases)
    if (data.discountPercentage !== undefined) {
      const discountScore = this.analyzeDiscount(data.discountPercentage);
      scores.push({ score: discountScore, weight: 0.3 });
      dataPoints.discountPercentage = data.discountPercentage;

      if (data.discountPercentage > 30) {
        reasons.push(
          `Strong ${data.discountPercentage.toFixed(0)}% discount from retail`,
        );
      } else if (data.discountPercentage > 15) {
        reasons.push(
          `Moderate ${data.discountPercentage.toFixed(0)}% discount`,
        );
      } else if (data.discountPercentage < 5) {
        reasons.push("Minimal discount from retail price");
      }
    }

    // 2. Resale margin analysis (retail vs Bricklink)
    if (
      data.currentRetailPrice && data.bricklink?.current.newAvg
    ) {
      const marginScore = this.analyzeResaleMargin(
        data.currentRetailPrice,
        data.bricklink.current.newAvg,
      );
      scores.push({ score: marginScore, weight: 0.35 });

      const margin =
        ((data.bricklink.current.newAvg - data.currentRetailPrice) /
          data.currentRetailPrice) * 100;
      dataPoints.currentMargin = margin;

      if (margin > 50) {
        reasons.push(
          `Excellent ${margin.toFixed(0)}% profit margin vs current resale`,
        );
      } else if (margin > 25) {
        reasons.push(`Good ${margin.toFixed(0)}% profit margin potential`);
      } else if (margin < 0) {
        reasons.push(`Currently selling below retail (${margin.toFixed(0)}%)`);
      }
    }

    // 3. Price appreciation trend analysis
    if (
      data.bricklink?.sixMonth.newAvg &&
      data.bricklink?.current.newAvg
    ) {
      const appreciationScore = this.analyzePriceAppreciation(
        data.bricklink.sixMonth.newAvg,
        data.bricklink.current.newAvg,
      );
      scores.push({ score: appreciationScore, weight: 0.25 });

      const appreciation = this.percentageChange(
        data.bricklink.sixMonth.newAvg,
        data.bricklink.current.newAvg,
      );
      dataPoints.sixMonthAppreciation = appreciation;

      if (appreciation > 20) {
        reasons.push(
          `Strong upward price trend (+${
            appreciation.toFixed(0)
          }% over 6 months)`,
        );
      } else if (appreciation > 10) {
        reasons.push(`Positive price momentum (+${appreciation.toFixed(0)}%)`);
      } else if (appreciation < -10) {
        reasons.push(
          `Declining resale value (${appreciation.toFixed(0)}% over 6 months)`,
        );
      }
    }

    // 4. Price volatility/stability (range analysis)
    if (
      data.bricklink?.current.newMin &&
      data.bricklink?.current.newMax &&
      data.bricklink?.current.newAvg
    ) {
      const volatilityScore = this.analyzeVolatility(
        data.bricklink.current.newMin,
        data.bricklink.current.newMax,
        data.bricklink.current.newAvg,
      );
      scores.push({ score: volatilityScore, weight: 0.1 });

      const range =
        ((data.bricklink.current.newMax - data.bricklink.current.newMin) /
          data.bricklink.current.newAvg) * 100;
      dataPoints.priceVolatility = range;

      if (range < 20) {
        reasons.push("Stable resale pricing");
      } else if (range > 50) {
        reasons.push("High price volatility in resale market");
      }
    }

    // Calculate final score
    const finalScore = scores.length > 0 ? this.weightedAverage(scores) : 50; // Neutral if no data

    // Calculate confidence based on data availability
    const confidence = this.calculateConfidence([
      data.currentRetailPrice,
      data.discountPercentage,
      data.bricklink?.current.newAvg,
      data.bricklink?.sixMonth.newAvg,
      data.bricklink?.current.newMin,
      data.bricklink?.current.newMax,
    ]);

    return {
      value: Math.round(finalScore),
      confidence,
      reasoning: reasons.length > 0
        ? this.formatReasoning(reasons)
        : "Insufficient pricing data for analysis.",
      dataPoints,
    };
  }

  /**
   * Score discount depth (higher discounts = better for investment)
   */
  private analyzeDiscount(discountPercentage: number): number {
    // 0% = 50, 50% = 100
    return 50 + (discountPercentage * 1.0);
  }

  /**
   * Score resale margin potential
   */
  private analyzeResaleMargin(
    retailPrice: number,
    resalePrice: number,
  ): number {
    const marginPercentage = ((resalePrice - retailPrice) / retailPrice) * 100;

    // Scoring:
    // <0% = 0-40 (selling below retail is bad)
    // 0-20% = 40-60 (minimal margin)
    // 20-50% = 60-80 (good margin)
    // 50-100% = 80-100 (excellent margin)
    // >100% = 100 (exceptional)

    if (marginPercentage < 0) {
      return Math.max(0, 40 + marginPercentage); // Penalize negative margins
    } else if (marginPercentage < 20) {
      return 40 + (marginPercentage / 20) * 20; // 40-60
    } else if (marginPercentage < 50) {
      return 60 + ((marginPercentage - 20) / 30) * 20; // 60-80
    } else if (marginPercentage < 100) {
      return 80 + ((marginPercentage - 50) / 50) * 20; // 80-100
    } else {
      return 100;
    }
  }

  /**
   * Score price appreciation trend
   */
  private analyzePriceAppreciation(
    sixMonthAvg: number,
    currentAvg: number,
  ): number {
    const appreciationPercentage = this.percentageChange(
      sixMonthAvg,
      currentAvg,
    );

    // Scoring:
    // <-20% = 0 (declining rapidly)
    // -20-0% = 20-50 (declining)
    // 0-10% = 50-70 (stable/slight growth)
    // 10-30% = 70-90 (good growth)
    // >30% = 90-100 (excellent growth)

    if (appreciationPercentage < -20) {
      return 0;
    } else if (appreciationPercentage < 0) {
      return 20 + ((appreciationPercentage + 20) / 20) * 30; // 20-50
    } else if (appreciationPercentage < 10) {
      return 50 + (appreciationPercentage / 10) * 20; // 50-70
    } else if (appreciationPercentage < 30) {
      return 70 + ((appreciationPercentage - 10) / 20) * 20; // 70-90
    } else {
      return Math.min(100, 90 + ((appreciationPercentage - 30) / 10)); // 90-100
    }
  }

  /**
   * Score price volatility (lower volatility is better for predictable investments)
   */
  private analyzeVolatility(
    min: number,
    max: number,
    avg: number,
  ): number {
    const rangePercentage = ((max - min) / avg) * 100;

    // Lower volatility = higher score
    // <10% = 90-100 (very stable)
    // 10-30% = 70-90 (stable)
    // 30-60% = 40-70 (moderate volatility)
    // >60% = 0-40 (high volatility)

    if (rangePercentage < 10) {
      return 90 + (10 - rangePercentage); // 90-100
    } else if (rangePercentage < 30) {
      return 70 + ((30 - rangePercentage) / 20) * 20; // 70-90
    } else if (rangePercentage < 60) {
      return 40 + ((60 - rangePercentage) / 30) * 30; // 40-70
    } else {
      return Math.max(0, 40 - ((rangePercentage - 60) / 10)); // 0-40
    }
  }
}
