/**
 * Base strategy class providing common recommendation logic
 * Following Strategy Pattern for different investment approaches
 */

import type {
  DimensionalScores,
  DimensionWeights,
  IStrategy,
  ProductRecommendation,
} from "../types.ts";

export abstract class BaseStrategy implements IStrategy {
  protected name: string;
  protected description: string;
  protected weights: DimensionWeights;

  constructor(
    name: string,
    description: string,
    weights: DimensionWeights,
  ) {
    this.name = name;
    this.description = description;
    this.weights = weights;
  }

  getName(): string {
    return this.name;
  }

  getDescription(): string {
    return this.description;
  }

  getWeights(): DimensionWeights {
    return this.weights;
  }

  /**
   * Calculate weighted overall score from dimensional scores
   */
  protected calculateOverallScore(scores: DimensionalScores): number {
    const weightedScores = [
      { score: scores.pricing.value, weight: this.weights.pricing },
      { score: scores.demand.value, weight: this.weights.demand },
      {
        score: scores.availability.value,
        weight: this.weights.availability,
      },
      { score: scores.quality.value, weight: this.weights.quality },
    ];

    const totalWeight = weightedScores.reduce(
      (sum, s) => sum + s.weight,
      0,
    );
    if (totalWeight === 0) return 0;

    const weightedSum = weightedScores.reduce(
      (sum, s) => sum + s.score * s.weight,
      0,
    );
    return weightedSum / totalWeight;
  }

  /**
   * Calculate overall confidence from dimensional confidences
   */
  protected calculateOverallConfidence(scores: DimensionalScores): number {
    const confidences = [
      scores.pricing.confidence,
      scores.demand.confidence,
      scores.availability.confidence,
      scores.quality.confidence,
    ];
    return confidences.reduce((sum, c) => sum + c, 0) / confidences.length;
  }

  /**
   * Determine action based on overall score
   */
  protected determineAction(
    score: number,
  ): "strong_buy" | "buy" | "hold" | "pass" {
    if (score >= 80) return "strong_buy";
    if (score >= 65) return "buy";
    if (score >= 45) return "hold";
    return "pass";
  }

  /**
   * Determine urgency based on availability score
   */
  protected determineUrgency(
    availabilityScore: number,
  ): "urgent" | "moderate" | "low" | "no_rush" {
    if (availabilityScore >= 85) return "urgent"; // Retiring soon or very low stock
    if (availabilityScore >= 65) return "moderate"; // Some urgency
    if (availabilityScore >= 40) return "low"; // Some time left
    return "no_rush"; // Plenty of time
  }

  /**
   * Generate reasoning from dimensional scores
   */
  protected generateReasoning(scores: DimensionalScores): string {
    const reasons: string[] = [];

    // Add top contributing factors
    const dimensions = [
      {
        name: "Pricing",
        score: scores.pricing.value,
        weight: this.weights.pricing,
      },
      {
        name: "Demand",
        score: scores.demand.value,
        weight: this.weights.demand,
      },
      {
        name: "Availability",
        score: scores.availability.value,
        weight: this.weights.availability,
      },
      {
        name: "Quality",
        score: scores.quality.value,
        weight: this.weights.quality,
      },
    ];

    // Sort by weighted contribution
    dimensions.sort((a, b) => b.score * b.weight - a.score * a.weight);

    // Add top 2 factors
    for (let i = 0; i < Math.min(2, dimensions.length); i++) {
      const dim = dimensions[i];
      if (dim.score >= 70) {
        reasons.push(`Strong ${dim.name.toLowerCase()} signals`);
      } else if (dim.score >= 50) {
        reasons.push(`Moderate ${dim.name.toLowerCase()}`);
      }
    }

    // Add warnings for low scores
    for (const dim of dimensions) {
      if (dim.score < 40 && dim.weight > 0.1) {
        reasons.push(`Weak ${dim.name.toLowerCase()}`);
      }
    }

    return reasons.join(". ") + ".";
  }

  /**
   * Identify risks based on dimensional scores
   */
  protected identifyRisks(scores: DimensionalScores): string[] {
    const risks: string[] = [];

    if (scores.pricing.value < 40) {
      risks.push("Poor pricing or negative margins");
    }
    if (scores.demand.value < 30) {
      risks.push("Low market demand or limited resale activity");
    }
    if (scores.availability.value < 30 && scores.availability.value > 0) {
      risks.push("Abundant stock may indicate slow-moving item");
    }
    if (scores.quality.value < 40) {
      risks.push("Quality concerns or untrusted seller");
    }

    // Confidence warnings
    if (scores.pricing.confidence < 0.5) {
      risks.push("Limited pricing data for accurate analysis");
    }
    if (scores.demand.confidence < 0.5) {
      risks.push("Insufficient demand data");
    }

    return risks;
  }

  /**
   * Identify opportunities based on dimensional scores
   */
  protected identifyOpportunities(scores: DimensionalScores): string[] {
    const opportunities: string[] = [];

    if (scores.pricing.value >= 75) {
      opportunities.push("Excellent profit margin potential");
    }
    if (scores.demand.value >= 75) {
      opportunities.push("Strong market demand and community interest");
    }
    if (scores.availability.value >= 75) {
      opportunities.push("Limited availability creates scarcity value");
    }
    if (scores.quality.value >= 80) {
      opportunities.push("High-quality product with good ratings");
    }

    // Combo opportunities
    if (scores.pricing.value >= 70 && scores.availability.value >= 70) {
      opportunities.push("Good margin with upcoming scarcity");
    }
    if (scores.demand.value >= 70 && scores.availability.value >= 70) {
      opportunities.push("High demand with limited supply");
    }

    return opportunities;
  }

  /**
   * Main interpretation method (to be optionally overridden by subclasses)
   */
  interpret(scores: DimensionalScores): ProductRecommendation {
    const overallScore = this.calculateOverallScore(scores);
    const confidence = this.calculateOverallConfidence(scores);
    const action = this.determineAction(overallScore);
    const urgency = this.determineUrgency(scores.availability.value);

    return {
      overall: {
        value: Math.round(overallScore),
        confidence,
        reasoning: this.generateReasoning(scores),
        dataPoints: {
          strategy: this.name,
          weights: this.weights,
        },
      },
      dimensions: scores,
      action,
      strategy: this.name,
      urgency,
      risks: this.identifyRisks(scores),
      opportunities: this.identifyOpportunities(scores),
      analyzedAt: new Date(),
    };
  }
}
