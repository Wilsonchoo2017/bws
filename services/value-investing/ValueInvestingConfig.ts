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

    /**
     * Liquidity multiplier based on sales velocity and time between sales
     * High liquidity = easier to sell = premium
     * Low liquidity = harder to sell = discount
     * ENHANCED: Stricter penalties for dead/very slow moving inventory
     */
    LIQUIDITY_MULTIPLIER: {
      MIN: 0.60, // 40% discount for dead/very illiquid assets (increased from 0.85)
      MAX: 1.10, // 10% premium for highly liquid assets
      DEFAULT: 1.0, // No adjustment when data unavailable
      // Sales velocity thresholds (transactions per day)
      VELOCITY_HIGH: 0.5, // 1 sale every 2 days = high liquidity
      VELOCITY_MEDIUM: 0.1, // 1 sale every 10 days = medium
      VELOCITY_LOW: 0.033, // 1 sale every 30 days = low
      VELOCITY_DEAD: 0.01, // 1 sale every 100 days = dead inventory
      // Days between sales thresholds (alternative metric)
      DAYS_FAST: 7, // Sales within 7 days = high liquidity
      DAYS_MEDIUM: 30, // Sales within 30 days = medium
      DAYS_SLOW: 90, // Sales within 90 days = low
      DAYS_VERY_SLOW: 180, // Sales > 180 days apart = very slow
    },

    /**
     * Volatility discount - penalize high price volatility (risk adjustment)
     * Based on coefficient of variation (std dev / mean)
     */
    VOLATILITY_DISCOUNT: {
      MAX_DISCOUNT: 0.12, // Maximum 12% discount for very volatile assets
      RISK_AVERSION_COEFFICIENT: 0.20, // How much to penalize volatility
      STABLE_THRESHOLD: 0.1, // CoV < 0.1 = stable pricing
      VOLATILE_THRESHOLD: 0.4, // CoV > 0.4 = high volatility
    },

    /**
     * Time-decayed retirement premium - REALISTIC J-CURVE
     * Reality: Initial dip (flooded market), then gradual appreciation
     * CRITICAL: Only applies if minimum demand threshold is met
     */
    RETIREMENT_TIME_DECAY: {
      YEAR_0_1: 0.95, // Just retired (0-1 years): -5% (market flooded)
      YEAR_1_2: 1.00, // Stabilization (1-2 years): 0% (baseline)
      YEAR_2_5: 1.15, // Early appreciation (2-5 years): 15% premium
      YEAR_5_10: 1.40, // Scarcity premium (5-10 years): 40% premium
      YEAR_10_PLUS: 2.00, // Vintage status (10+ years): 100% premium
      // Demand gating
      MIN_DEMAND_FOR_PREMIUM: 40, // Demand score must be >= 40 for retirement premium
      LOW_DEMAND_MAX_PREMIUM: 1.02, // Max 2% premium if demand < 40
    },

    /**
     * Theme-based valuation multipliers
     * Not all LEGO themes appreciate equally
     */
    THEME_MULTIPLIERS: {
      "Star Wars": 1.30, // Strong performer
      "Harry Potter": 1.20,
      "Architecture": 1.40, // Best performer
      "Creator Expert": 1.35,
      "Technic": 1.15,
      "Ideas": 1.25,
      "City": 0.80, // Poor investment
      "Friends": 0.75, // Poor investment
      "Duplo": 0.70, // Very poor investment
      DEFAULT: 1.00, // Unknown themes
    },

    /**
     * Price-to-Retail (P/R) ratio thresholds
     * Like P/E ratio in stocks - filters bubble prices
     */
    PRICE_TO_RETAIL: {
      GOOD_DEAL: 1.0, // Below or at retail
      FAIR: 1.5, // Normal aftermarket
      EXPENSIVE: 2.0, // Speculation territory
      BUBBLE: 2.5, // Bubble - avoid
      MAX_ACCEPTABLE: 2.0, // Hard filter - reject above this
    },

    /**
     * Parts-per-dollar quality metric
     * Higher PPD = better brick value
     */
    PARTS_PER_DOLLAR: {
      EXCELLENT: 10, // > 10 PPD = holds value well
      GOOD: 8, // 8-10 PPD = acceptable
      FAIR: 6, // 6-8 PPD = mediocre
      POOR: 6, // < 6 PPD = often declines
    },

    /**
     * Market saturation detection and penalty
     * High supply + low demand = oversaturated market
     * ENHANCED: More aggressive penalties for extreme oversaturation
     */
    SATURATION_PENALTY: {
      // Quantity thresholds (total units available for sale)
      QTY_LOW: 50, // < 50 units = healthy supply
      QTY_MEDIUM: 200, // 50-200 = moderate supply
      QTY_HIGH: 500, // 500-1000 = oversupply risk
      QTY_EXTREME: 1000, // > 1000 = extreme oversupply

      // Lots thresholds (number of competing sellers)
      LOTS_LOW: 10, // < 10 sellers = healthy
      LOTS_MEDIUM: 30, // 10-30 sellers = competitive
      LOTS_HIGH: 50, // 50-100 = saturated
      LOTS_EXTREME: 100, // > 100 sellers = extreme saturation

      // Saturation discount multiplier (enhanced range)
      MIN: 0.50, // 50% discount for extremely saturated markets (increased from 0.80)
      MAX: 1.0, // No discount for healthy supply

      // Velocity-to-supply ratio (low ratio = oversupply)
      HEALTHY_RATIO: 0.01, // 1% of inventory sells per day = healthy
      POOR_RATIO: 0.001, // 0.1% of inventory sells per day = saturated
    },

    /**
     * Zero sales penalty - CRITICAL for dead inventory
     * Items with confirmed zero sales get heavily penalized
     * Prevents overvaluing inventory nobody wants
     */
    ZERO_SALES_PENALTY: {
      MULTIPLIER: 0.50, // 50% discount for zero sales in observation period
      MIN_SALES_THRESHOLD: 1, // Must have at least 1 sale to avoid penalty
      GRACE_PERIOD_DAYS: 90, // Only apply penalty if 90+ days with zero sales
      // Compounding with demand score
      LOW_DEMAND_THRESHOLD: 30, // Demand score < 30 compounds with zero sales
      COMPOUND_MULTIPLIER: 0.60, // Additional 40% discount if low demand + zero sales
    },

    /**
     * Sanity bounds to prevent extreme valuations
     * Prevents multiplicative compounding from creating unrealistic values
     * Buffett principle: "If it seems too good to be true, it probably is"
     */
    SANITY_BOUNDS: {
      MIN_MULTIPLIER: 0.30, // Minimum 0.30× base value (even junk sets retain some value)
      MAX_MULTIPLIER: 3.50, // Maximum 3.50× base value (very few sets exceed this, even vintage)
    },
  },

  /**
   * Margin of safety parameters (Buffett/Pabrai principle)
   * ENHANCED: Confidence-aware margins
   * Buffett principle: "The less certain you are, the bigger your margin should be"
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

    /**
     * Confidence-aware margins based on data quality
     * Higher quality data = can accept smaller margin
     * Lower quality data = need bigger margin for safety
     */
    HIGH_CONFIDENCE: 0.20, // Data quality 80-100: 20% margin
    MEDIUM_CONFIDENCE: 0.30, // Data quality 50-79: 30% margin
    LOW_CONFIDENCE: 0.40, // Data quality 0-49: 40% margin
  },

  /**
   * Transaction costs for realistic profit projections
   * UPDATED: More realistic estimates based on actual selling experience
   */
  TRANSACTION_COSTS: {
    SELLING_FEE_RATE: 0.15, // 15% platform fees (eBay 12.9% + PayPal 2.9% + other)
    SHIPPING_BASE: 10.00, // Base shipping cost
    SHIPPING_PER_POUND: 2.00, // Additional per pound (estimate)
    PACKAGING_COST: 5.00, // Proper packaging materials ($5-20, conservative)
    RETURN_DAMAGE_RATE: 0.03, // 3% of transactions have issues
    // Holding costs (annually)
    STORAGE_COST_ANNUAL: 0.02, // 2% of value (space opportunity cost)
    CAPITAL_COST_ANNUAL: 0.05, // 5% cost of capital (could invest elsewhere)
    DEGRADATION_RISK_ANNUAL: 0.01, // 1% risk of damage/wear per year
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
