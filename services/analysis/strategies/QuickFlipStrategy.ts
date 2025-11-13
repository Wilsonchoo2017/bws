/**
 * QuickFlipStrategy - Optimized for fast turnaround resales
 * Prioritizes: current demand, low stock, existing margins
 * Use case: Quick profits on in-demand items with immediate resale potential
 */

import { BaseStrategy } from "./BaseStrategy.ts";
import type {
  DimensionalScores,
  DimensionWeights,
  ProductRecommendation,
} from "../types.ts";

export class QuickFlipStrategy extends BaseStrategy {
  constructor() {
    const weights: DimensionWeights = {
      demand: 0.40, // Highest priority - need active buyers
      pricing: 0.35, // Very important - current margins matter most
      availability: 0.20, // Important - low stock creates urgency
      quality: 0.05, // Lower priority - speed over perfection
    };

    super(
      "Quick Flip",
      "Identifies sets with immediate resale potential based on high current demand, good margins, and low stock. Best for fast turnover and quick profits.",
      weights,
    );
  }

  // Override interpret to add quick flip specific metrics
  override interpret(scores: DimensionalScores): ProductRecommendation {
    const recommendation = super.interpret(scores);

    // For quick flips, focus on current margins
    if (scores.pricing) {
      const pricingData = scores.pricing.dataPoints as Record<string, number>;
      if (pricingData.currentMargin !== undefined) {
        recommendation.estimatedROI = pricingData.currentMargin;
        recommendation.timeHorizon = "Immediate - 1 month";
      } else {
        recommendation.timeHorizon = "1-3 months";
      }

      if (
        pricingData.currentMargin !== undefined &&
        pricingData.currentMargin < 15
      ) {
        recommendation.risks.push(
          "Thin margins reduce profit potential for quick flips",
        );
      }
    } else {
      recommendation.timeHorizon = "1-3 months";
    }

    // Add quick flip specific opportunities
    if (scores.demand) {
      const demandData = scores.demand.dataPoints as Record<string, number>;

      if (
        demandData.unitsSold !== undefined &&
        demandData.unitsSold > 500
      ) {
        recommendation.opportunities.push(
          "High sales velocity indicates strong immediate demand",
        );
      }

      if (
        demandData.bricklinkTimesSold !== undefined &&
        demandData.bricklinkTimesSold > 50
      ) {
        recommendation.opportunities.push(
          "Active resale market with proven buyer demand",
        );
      }

      // Add quick flip specific risks
      if (scores.demand.value < 50) {
        recommendation.risks.push(
          "Lower demand may slow resale velocity",
        );
      }
    }

    if (scores.availability) {
      const availabilityData = scores.availability.dataPoints as Record<
        string,
        number | boolean
      >;

      if (
        availabilityData.currentStock !== undefined &&
        typeof availabilityData.currentStock === "number" &&
        availabilityData.currentStock < 20
      ) {
        recommendation.opportunities.push(
          "Low stock creates buying urgency for customers",
        );
      }

      if (
        availabilityData.currentStock !== undefined &&
        typeof availabilityData.currentStock === "number" &&
        availabilityData.currentStock > 200
      ) {
        recommendation.risks.push(
          "High stock availability may limit price appreciation",
        );
      }
    }

    return recommendation;
  }

  // Override urgency to focus on immediate opportunities
  protected override determineUrgency(
    availabilityScore: number,
  ): "urgent" | "moderate" | "low" | "no_rush" {
    // For quick flips, urgency is about scarcity NOW
    if (availabilityScore >= 80) return "urgent"; // Very low stock
    if (availabilityScore >= 60) return "moderate"; // Low stock
    if (availabilityScore >= 40) return "low"; // Moderate stock
    return "no_rush"; // High stock - wait for better opportunity
  }

  // Override action to be more aggressive on high-demand items
  protected override determineAction(
    score: number,
  ): "strong_buy" | "buy" | "hold" | "pass" {
    if (score >= 75) return "strong_buy"; // Lower threshold for quick wins
    if (score >= 60) return "buy";
    if (score >= 45) return "hold";
    return "pass";
  }
}
