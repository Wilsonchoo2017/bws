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
      demand: 0.55, // Highest priority - need active buyers (40% + 15%)
      availability: 0.35, // Important - low stock creates urgency (20% + 15%)
      quality: 0.10, // Moderate priority - reputation matters (5% + 5%)
    };

    super(
      "Quick Flip",
      "Identifies sets with immediate resale potential based on high current demand and low stock. Buy prices set aggressively for fast turnover.",
      weights,
    );
  }

  // Override interpret to add quick flip specific metrics
  override interpret(scores: DimensionalScores): ProductRecommendation {
    const recommendation = super.interpret(scores);

    // For quick flips, time horizon is immediate
    recommendation.timeHorizon = "Immediate - 1 month";

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
