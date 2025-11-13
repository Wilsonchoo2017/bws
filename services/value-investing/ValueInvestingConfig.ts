/**
 * Configuration for Value Investing calculations
 * Centralized config following Open/Closed Principle - easy to extend and tune
 */

export const VALUE_INVESTING_CONFIG = {
  /**
   * Intrinsic value calculation parameters
   */
  INTRINSIC_VALUE: {
    /**
     * Weights for averaging Bricklink prices
     * Conservative approach: favor average over max price
     */
    BASE_WEIGHTS: {
      AVG_PRICE: 0.7,
      MAX_PRICE: 0.3,
      MAX_ONLY_DISCOUNT: 0.6, // Applied when only max price available
    },

    /**
     * Retirement status multipliers
     * Retired sets tend to appreciate in value
     */
    RETIREMENT_MULTIPLIERS: {
      RETIRED: 1.15, // 15% premium
      RETIRING_SOON: 1.08, // 8% premium
      ACTIVE: 1.0, // No premium
    },

    /**
     * Quality score adjustment range (0-100 input -> 0.9-1.1 multiplier)
     * Higher quality = higher intrinsic value
     */
    QUALITY_MULTIPLIER: {
      MIN: 0.9,
      MAX: 1.1,
      DEFAULT_SCORE: 50,
    },

    /**
     * Demand score adjustment range (0-100 input -> 0.85-1.15 multiplier)
     * Higher demand = more confident in resale value
     */
    DEMAND_MULTIPLIER: {
      MIN: 0.85,
      MAX: 1.15,
      DEFAULT_SCORE: 50,
    },
  },

  /**
   * Margin of safety parameters (Buffett/Pabrai principle)
   */
  MARGIN_OF_SAFETY: {
    /**
     * Default margin: buy at 25% discount to intrinsic value
     * Provides cushion for errors in valuation
     */
    DEFAULT: 0.25,

    /**
     * Minimum margin to consider a "good buy"
     */
    MINIMUM: 0.20,
  },

  /**
   * Value rating thresholds and display properties
   */
  VALUE_RATINGS: [
    {
      threshold: 40,
      rating: "Exceptional Value",
      color: "success",
      description: "Rare opportunity - 40%+ discount to value",
    },
    {
      threshold: 25,
      rating: "Strong Buy",
      color: "success",
      description: "High margin of safety",
    },
    {
      threshold: 15,
      rating: "Good Buy",
      color: "info",
      description: "Adequate margin of safety",
    },
    {
      threshold: 5,
      rating: "Fair Value",
      color: "warning",
      description: "Minimal margin of safety",
    },
    {
      threshold: 0,
      rating: "At Intrinsic Value",
      color: "warning",
      description: "No margin of safety",
    },
    {
      threshold: -Infinity,
      rating: "Overvalued",
      color: "error",
      description: "Trading above intrinsic value",
    },
  ] as const,

  /**
   * Time horizon estimates based on market conditions
   */
  TIME_HORIZONS: {
    URGENT: "1-3 months",
    RETIRED: "3-6 months",
    RETIRING_SOON: "6-12 months",
    ACTIVE: "12-24 months",
  },

  /**
   * Input validation ranges
   */
  VALIDATION: {
    SCORE_MIN: 0,
    SCORE_MAX: 100,
    PRICE_MIN: 0,
    PERCENTAGE_MIN: -100,
    PERCENTAGE_MAX: 1000,
  },

  /**
   * Decimal precision for rounding
   */
  PRECISION: {
    PRICE: 2,
    PERCENTAGE: 1,
  },
} as const;

/**
 * Type-safe access to value ratings
 */
export type ValueRating = typeof VALUE_INVESTING_CONFIG.VALUE_RATINGS[number];

/**
 * Helper to get value rating by margin of safety
 */
export function getValueRatingConfig(marginOfSafety: number): ValueRating {
  for (const rating of VALUE_INVESTING_CONFIG.VALUE_RATINGS) {
    if (marginOfSafety >= rating.threshold) {
      return rating;
    }
  }
  // Fallback (should never reach here due to -Infinity threshold)
  return VALUE_INVESTING_CONFIG.VALUE_RATINGS[
    VALUE_INVESTING_CONFIG.VALUE_RATINGS.length - 1
  ];
}
