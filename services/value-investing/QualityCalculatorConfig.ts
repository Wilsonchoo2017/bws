/**
 * QualityCalculator Configuration
 *
 * Defines thresholds and weights for calculating quality score (0-100)
 * based on set characteristics, build complexity, and collectibility factors.
 */

export const QUALITY_CALCULATOR_CONFIG = {
  /**
   * Component weights (must sum to 1.0)
   */
  WEIGHTS: {
    PPD_SCORE: 0.40, // 40% - Parts per dollar value
    COMPLEXITY_SCORE: 0.30, // 30% - Build complexity/piece count
    THEME_PREMIUM: 0.20, // 20% - Collectible themes (Star Wars, etc.)
    SCARCITY_SCORE: 0.10, // 10% - Production run scarcity
  },

  /**
   * Parts-Per-Dollar (PPD) Scoring
   * Measures value proposition: pieces / (MSRP in dollars)
   * Higher PPD = better value = higher quality for investors
   */
  PPD_SCORE: {
    EXCELLENT: 12.0, // ≥12 PPD = 100 points (excellent value)
    VERY_GOOD: 10.0, // 10-12 PPD = 85 points
    GOOD: 8.0, // 8-10 PPD = 70 points
    FAIR: 6.0, // 6-8 PPD = 50 points
    POOR: 4.0, // 4-6 PPD = 30 points
    // <4 PPD = 0-30 points (poor value, likely minifigs/IP premium)
  },

  /**
   * Set Complexity Scoring
   * Based on absolute parts count (complexity indicator)
   * More complex sets tend to appreciate better
   */
  COMPLEXITY_SCORE: {
    MASSIVE: 5000, // ≥5000 pieces = 100 points (UCS, flagship sets)
    VERY_LARGE: 3000, // 3000-5000 = 85 points
    LARGE: 2000, // 2000-3000 = 70 points
    MEDIUM: 1000, // 1000-2000 = 55 points
    MODERATE: 500, // 500-1000 = 40 points
    SMALL: 200, // 200-500 = 25 points
    // <200 pieces = 0-25 points (polybags, small sets)
  },

  /**
   * Theme Premium Scoring
   * Certain themes historically appreciate better
   * Based on collector demand and brand strength
   */
  THEME_PREMIUM: {
    // Tier 1: Premium themes (100 points)
    PREMIUM_THEMES: [
      "Star Wars",
      "Ultimate Collector Series",
      "Ideas",
      "Architecture",
      "Creator Expert",
      "Modular Buildings",
    ],

    // Tier 2: Strong themes (75 points)
    STRONG_THEMES: [
      "Harry Potter",
      "Marvel",
      "DC",
      "Technic",
      "Castle",
      "Pirates",
      "Space",
      "Lord of the Rings",
      "Minecraft",
    ],

    // Tier 3: Moderate themes (50 points)
    MODERATE_THEMES: [
      "City",
      "Creator",
      "Ninjago",
      "Speed Champions",
      "Friends",
      "Jurassic World",
    ],
    // All others: 25 points (default)
  },

  /**
   * Scarcity Score
   * Based on availability indicators:
   * - Very few listings (scarce)
   * - High sales-to-listing ratio
   * - Production run indicators
   */
  SCARCITY_SCORE: {
    ULTRA_RARE: 10, // <10 lots available = 100 points
    VERY_RARE: 20, // 10-20 lots = 85 points
    RARE: 40, // 20-40 lots = 70 points
    LIMITED: 70, // 40-70 lots = 55 points
    COMMON: 100, // 70-100 lots = 40 points
    ABUNDANT: 200, // 100-200 lots = 25 points
    // >200 lots = 0-25 points (mass produced)
  },

  /**
   * Minimum data requirements for confidence scoring
   */
  MIN_DATA_REQUIREMENTS: {
    MIN_PARTS_FOR_PPD: 50, // Need 50+ parts for meaningful PPD
    MIN_MSRP_FOR_PPD: 500, // Need $5+ MSRP for meaningful PPD
    MIN_LISTINGS_FOR_SCARCITY: 5, // Need 5+ listings for scarcity calc
  },

  /**
   * Confidence penalties for missing/insufficient data
   */
  CONFIDENCE_PENALTIES: {
    NO_PARTS_COUNT: 0.40, // 40% confidence penalty
    NO_MSRP: 0.40, // 40% confidence penalty
    NO_THEME: 0.20, // 20% confidence penalty
    NO_AVAILABILITY_DATA: 0.20, // 20% confidence penalty
    INSUFFICIENT_PARTS: 0.20, // 20% confidence penalty
  },

  /**
   * Default values when data is missing
   * Philosophy: "Bad until proven" - assume worst case when data is missing
   */
  DEFAULTS: {
    SCORE: 0, // Pessimistic score - missing data is bad
    CONFIDENCE: 0.0, // No confidence (0%)
    THEME_SCORE: 0, // Default theme score (unknown theme)
  },
};

/**
 * Helper function to validate configuration
 */
export function validateQualityCalculatorConfig(): boolean {
  const weights = QUALITY_CALCULATOR_CONFIG.WEIGHTS;
  const sum = Object.values(weights).reduce((a, b) => a + b, 0);
  const isValid = Math.abs(sum - 1.0) < 0.001; // Allow floating point tolerance

  if (!isValid) {
    console.error(
      `[QualityCalculatorConfig] Invalid weights: sum = ${sum}, expected 1.0`,
    );
  }

  return isValid;
}

// Validate on module load
if (!validateQualityCalculatorConfig()) {
  throw new Error("QualityCalculator configuration is invalid!");
}
