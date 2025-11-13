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
   * Only includes dimensions with non-null scores
   */
  protected calculateOverallScore(scores: DimensionalScores): number {
    const weightedScores = [
      scores.demand
        ? { score: scores.demand.value, weight: this.weights.demand }
        : null,
      scores.availability
        ? {
          score: scores.availability.value,
          weight: this.weights.availability,
        }
        : null,
      scores.quality
        ? { score: scores.quality.value, weight: this.weights.quality }
        : null,
    ].filter((s) => s !== null) as Array<{ score: number; weight: number }>;

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
   * Only includes dimensions with non-null scores
   */
  protected calculateOverallConfidence(scores: DimensionalScores): number {
    const confidences = [
      scores.demand?.confidence,
      scores.availability?.confidence,
      scores.quality?.confidence,
    ].filter((c) => c !== undefined) as number[];

    if (confidences.length === 0) return 0;
    return confidences.reduce((sum, c) => sum + c, 0) / confidences.length;
  }

  /**
   * Determine action based on overall score and available dimensions
   */
  protected determineAction(
    score: number,
    availableDimensions: number,
  ): "strong_buy" | "buy" | "hold" | "pass" | "insufficient_data" {
    // Need at least 2 dimensions for a recommendation
    if (availableDimensions < 2) return "insufficient_data";

    if (score >= 80) return "strong_buy";
    if (score >= 65) return "buy";
    if (score >= 45) return "hold";
    return "pass";
  }

  /**
   * Determine urgency based on availability score
   */
  protected determineUrgency(
    availabilityScore: number | null,
  ): "urgent" | "moderate" | "low" | "no_rush" {
    if (availabilityScore === null) return "no_rush"; // No availability data
    if (availabilityScore >= 85) return "urgent"; // Retiring soon or very low stock
    if (availabilityScore >= 65) return "moderate"; // Some urgency
    if (availabilityScore >= 40) return "low"; // Some time left
    return "no_rush"; // Plenty of time
  }

  /**
   * Generate reasoning from dimensional scores
   * Only includes dimensions with non-null scores
   */
  protected generateReasoning(scores: DimensionalScores): string {
    const reasons: string[] = [];

    // Add top contributing factors (filter out nulls)
    const dimensions = [
      scores.demand
        ? {
          name: "Demand",
          score: scores.demand.value,
          weight: this.weights.demand,
        }
        : null,
      scores.availability
        ? {
          name: "Availability",
          score: scores.availability.value,
          weight: this.weights.availability,
        }
        : null,
      scores.quality
        ? {
          name: "Quality",
          score: scores.quality.value,
          weight: this.weights.quality,
        }
        : null,
    ].filter((d) => d !== null) as Array<
      { name: string; score: number; weight: number }
    >;

    if (dimensions.length === 0) {
      return "Insufficient data for analysis.";
    }

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
   * Only includes dimensions with non-null scores
   */
  protected identifyRisks(scores: DimensionalScores): string[] {
    const risks: string[] = [];

    if (scores.demand && scores.demand.value < 30) {
      risks.push("Low market demand or limited resale activity");
    }
    if (
      scores.availability && scores.availability.value < 30 &&
      scores.availability.value > 0
    ) {
      risks.push("Abundant stock may indicate slow-moving item");
    }
    if (scores.quality && scores.quality.value < 40) {
      risks.push("Quality concerns or untrusted seller");
    }

    // Confidence warnings
    if (scores.demand && scores.demand.confidence < 0.5) {
      risks.push("Insufficient demand data");
    }

    return risks;
  }

  /**
   * Identify opportunities based on dimensional scores
   * Only includes dimensions with non-null scores
   */
  protected identifyOpportunities(scores: DimensionalScores): string[] {
    const opportunities: string[] = [];

    if (scores.demand && scores.demand.value >= 75) {
      opportunities.push("Strong market demand and community interest");
    }
    if (scores.availability && scores.availability.value >= 75) {
      opportunities.push("Limited availability creates scarcity value");
    }
    if (scores.quality && scores.quality.value >= 80) {
      opportunities.push("High-quality product with good ratings");
    }

    // Combo opportunities
    if (
      scores.demand && scores.availability &&
      scores.demand.value >= 70 && scores.availability.value >= 70
    ) {
      opportunities.push("High demand with limited supply");
    }

    return opportunities;
  }

  /**
   * Count available dimensions (non-null scores)
   */
  protected countAvailableDimensions(scores: DimensionalScores): number {
    let count = 0;
    if (scores.demand !== null) count++;
    if (scores.availability !== null) count++;
    if (scores.quality !== null) count++;
    return count;
  }

  /**
   * Main interpretation method (to be optionally overridden by subclasses)
   */
  interpret(scores: DimensionalScores): ProductRecommendation {
    const availableDimensions = this.countAvailableDimensions(scores);
    const overallScore = this.calculateOverallScore(scores);
    const confidence = this.calculateOverallConfidence(scores);
    const action = this.determineAction(overallScore, availableDimensions);
    const urgency = this.determineUrgency(
      scores.availability ? scores.availability.value : null,
    );

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
      availableDimensions,
      action,
      strategy: this.name,
      urgency,
      risks: this.identifyRisks(scores),
      opportunities: this.identifyOpportunities(scores),
      analyzedAt: new Date(),
    };
  }
}
