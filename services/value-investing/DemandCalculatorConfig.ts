/**
 * DemandCalculator Configuration
 *
 * Defines thresholds and weights for calculating demand score (0-100)
 * from BrickLink sales data, market depth, and supply/demand dynamics.
 */

export const DEMAND_CALCULATOR_CONFIG = {
  /**
   * Component weights (must sum to 1.0)
   */
  WEIGHTS: {
    SALES_VELOCITY: 0.30, // 30% - How fast items are selling
    PRICE_MOMENTUM: 0.25, // 25% - Price trend direction
    MARKET_DEPTH: 0.20, // 20% - Number of competing sellers
    SUPPLY_DEMAND_RATIO: 0.15, // 15% - Sales vs available supply
    VELOCITY_CONSISTENCY: 0.10, // 10% - Steady vs sporadic sales
  },

  /**
   * Sales Velocity Scoring (transactions per day)
   * Maps velocity to 0-100 score
   */
  SALES_VELOCITY: {
    EXCELLENT: 0.5, // 1 sale every 2 days = 100 points
    GOOD: 0.2, // 1 sale every 5 days = 75 points
    FAIR: 0.1, // 1 sale every 10 days = 50 points
    POOR: 0.033, // 1 sale every 30 days = 25 points
    DEAD: 0.01, // 1 sale every 100 days = 10 points
    // Below DEAD = 0-10 points (linear interpolation)
  },

  /**
   * Price Momentum Scoring
   * Based on price trend over observation period
   */
  PRICE_MOMENTUM: {
    STRONG_UP: 0.10, // +10% or more = 100 points
    MODERATE_UP: 0.05, // +5% to +10% = 75 points
    STABLE: 0.02, // -2% to +2% = 50 points (neutral)
    MODERATE_DOWN: -0.05, // -5% to -2% = 25 points
    STRONG_DOWN: -0.10, // -10% or worse = 0 points
  },

  /**
   * Market Depth Scoring (number of competing sellers)
   * Fewer sellers = higher demand/scarcity
   * More sellers = more competition/saturation
   */
  MARKET_DEPTH: {
    SCARCE: 10, // < 10 sellers = 100 points (high demand)
    LIMITED: 30, // 10-30 sellers = 75 points
    COMPETITIVE: 50, // 30-50 sellers = 50 points
    SATURATED: 100, // 50-100 sellers = 25 points
    OVERSATURATED: 200, // > 100 sellers = 0-25 points
    // Inverse relationship: fewer sellers = higher score
  },

  /**
   * Supply/Demand Ratio Scoring
   * Ratio = (Sales in period) / (Available supply)
   * High ratio = healthy turnover
   */
  SUPPLY_DEMAND_RATIO: {
    EXCELLENT: 0.20, // 20% of supply sells in 6mo = 100 points
    GOOD: 0.10, // 10% turnover = 75 points
    FAIR: 0.05, // 5% turnover = 50 points
    POOR: 0.02, // 2% turnover = 25 points
    STAGNANT: 0.005, // 0.5% turnover = 10 points
    // Below 0.5% = 0-10 points
  },

  /**
   * Velocity Consistency Scoring
   * Measures steadiness of sales (low variance = consistent demand)
   * Uses coefficient of variation if time-series data available
   */
  VELOCITY_CONSISTENCY: {
    VERY_STEADY: 0.10, // CV < 0.1 = 100 points
    STEADY: 0.25, // CV 0.1-0.25 = 75 points
    MODERATE: 0.50, // CV 0.25-0.5 = 50 points
    SPORADIC: 0.75, // CV 0.5-0.75 = 25 points
    ERRATIC: 1.00, // CV > 0.75 = 10 points
    // High variance = unpredictable demand
  },

  /**
   * Minimum data requirements for confidence scoring
   */
  MIN_DATA_REQUIREMENTS: {
    MIN_SALES_FOR_VELOCITY: 3, // Need 3+ sales for reliable velocity
    MIN_SALES_FOR_MOMENTUM: 5, // Need 5+ sales for trend analysis
    MIN_SALES_FOR_CONSISTENCY: 10, // Need 10+ sales for variance calc
    MIN_OBSERVATION_DAYS: 90, // Need 90+ days of data
  },

  /**
   * Confidence penalties for missing/insufficient data
   */
  CONFIDENCE_PENALTIES: {
    NO_SALES_DATA: 0.50, // 50% confidence penalty
    INSUFFICIENT_SALES: 0.25, // 25% confidence penalty
    SHORT_OBSERVATION: 0.15, // 15% confidence penalty
    NO_PRICE_HISTORY: 0.10, // 10% confidence penalty
  },

  /**
   * Default values when data is missing
   * Philosophy: "Bad until proven" - assume worst case when data is missing
   */
  DEFAULTS: {
    SCORE: 0, // Pessimistic score - missing data is bad
    CONFIDENCE: 0.0, // No confidence (0%)
  },
};

/**
 * Helper function to validate configuration
 */
export function validateDemandCalculatorConfig(): boolean {
  const weights = DEMAND_CALCULATOR_CONFIG.WEIGHTS;
  const sum = Object.values(weights).reduce((a, b) => a + b, 0);
  const isValid = Math.abs(sum - 1.0) < 0.001; // Allow floating point tolerance

  if (!isValid) {
    console.error(
      `[DemandCalculatorConfig] Invalid weights: sum = ${sum}, expected 1.0`,
    );
  }

  return isValid;
}

// Validate on module load
if (!validateDemandCalculatorConfig()) {
  throw new Error("DemandCalculator configuration is invalid!");
}
