/**
 * AvailabilityAnalyzer - Analyzes stock and retirement urgency
 * Focuses on: stock levels, retirement timing, scarcity signals
 */

import { BaseAnalyzer } from "./BaseAnalyzer.ts";
import type { AnalysisScore, AvailabilityData } from "../types.ts";

export class AvailabilityAnalyzer extends BaseAnalyzer<AvailabilityData> {
  constructor() {
    super(
      "Availability Analyzer",
      "Evaluates stock availability, retirement urgency, and scarcity",
    );
  }

  async analyze(data: AvailabilityData): Promise<AnalysisScore | null> {
    // Prerequisite check: Need at least retirement info OR stock data
    const hasRetirementData = data.retiringSoon !== undefined ||
      data.expectedRetirementDate !== undefined;
    const hasStockData = data.currentStock !== undefined;
    const hasActiveStatus = data.isActive !== undefined;

    if (!hasRetirementData && !hasStockData && !hasActiveStatus) {
      return null; // Skip analysis - insufficient availability data
    }

    const scores: Array<{ score: number; weight: number }> = [];
    const reasons: string[] = [];
    const dataPoints: Record<string, unknown> = {};

    // 1. Retirement urgency analysis (critical for investment)
    if (data.retiringSoon !== undefined || data.expectedRetirementDate) {
      const retirementScore = this.analyzeRetirement(
        data.retiringSoon,
        data.expectedRetirementDate,
        data.daysUntilRetirement,
      );
      scores.push({ score: retirementScore, weight: 0.5 }); // Highest weight for investment

      if (data.retiringSoon) {
        dataPoints.retiringSoon = true;

        if (
          data.daysUntilRetirement !== undefined &&
          data.daysUntilRetirement > 0
        ) {
          dataPoints.daysUntilRetirement = data.daysUntilRetirement;

          if (data.daysUntilRetirement < 30) {
            reasons.push(
              `URGENT: Retiring in ${data.daysUntilRetirement} days`,
            );
          } else if (data.daysUntilRetirement < 90) {
            reasons.push(
              `Retiring soon (${
                Math.round(data.daysUntilRetirement / 30)
              } months)`,
            );
          } else if (data.daysUntilRetirement < 180) {
            reasons.push("Expected to retire within 6 months");
          }
        } else if (data.expectedRetirementDate) {
          const daysUntil = this.daysBetween(
            new Date(),
            new Date(data.expectedRetirementDate),
          );
          reasons.push(`Retiring in ${Math.round(daysUntil / 30)} months`);
        } else {
          reasons.push("Marked as retiring soon");
        }
      } else {
        reasons.push("Not expected to retire soon");
      }
    }

    // 2. Stock availability analysis
    if (data.currentStock !== undefined) {
      const stockScore = this.analyzeStock(data.currentStock);
      scores.push({ score: stockScore, weight: 0.3 });

      dataPoints.currentStock = data.currentStock;

      if (data.currentStock === 0) {
        reasons.push("Out of stock");
      } else if (data.currentStock < 10) {
        reasons.push(`Limited stock (${data.currentStock} units)`);
      } else if (data.currentStock < 50) {
        reasons.push(`Low stock (${data.currentStock} units)`);
      } else if (data.currentStock > 500) {
        reasons.push("Abundant stock available");
      }
    }

    // 3. Platform availability status
    if (!data.isActive) {
      scores.push({ score: 100, weight: 0.2 }); // High score if delisted
      dataPoints.isActive = false;
      reasons.push("Already delisted/retired from platform");
    } else {
      scores.push({ score: 30, weight: 0.2 }); // Lower score if still available
      dataPoints.isActive = true;
    }

    // Calculate final score
    const finalScore = scores.length > 0 ? this.weightedAverage(scores) : 50; // Neutral if no data

    // Calculate confidence based on data availability
    const confidence = this.calculateConfidence([
      data.retiringSoon,
      data.expectedRetirementDate,
      data.currentStock,
      data.isActive,
    ]);

    return {
      value: Math.round(finalScore),
      confidence,
      reasoning: reasons.length > 0
        ? this.formatReasoning(reasons)
        : "Insufficient availability data for analysis.",
      dataPoints,
    };
  }

  /**
   * Score retirement urgency (higher urgency = higher score for investment)
   */
  private analyzeRetirement(
    retiringSoon?: boolean,
    expectedDate?: Date,
    daysUntil?: number,
  ): number {
    // Not retiring = low score (plenty of time, less urgent)
    if (!retiringSoon) return 20;

    // Calculate days until retirement
    let days = daysUntil;
    if (!days && expectedDate) {
      days = this.daysBetween(new Date(), new Date(expectedDate));
    }

    if (!days || days < 0) {
      // Already retired or no date info
      return 40; // Some value but not ideal (missed the boat)
    }

    // Scoring based on urgency (investment window)
    // 0-30 days = 95-100 (critical urgency - last chance)
    // 30-90 days = 80-95 (high urgency - good window)
    // 90-180 days = 60-80 (moderate urgency - decent window)
    // 180-365 days = 40-60 (low urgency - early but safe)
    // >365 days = 20-40 (very low urgency - too early)

    if (days < 30) {
      return 95 + ((30 - days) / 30) * 5; // 95-100
    } else if (days < 90) {
      return 80 + ((90 - days) / 60) * 15; // 80-95
    } else if (days < 180) {
      return 60 + ((180 - days) / 90) * 20; // 60-80
    } else if (days < 365) {
      return 40 + ((365 - days) / 185) * 20; // 40-60
    } else {
      return Math.max(20, 40 - ((days - 365) / 365) * 20); // 20-40
    }
  }

  /**
   * Score stock availability (lower stock = higher score for scarcity)
   */
  private analyzeStock(stock: number): number {
    // For investment purposes, lower stock is better (scarcity)
    // 0 = 100 (out of stock - highest scarcity)
    // 1-5 = 90-100 (critical low)
    // 5-20 = 70-90 (low stock)
    // 20-100 = 40-70 (moderate)
    // 100-500 = 20-40 (high stock)
    // >500 = 0-20 (abundant)

    if (stock === 0) return 100;
    if (stock < 5) return 90 + ((5 - stock) / 5) * 10; // 90-100
    if (stock < 20) return 70 + ((20 - stock) / 15) * 20; // 70-90
    if (stock < 100) return 40 + ((100 - stock) / 80) * 30; // 40-70
    if (stock < 500) return 20 + ((500 - stock) / 400) * 20; // 20-40
    return Math.max(0, 20 - ((stock - 500) / 500) * 20); // 0-20
  }
}
