/**
 * InvestmentFocusStrategy - Optimized for long-term investment returns
 * Prioritizes: retirement timing, price appreciation, resale margins
 * Use case: Building investment portfolio for maximum ROI
 */

import { BaseStrategy } from "./BaseStrategy.ts";
import type {
  DimensionalScores,
  DimensionWeights,
  ProductRecommendation,
} from "../types.ts";

export class InvestmentFocusStrategy extends BaseStrategy {
  constructor() {
    const weights: DimensionWeights = {
      demand: 0.45, // Highest priority - no demand means no sale, regardless of price
      availability: 0.40, // Important - retirement timing creates scarcity
      quality: 0.15, // Moderate priority - ensures product appeal and collectability
    };

    super(
      "Investment Focus",
      "Identifies sets with best investment potential based on retirement timing and resale market activity. Buy prices calculated using value investing principles.",
      weights,
    );
  }

  // Override interpret to add investment-specific metrics
  override interpret(scores: DimensionalScores): ProductRecommendation {
    const recommendation = super.interpret(scores);

    // Estimate time horizon based on availability
    if (scores.availability) {
      const availabilityData = scores.availability.dataPoints as Record<
        string,
        number | boolean
      >;
      if (
        availabilityData.daysUntilRetirement !== undefined &&
        typeof availabilityData.daysUntilRetirement === "number"
      ) {
        const days = availabilityData.daysUntilRetirement;
        if (days < 90) {
          recommendation.timeHorizon = "1-3 months post-retirement";
        } else if (days < 180) {
          recommendation.timeHorizon = "3-6 months post-retirement";
        } else if (days < 365) {
          recommendation.timeHorizon = "6-12 months post-retirement";
        } else {
          recommendation.timeHorizon = "12+ months post-retirement";
        }
      } else if (availabilityData.retiringSoon) {
        recommendation.timeHorizon = "6-12 months post-retirement";
      } else {
        recommendation.timeHorizon = "12-24 months (active set)";
      }

      if (
        availabilityData.daysUntilRetirement !== undefined &&
        typeof availabilityData.daysUntilRetirement === "number" &&
        availabilityData.daysUntilRetirement > 365
      ) {
        recommendation.risks.push(
          "Long time until retirement - capital will be tied up",
        );
      }
    }

    // Add investment-specific opportunities
    if (
      scores.availability &&
      scores.demand &&
      scores.availability.value >= 70 &&
      scores.demand.value >= 60
    ) {
      recommendation.opportunities.push(
        "Optimal investment window - retiring soon with strong resale market",
      );
    }

    // Add investment-specific risks
    if (scores.demand && scores.demand.value < 40) {
      recommendation.risks.push(
        "Low demand may impact resale velocity after retirement",
      );
    }

    return recommendation;
  }

  // Override urgency to be more investment-focused
  protected override determineUrgency(
    availabilityScore: number,
  ): "urgent" | "moderate" | "low" | "no_rush" {
    // More aggressive urgency for investment timing
    if (availabilityScore >= 80) return "urgent"; // Sweet spot for buying
    if (availabilityScore >= 60) return "moderate"; // Good window
    if (availabilityScore >= 35) return "low"; // Early but acceptable
    return "no_rush"; // Too early for investment
  }
}
