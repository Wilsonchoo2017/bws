/**
 * QualityCalculator Service
 *
 * Calculates quality score (0-100) based on set characteristics:
 * - Parts-per-dollar (PPD) value proposition
 * - Build complexity (parts count)
 * - Theme collectibility premium
 * - Production scarcity indicators
 *
 * Used in DataAggregationService to replace hardcoded quality scores
 * with data-driven calculations.
 */

import { QUALITY_CALCULATOR_CONFIG as CONFIG } from "./QualityCalculatorConfig.ts";
import type { Cents } from "../../types/price.ts";
import { DataValidator } from "./DataValidator.ts";

/**
 * Input data for quality calculation
 * Sourced from: WorldBricks, BrickLink, product metadata
 */
export interface QualityCalculatorInput {
  // Parts-Per-Dollar calculation
  partsCount?: number; // From WorldBricks
  msrp?: Cents; // From WorldBricks or manual entry

  // Complexity indicator
  // (partsCount already used above)

  // Theme premium
  theme?: string; // From product metadata

  // Scarcity indicators
  availableLots?: number; // From BrickLink
  availableQty?: number; // From BrickLink (backup indicator)

  // Optional: Production run indicators
  yearReleased?: number; // From WorldBricks
  yearRetired?: number; // From WorldBricks
  limitedEdition?: boolean; // From product metadata
}

/**
 * Component score breakdown
 */
interface ComponentScore {
  score: number; // Raw score (0-100)
  weightedScore: number; // score × weight
  notes: string; // Human-readable explanation
}

/**
 * Quality score output with component breakdown
 */
export interface QualityScore {
  score: number; // Overall quality score (0-100)
  confidence: number; // Confidence level (0-1)
  components: {
    ppdScore: ComponentScore;
    complexityScore: ComponentScore;
    themePremium: ComponentScore;
    scarcityScore: ComponentScore;
  };
  dataQuality: {
    hasParts: boolean;
    hasMsrp: boolean;
    hasTheme: boolean;
    hasAvailability: boolean;
  };
}

export class QualityCalculator {
  /**
   * Calculate overall quality score from input data
   */
  static calculate(input: QualityCalculatorInput): QualityScore {
    // Validate and sanitize input
    const validation = DataValidator.validateQualityInput(input);
    if (!validation.isValid || !validation.data) {
      // Return default score with low confidence if validation fails
      console.warn(
        "[QualityCalculator] Validation failed:",
        validation.warnings,
      );
      return this.createDefaultScore(validation.warnings);
    }

    // Log warnings if any
    if (validation.warnings.length > 0) {
      console.warn(
        "[QualityCalculator] Validation warnings:",
        validation.warnings,
      );
    }

    // Use sanitized data for calculations
    const sanitizedInput = validation.data;

    const ppdScore = this.calculatePPDScore(sanitizedInput);
    const complexityScore = this.calculateComplexityScore(sanitizedInput);
    const themePremium = this.calculateThemePremium(sanitizedInput);
    const scarcityScore = this.calculateScarcityScore(sanitizedInput);

    // Sum weighted scores
    const overallScore = ppdScore.weightedScore +
      complexityScore.weightedScore +
      themePremium.weightedScore +
      scarcityScore.weightedScore;

    // Calculate confidence based on data availability
    const confidence = this.calculateConfidence(sanitizedInput);

    // Track data quality
    const dataQuality = {
      hasParts: sanitizedInput.partsCount !== undefined &&
        sanitizedInput.partsCount !== null,
      hasMsrp: sanitizedInput.msrp !== undefined &&
        sanitizedInput.msrp !== null,
      hasTheme: sanitizedInput.theme !== undefined &&
        sanitizedInput.theme !== null && sanitizedInput.theme.trim() !== "",
      hasAvailability: sanitizedInput.availableLots !== undefined &&
        sanitizedInput.availableLots !== null,
    };

    return {
      score: Math.round(overallScore),
      confidence,
      components: {
        ppdScore,
        complexityScore,
        themePremium,
        scarcityScore,
      },
      dataQuality,
    };
  }

  /**
   * Component 1: Parts-Per-Dollar (PPD) Score (40% weight)
   * Measures value proposition: higher PPD = better value
   */
  private static calculatePPDScore(
    input: QualityCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.PPD_SCORE;

    // Missing data check
    if (
      !input.partsCount ||
      !input.msrp ||
      input.partsCount < CONFIG.MIN_DATA_REQUIREMENTS.MIN_PARTS_FOR_PPD ||
      input.msrp < CONFIG.MIN_DATA_REQUIREMENTS.MIN_MSRP_FOR_PPD
    ) {
      return {
        score: CONFIG.DEFAULTS.SCORE,
        weightedScore: CONFIG.DEFAULTS.SCORE * weight,
        notes: "(insufficient data)",
      };
    }

    // Calculate PPD
    const msrpDollars = input.msrp / 100;
    const ppd = input.partsCount / msrpDollars;

    // Score based on thresholds
    let score: number;
    let notes: string;

    if (ppd >= CONFIG.PPD_SCORE.EXCELLENT) {
      score = 100;
      notes = `(excellent: ${ppd.toFixed(1)} PPD)`;
    } else if (ppd >= CONFIG.PPD_SCORE.VERY_GOOD) {
      // 85-100: Linear interpolation
      const range = CONFIG.PPD_SCORE.EXCELLENT - CONFIG.PPD_SCORE.VERY_GOOD;
      const position = (ppd - CONFIG.PPD_SCORE.VERY_GOOD) / range;
      score = 85 + position * 15;
      notes = `(very good: ${ppd.toFixed(1)} PPD)`;
    } else if (ppd >= CONFIG.PPD_SCORE.GOOD) {
      // 70-85: Linear interpolation
      const range = CONFIG.PPD_SCORE.VERY_GOOD - CONFIG.PPD_SCORE.GOOD;
      const position = (ppd - CONFIG.PPD_SCORE.GOOD) / range;
      score = 70 + position * 15;
      notes = `(good: ${ppd.toFixed(1)} PPD)`;
    } else if (ppd >= CONFIG.PPD_SCORE.FAIR) {
      // 50-70: Linear interpolation
      const range = CONFIG.PPD_SCORE.GOOD - CONFIG.PPD_SCORE.FAIR;
      const position = (ppd - CONFIG.PPD_SCORE.FAIR) / range;
      score = 50 + position * 20;
      notes = `(fair: ${ppd.toFixed(1)} PPD)`;
    } else if (ppd >= CONFIG.PPD_SCORE.POOR) {
      // 30-50: Linear interpolation
      const range = CONFIG.PPD_SCORE.FAIR - CONFIG.PPD_SCORE.POOR;
      const position = (ppd - CONFIG.PPD_SCORE.POOR) / range;
      score = 30 + position * 20;
      notes = `(poor: ${ppd.toFixed(1)} PPD)`;
    } else {
      // 0-30: Linear interpolation from 0 to POOR
      const position = ppd / CONFIG.PPD_SCORE.POOR;
      score = position * 30;
      notes = `(very poor: ${ppd.toFixed(1)} PPD)`;
    }

    return {
      score: Math.round(score),
      weightedScore: score * weight,
      notes,
    };
  }

  /**
   * Component 2: Complexity Score (30% weight)
   * Based on parts count as complexity indicator
   */
  private static calculateComplexityScore(
    input: QualityCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.COMPLEXITY_SCORE;

    // Missing data check
    if (
      !input.partsCount ||
      input.partsCount < CONFIG.MIN_DATA_REQUIREMENTS.MIN_PARTS_FOR_PPD
    ) {
      return {
        score: CONFIG.DEFAULTS.SCORE,
        weightedScore: CONFIG.DEFAULTS.SCORE * weight,
        notes: "(no parts data)",
      };
    }

    const parts = input.partsCount;
    let score: number;
    let notes: string;

    if (parts >= CONFIG.COMPLEXITY_SCORE.MASSIVE) {
      score = 100;
      notes = `(massive: ${parts} pieces)`;
    } else if (parts >= CONFIG.COMPLEXITY_SCORE.VERY_LARGE) {
      // 85-100: Linear interpolation
      const range = CONFIG.COMPLEXITY_SCORE.MASSIVE -
        CONFIG.COMPLEXITY_SCORE.VERY_LARGE;
      const position = (parts - CONFIG.COMPLEXITY_SCORE.VERY_LARGE) / range;
      score = 85 + position * 15;
      notes = `(very large: ${parts} pieces)`;
    } else if (parts >= CONFIG.COMPLEXITY_SCORE.LARGE) {
      // 70-85
      const range = CONFIG.COMPLEXITY_SCORE.VERY_LARGE -
        CONFIG.COMPLEXITY_SCORE.LARGE;
      const position = (parts - CONFIG.COMPLEXITY_SCORE.LARGE) / range;
      score = 70 + position * 15;
      notes = `(large: ${parts} pieces)`;
    } else if (parts >= CONFIG.COMPLEXITY_SCORE.MEDIUM) {
      // 55-70
      const range = CONFIG.COMPLEXITY_SCORE.LARGE -
        CONFIG.COMPLEXITY_SCORE.MEDIUM;
      const position = (parts - CONFIG.COMPLEXITY_SCORE.MEDIUM) / range;
      score = 55 + position * 15;
      notes = `(medium: ${parts} pieces)`;
    } else if (parts >= CONFIG.COMPLEXITY_SCORE.MODERATE) {
      // 40-55
      const range = CONFIG.COMPLEXITY_SCORE.MEDIUM -
        CONFIG.COMPLEXITY_SCORE.MODERATE;
      const position = (parts - CONFIG.COMPLEXITY_SCORE.MODERATE) / range;
      score = 40 + position * 15;
      notes = `(moderate: ${parts} pieces)`;
    } else if (parts >= CONFIG.COMPLEXITY_SCORE.SMALL) {
      // 25-40
      const range = CONFIG.COMPLEXITY_SCORE.MODERATE -
        CONFIG.COMPLEXITY_SCORE.SMALL;
      const position = (parts - CONFIG.COMPLEXITY_SCORE.SMALL) / range;
      score = 25 + position * 15;
      notes = `(small: ${parts} pieces)`;
    } else {
      // 0-25: Linear from 0 to SMALL threshold
      const position = parts / CONFIG.COMPLEXITY_SCORE.SMALL;
      score = position * 25;
      notes = `(very small: ${parts} pieces)`;
    }

    return {
      score: Math.round(score),
      weightedScore: score * weight,
      notes,
    };
  }

  /**
   * Component 3: Theme Premium (20% weight)
   * Certain themes historically appreciate better
   */
  private static calculateThemePremium(
    input: QualityCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.THEME_PREMIUM;

    // Missing data check
    if (!input.theme || input.theme.trim() === "") {
      return {
        score: CONFIG.DEFAULTS.THEME_SCORE,
        weightedScore: CONFIG.DEFAULTS.THEME_SCORE * weight,
        notes: "(no theme data)",
      };
    }

    const theme = input.theme.trim();
    let score: number;
    let notes: string;

    // Check premium themes (Tier 1: 100 points)
    if (CONFIG.THEME_PREMIUM.PREMIUM_THEMES.includes(theme)) {
      score = 100;
      notes = `(premium: ${theme})`;
    } // Check strong themes (Tier 2: 75 points)
    else if (CONFIG.THEME_PREMIUM.STRONG_THEMES.includes(theme)) {
      score = 75;
      notes = `(strong: ${theme})`;
    } // Check moderate themes (Tier 3: 50 points)
    else if (CONFIG.THEME_PREMIUM.MODERATE_THEMES.includes(theme)) {
      score = 50;
      notes = `(moderate: ${theme})`;
    } // Default: 25 points (unknown/weak theme)
    else {
      score = 25;
      notes = `(standard: ${theme})`;
    }

    return {
      score,
      weightedScore: score * weight,
      notes,
    };
  }

  /**
   * Component 4: Scarcity Score (10% weight)
   * Based on available lots (fewer = scarcer)
   */
  private static calculateScarcityScore(
    input: QualityCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.SCARCITY_SCORE;

    // Missing data check
    if (input.availableLots === undefined || input.availableLots === null) {
      // Fallback to availableQty if lots not available
      if (input.availableQty !== undefined && input.availableQty !== null) {
        // Estimate lots as qty/3 (rough average)
        const estimatedLots = Math.ceil(input.availableQty / 3);
        return this.calculateScarcityFromLots(estimatedLots, weight, true);
      }

      return {
        score: CONFIG.DEFAULTS.SCORE,
        weightedScore: CONFIG.DEFAULTS.SCORE * weight,
        notes: "(no availability data)",
      };
    }

    return this.calculateScarcityFromLots(input.availableLots, weight, false);
  }

  /**
   * Helper: Calculate scarcity score from lot count
   */
  private static calculateScarcityFromLots(
    lots: number,
    weight: number,
    isEstimated: boolean,
  ): ComponentScore {
    let score: number;
    let notes: string;
    const suffix = isEstimated ? " est." : "";

    if (lots < CONFIG.SCARCITY_SCORE.ULTRA_RARE) {
      score = 100;
      notes = `(ultra rare: ${lots}${suffix} lots)`;
    } else if (lots < CONFIG.SCARCITY_SCORE.VERY_RARE) {
      // 85-100
      const range = CONFIG.SCARCITY_SCORE.VERY_RARE -
        CONFIG.SCARCITY_SCORE.ULTRA_RARE;
      const position = (lots - CONFIG.SCARCITY_SCORE.ULTRA_RARE) / range;
      score = 100 - position * 15; // Inverse: fewer = higher
      notes = `(very rare: ${lots}${suffix} lots)`;
    } else if (lots < CONFIG.SCARCITY_SCORE.RARE) {
      // 70-85
      const range = CONFIG.SCARCITY_SCORE.RARE -
        CONFIG.SCARCITY_SCORE.VERY_RARE;
      const position = (lots - CONFIG.SCARCITY_SCORE.VERY_RARE) / range;
      score = 85 - position * 15;
      notes = `(rare: ${lots}${suffix} lots)`;
    } else if (lots < CONFIG.SCARCITY_SCORE.LIMITED) {
      // 55-70
      const range = CONFIG.SCARCITY_SCORE.LIMITED - CONFIG.SCARCITY_SCORE.RARE;
      const position = (lots - CONFIG.SCARCITY_SCORE.RARE) / range;
      score = 70 - position * 15;
      notes = `(limited: ${lots}${suffix} lots)`;
    } else if (lots < CONFIG.SCARCITY_SCORE.COMMON) {
      // 40-55
      const range = CONFIG.SCARCITY_SCORE.COMMON -
        CONFIG.SCARCITY_SCORE.LIMITED;
      const position = (lots - CONFIG.SCARCITY_SCORE.LIMITED) / range;
      score = 55 - position * 15;
      notes = `(common: ${lots}${suffix} lots)`;
    } else if (lots < CONFIG.SCARCITY_SCORE.ABUNDANT) {
      // 25-40
      const range = CONFIG.SCARCITY_SCORE.ABUNDANT -
        CONFIG.SCARCITY_SCORE.COMMON;
      const position = (lots - CONFIG.SCARCITY_SCORE.COMMON) / range;
      score = 40 - position * 15;
      notes = `(abundant: ${lots}${suffix} lots)`;
    } else {
      // 0-25: >200 lots
      const excessLots = lots - CONFIG.SCARCITY_SCORE.ABUNDANT;
      const position = Math.min(1, excessLots / 200); // Cap at 200 excess
      score = 25 - position * 25;
      notes = `(oversupplied: ${lots}${suffix} lots)`;
    }

    return {
      score: Math.round(score),
      weightedScore: score * weight,
      notes,
    };
  }

  /**
   * Calculate confidence level based on data completeness
   */
  private static calculateConfidence(input: QualityCalculatorInput): number {
    let confidence = 1.0; // Start with full confidence

    // Apply penalties for missing data
    if (
      !input.partsCount ||
      input.partsCount < CONFIG.MIN_DATA_REQUIREMENTS.MIN_PARTS_FOR_PPD
    ) {
      confidence -= CONFIG.CONFIDENCE_PENALTIES.NO_PARTS_COUNT;
    }

    if (
      !input.msrp ||
      input.msrp < CONFIG.MIN_DATA_REQUIREMENTS.MIN_MSRP_FOR_PPD
    ) {
      confidence -= CONFIG.CONFIDENCE_PENALTIES.NO_MSRP;
    }

    if (!input.theme || input.theme.trim() === "") {
      confidence -= CONFIG.CONFIDENCE_PENALTIES.NO_THEME;
    }

    if (input.availableLots === undefined && input.availableQty === undefined) {
      confidence -= CONFIG.CONFIDENCE_PENALTIES.NO_AVAILABILITY_DATA;
    }

    return Math.max(0, Math.min(1, confidence));
  }

  /**
   * Create default score when validation fails
   */
  private static createDefaultScore(_warnings: string[]): QualityScore {
    const defaultScore = CONFIG.DEFAULTS.SCORE;
    const defaultConfidence = CONFIG.DEFAULTS.CONFIDENCE;
    const weight = CONFIG.WEIGHTS;

    return {
      score: defaultScore,
      confidence: defaultConfidence,
      components: {
        ppdScore: {
          score: defaultScore,
          weightedScore: defaultScore * weight.PPD_SCORE,
          notes: "(validation failed)",
        },
        complexityScore: {
          score: defaultScore,
          weightedScore: defaultScore * weight.COMPLEXITY_SCORE,
          notes: "(validation failed)",
        },
        themePremium: {
          score: CONFIG.DEFAULTS.THEME_SCORE,
          weightedScore: CONFIG.DEFAULTS.THEME_SCORE * weight.THEME_PREMIUM,
          notes: "(validation failed)",
        },
        scarcityScore: {
          score: defaultScore,
          weightedScore: defaultScore * weight.SCARCITY_SCORE,
          notes: "(validation failed)",
        },
      },
      dataQuality: {
        hasParts: false,
        hasMsrp: false,
        hasTheme: false,
        hasAvailability: false,
      },
    };
  }
}
