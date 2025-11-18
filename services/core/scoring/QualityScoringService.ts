/**
 * QualityScoringService - Unified quality scoring logic
 *
 * CONSOLIDATES:
 * - services/analysis/analyzers/QualityAnalyzer.ts (319 lines)
 * - services/value-investing/QualityCalculator.ts (499 lines)
 *
 * SOLID Principles Applied:
 * - Single Responsibility: Only calculates quality scores
 * - Open/Closed: Easy to add new components via configuration
 * - Dependency Inversion: Accepts abstract input interface
 *
 * Scoring Components (weighted):
 * 1. Parts-Per-Dollar (40%) - Value proposition
 * 2. Build Complexity (25%) - Parts count (engagement factor)
 * 3. Theme Premium (20%) - Collectibility of theme
 * 4. Scarcity (15%) - Production/availability scarcity
 */

import type { Cents } from "../../../types/price.ts";

/**
 * Input data for quality scoring
 */
export interface QualityScoringInput {
  // Parts-Per-Dollar calculation
  partsCount?: number; // Number of pieces
  msrp?: Cents; // Original retail price in cents

  // Theme collectibility
  theme?: string; // LEGO theme (Star Wars, Architecture, etc.)

  // Scarcity indicators
  availableLots?: number; // Number of competing sellers
  availableQty?: number; // Total units available

  // Production indicators
  yearReleased?: number;
  yearRetired?: number;
  limitedEdition?: boolean;
}

/**
 * Component score breakdown
 */
export interface ComponentScore {
  score: number; // 0-100 raw component score
  weight: number; // Component weight (0-1)
  weightedScore: number; // score * weight
  confidence: number; // Data quality confidence (0-1)
  notes?: string; // Explanation
}

/**
 * Quality score result
 */
export interface QualityScoringResult {
  score: number; // Final 0-100 score
  confidence: number; // Overall confidence (0-1)

  components?: {
    ppdScore: ComponentScore;
    complexityScore: ComponentScore;
    themePremium: ComponentScore;
    scarcityScore: ComponentScore;
  };

  metadata: {
    hasParts: boolean;
    hasMsrp: boolean;
    hasTheme: boolean;
    hasAvailability: boolean;
  };
}

/**
 * Theme multipliers for premium collectible themes
 */
const THEME_MULTIPLIERS: Record<string, number> = {
  "Star Wars": 1.30,
  "Harry Potter": 1.20,
  "Marvel": 1.15,
  "DC": 1.15,
  "Architecture": 1.25,
  "Creator Expert": 1.20,
  "Ideas": 1.15,
  "Technic": 1.10,
  "City": 1.0,
  "Friends": 0.95,
  "Duplo": 0.90,
  "DEFAULT": 1.0,
};

/**
 * Configuration for scoring weights
 */
const DEFAULT_WEIGHTS = {
  ppdScore: 0.40, // 40% - Most important (value proposition)
  complexityScore: 0.25, // 25% - Build engagement
  themePremium: 0.20, // 20% - Collectibility
  scarcityScore: 0.15, // 15% - Rarity factor
} as const;

/**
 * QualityScoringService - Instance-based service for testability
 */
export class QualityScoringService {
  constructor(
    private weights = DEFAULT_WEIGHTS,
    private themeMultipliers = THEME_MULTIPLIERS,
  ) {}

  /**
   * Calculate quality score from product characteristics
   */
  calculateScore(input: QualityScoringInput): QualityScoringResult {
    // Detect available data
    const hasParts = input.partsCount !== undefined && input.partsCount > 0;
    const hasMsrp = input.msrp !== undefined && input.msrp > 0;
    const hasTheme = input.theme !== undefined && input.theme.length > 0;
    const hasAvailability = input.availableLots !== undefined ||
      input.availableQty !== undefined;

    // If no data at all, return neutral score
    if (!hasParts && !hasMsrp && !hasTheme && !hasAvailability) {
      return {
        score: 50, // Neutral when no data
        confidence: 0,
        metadata: {
          hasParts: false,
          hasMsrp: false,
          hasTheme: false,
          hasAvailability: false,
        },
      };
    }

    // Calculate components
    const components = {
      ppdScore: this.calculatePPDScore(input),
      complexityScore: this.calculateComplexityScore(input),
      themePremium: this.calculateThemePremium(input),
      scarcityScore: this.calculateScarcityScore(input),
    };

    // Calculate weighted final score
    const finalScore = Object.values(components).reduce(
      (sum, component) => sum + component.weightedScore,
      0,
    );

    // Calculate overall confidence (average of component confidences)
    const overallConfidence = Object.values(components).reduce(
      (sum, component) => sum + component.confidence,
      0,
    ) / Object.values(components).length;

    return {
      score: this.clamp(Math.round(finalScore), 0, 100),
      confidence: this.clamp(overallConfidence, 0, 1),
      components,
      metadata: {
        hasParts,
        hasMsrp,
        hasTheme,
        hasAvailability,
      },
    };
  }

  /**
   * Component 1: Parts-Per-Dollar Score (40% weight)
   * Higher PPD = better value proposition
   */
  private calculatePPDScore(input: QualityScoringInput): ComponentScore {
    const parts = input.partsCount;
    const msrp = input.msrp;

    if (!parts || parts <= 0 || !msrp || msrp <= 0) {
      return {
        score: 50, // Neutral when no data
        weight: this.weights.ppdScore,
        weightedScore: 50 * this.weights.ppdScore,
        confidence: 0.1,
        notes: "No PPD data available",
      };
    }

    // Calculate parts per dollar
    const dollars = msrp / 100;
    const ppd = parts / dollars;

    // Score mapping (based on LEGO market norms):
    // PPD < 5 = 20 score (poor value)
    // PPD 5-7 = 50 score (average)
    // PPD 8-10 = 70 score (good value)
    // PPD 11-15 = 90 score (excellent value)
    // PPD > 15 = 100 score (exceptional value)

    let score: number;
    if (ppd < 5) score = 20 + (ppd / 5) * 30; // 20-50
    else if (ppd < 8) score = 50 + ((ppd - 5) / 3) * 20; // 50-70
    else if (ppd < 11) score = 70 + ((ppd - 8) / 3) * 20; // 70-90
    else if (ppd < 15) score = 90 + ((ppd - 11) / 4) * 10; // 90-100
    else score = 100;

    return {
      score: this.clamp(score, 0, 100),
      weight: this.weights.ppdScore,
      weightedScore: this.clamp(score, 0, 100) * this.weights.ppdScore,
      confidence: 0.9, // High confidence when we have both values
      notes: `${ppd.toFixed(1)} parts per dollar`,
    };
  }

  /**
   * Component 2: Build Complexity Score (25% weight)
   * More parts = more engaging build experience
   */
  private calculateComplexityScore(input: QualityScoringInput): ComponentScore {
    const parts = input.partsCount;

    if (!parts || parts <= 0) {
      return {
        score: 50, // Neutral
        weight: this.weights.complexityScore,
        weightedScore: 50 * this.weights.complexityScore,
        confidence: 0.1,
        notes: "No parts count data",
      };
    }

    // Score mapping:
    // < 100 parts = 30 score (very simple)
    // 100-300 parts = 50 score (simple)
    // 300-500 parts = 65 score (moderate)
    // 500-1000 parts = 80 score (complex)
    // 1000-2000 parts = 90 score (very complex)
    // > 2000 parts = 100 score (expert level)

    let score: number;
    if (parts < 100) score = 30;
    else if (parts < 300) score = 50;
    else if (parts < 500) score = 65;
    else if (parts < 1000) score = 80;
    else if (parts < 2000) score = 90;
    else score = 100;

    return {
      score,
      weight: this.weights.complexityScore,
      weightedScore: score * this.weights.complexityScore,
      confidence: 0.8,
      notes: `${parts} parts`,
    };
  }

  /**
   * Component 3: Theme Premium Score (20% weight)
   * Premium themes command higher collectibility
   */
  private calculateThemePremium(input: QualityScoringInput): ComponentScore {
    const theme = input.theme;

    if (!theme || theme.length === 0) {
      return {
        score: 50, // Neutral
        weight: this.weights.themePremium,
        weightedScore: 50 * this.weights.themePremium,
        confidence: 0.1,
        notes: "No theme data",
      };
    }

    // Get theme multiplier (default to 1.0 if not found)
    const multiplier = this.themeMultipliers[theme] ||
      this.themeMultipliers.DEFAULT;

    // Convert multiplier (0.9 - 1.3) to score (0-100)
    // 0.90 = 40 score (below average)
    // 1.00 = 50 score (average)
    // 1.15 = 75 score (good)
    // 1.30 = 100 score (premium)

    const score = 50 + ((multiplier - 1.0) / 0.30) * 50;

    return {
      score: this.clamp(score, 0, 100),
      weight: this.weights.themePremium,
      weightedScore: this.clamp(score, 0, 100) * this.weights.themePremium,
      confidence: 0.7,
      notes: `${theme} theme (${multiplier}x)`,
    };
  }

  /**
   * Component 4: Scarcity Score (15% weight)
   * Limited availability increases collectibility
   */
  private calculateScarcityScore(input: QualityScoringInput): ComponentScore {
    const lots = input.availableLots;
    const limited = input.limitedEdition;

    // Base score from availability
    let baseScore = 50; // Default neutral
    let confidence = 0.2;
    let notes = "No scarcity data";

    if (lots !== undefined && lots >= 0) {
      // Score mapping (inverse relationship):
      // 1-5 sellers = 100 score (very scarce)
      // 6-10 sellers = 80 score (scarce)
      // 11-20 sellers = 60 score (moderate)
      // 21-50 sellers = 40 score (common)
      // 51+ sellers = 20 score (abundant)

      if (lots <= 5) baseScore = 100;
      else if (lots <= 10) baseScore = 80;
      else if (lots <= 20) baseScore = 60;
      else if (lots <= 50) baseScore = 40;
      else baseScore = 20;

      confidence = 0.6;
      notes = `${lots} available sellers`;
    }

    // Boost for limited edition
    if (limited) {
      baseScore = Math.min(baseScore + 20, 100);
      confidence = Math.max(confidence, 0.7);
      notes += " (limited edition)";
    }

    return {
      score: baseScore,
      weight: this.weights.scarcityScore,
      weightedScore: baseScore * this.weights.scarcityScore,
      confidence,
      notes,
    };
  }

  /**
   * Utility: Clamp value to range
   */
  private clamp(value: number, min: number, max: number): number {
    return Math.max(min, Math.min(max, value));
  }
}
