/**
 * DemandCalculator - Calculates demand score from BrickLink market data
 *
 * Implements a 5-component scoring system:
 * 1. Sales Velocity (30%) - Transactions per day
 * 2. Price Momentum (25%) - Price trend direction
 * 3. Market Depth (20%) - Number of competing sellers
 * 4. Supply/Demand Ratio (15%) - Sales vs available supply
 * 5. Velocity Consistency (10%) - Steady vs sporadic sales
 *
 * Follows SOLID principles:
 * - Single Responsibility: Only calculates demand score
 * - Open/Closed: Easy to add new components
 * - Dependency Inversion: Uses interfaces for inputs
 */

import { DEMAND_CALCULATOR_CONFIG as CONFIG } from "./DemandCalculatorConfig.ts";
import { DataValidator } from "./DataValidator.ts";

/**
 * Input data for demand calculation
 */
export interface DemandCalculatorInput {
  // Sales velocity metrics
  timesSold?: number; // Total sales in observation period
  observationDays?: number; // Length of observation period (e.g., 180 for 6 months)
  salesVelocity?: number; // Pre-calculated transactions/day

  // Price data for momentum
  currentPrice?: number; // Current average price (cents)
  historicalPrices?: number[]; // Array of historical prices (cents)
  firstPrice?: number; // Price at start of period (cents)
  lastPrice?: number; // Price at end of period (cents)

  // Market depth
  availableLots?: number; // Number of competing sellers
  availableQty?: number; // Total units available

  // For consistency calculation
  salesTimestamps?: Date[]; // Individual sale dates (if available)
}

/**
 * Output from demand calculation
 */
export interface DemandScore {
  // Overall score
  score: number; // 0-100
  confidence: number; // 0-1

  // Component breakdown
  components: {
    salesVelocity: ComponentScore;
    priceMomentum: ComponentScore;
    marketDepth: ComponentScore;
    supplyDemandRatio: ComponentScore;
    velocityConsistency: ComponentScore;
  };

  // Metadata
  dataQuality: {
    hasSalesData: boolean;
    hasPriceData: boolean;
    hasMarketDepth: boolean;
    observationPeriod: number; // days
  };
}

export interface ComponentScore {
  score: number; // 0-100 raw score
  weight: number; // 0-1 weight
  weightedScore: number; // score * weight
  confidence: number; // 0-1
  notes?: string;
}

/**
 * DemandCalculator - Pure calculation service
 */
export class DemandCalculator {
  /**
   * Calculate demand score from BrickLink market data
   */
  static calculate(input: DemandCalculatorInput): DemandScore {
    // Validate and sanitize input
    const validation = DataValidator.validateDemandInput(input);
    if (!validation.isValid || !validation.data) {
      // Return default score with low confidence if validation fails
      console.warn(
        "[DemandCalculator] Validation failed:",
        validation.warnings,
      );
      return this.createDefaultScore(input, validation.warnings);
    }

    // Log warnings if any
    if (validation.warnings.length > 0) {
      console.warn(
        "[DemandCalculator] Validation warnings:",
        validation.warnings,
      );
    }

    // Use sanitized data for calculations
    const sanitizedInput = validation.data;

    // Calculate each component
    const salesVelocity = this.calculateSalesVelocityScore(sanitizedInput);
    const priceMomentum = this.calculatePriceMomentumScore(sanitizedInput);
    const marketDepth = this.calculateMarketDepthScore(sanitizedInput);
    const supplyDemandRatio = this.calculateSupplyDemandRatioScore(
      sanitizedInput,
    );
    const velocityConsistency = this.calculateVelocityConsistencyScore(
      sanitizedInput,
    );

    // Calculate weighted overall score
    const overallScore = salesVelocity.weightedScore +
      priceMomentum.weightedScore +
      marketDepth.weightedScore +
      supplyDemandRatio.weightedScore +
      velocityConsistency.weightedScore;

    // Calculate overall confidence (average of component confidences weighted by their weights)
    const overallConfidence = salesVelocity.confidence * salesVelocity.weight +
      priceMomentum.confidence * priceMomentum.weight +
      marketDepth.confidence * marketDepth.weight +
      supplyDemandRatio.confidence * supplyDemandRatio.weight +
      velocityConsistency.confidence * velocityConsistency.weight;

    // Data quality assessment
    const observationDays = sanitizedInput.observationDays ?? 180;
    const hasSalesData = (sanitizedInput.timesSold ?? 0) > 0 ||
      (sanitizedInput.salesVelocity ?? 0) > 0;
    const hasPriceData = (sanitizedInput.historicalPrices?.length ?? 0) > 0 ||
      (sanitizedInput.firstPrice !== undefined &&
        sanitizedInput.lastPrice !== undefined);
    const hasMarketDepth = sanitizedInput.availableLots !== undefined;

    return {
      score: Math.round(overallScore),
      confidence: Math.max(0, Math.min(1, overallConfidence)),
      components: {
        salesVelocity,
        priceMomentum,
        marketDepth,
        supplyDemandRatio,
        velocityConsistency,
      },
      dataQuality: {
        hasSalesData,
        hasPriceData,
        hasMarketDepth,
        observationPeriod: observationDays,
      },
    };
  }

  /**
   * Component 1: Sales Velocity Score (30% weight)
   * Higher velocity = higher demand
   */
  private static calculateSalesVelocityScore(
    input: DemandCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.SALES_VELOCITY;

    // Calculate or use pre-calculated velocity
    let velocity: number;
    if (input.salesVelocity !== undefined && input.salesVelocity !== null) {
      velocity = input.salesVelocity;
    } else if (
      input.timesSold !== undefined && input.observationDays !== undefined
    ) {
      velocity = input.timesSold / input.observationDays;
    } else {
      // No data - return default
      return {
        score: CONFIG.DEFAULTS.SCORE,
        weight,
        weightedScore: CONFIG.DEFAULTS.SCORE * weight,
        confidence: CONFIG.DEFAULTS.CONFIDENCE,
        notes: "No sales velocity data available",
      };
    }

    // Map velocity to 0-100 score
    let score: number;
    let confidence = 1.0;

    if (velocity >= CONFIG.SALES_VELOCITY.EXCELLENT) {
      score = 100;
    } else if (velocity >= CONFIG.SALES_VELOCITY.GOOD) {
      score = 75 + ((velocity - CONFIG.SALES_VELOCITY.GOOD) /
            (CONFIG.SALES_VELOCITY.EXCELLENT - CONFIG.SALES_VELOCITY.GOOD)) *
          25;
    } else if (velocity >= CONFIG.SALES_VELOCITY.FAIR) {
      score = 50 + ((velocity - CONFIG.SALES_VELOCITY.FAIR) /
            (CONFIG.SALES_VELOCITY.GOOD - CONFIG.SALES_VELOCITY.FAIR)) * 25;
    } else if (velocity >= CONFIG.SALES_VELOCITY.POOR) {
      score = 25 + ((velocity - CONFIG.SALES_VELOCITY.POOR) /
            (CONFIG.SALES_VELOCITY.FAIR - CONFIG.SALES_VELOCITY.POOR)) * 25;
    } else if (velocity >= CONFIG.SALES_VELOCITY.DEAD) {
      score = 10 + ((velocity - CONFIG.SALES_VELOCITY.DEAD) /
            (CONFIG.SALES_VELOCITY.POOR - CONFIG.SALES_VELOCITY.DEAD)) * 15;
    } else {
      score = Math.max(0, (velocity / CONFIG.SALES_VELOCITY.DEAD) * 10);
    }

    // Reduce confidence if insufficient sales data
    const salesCount = input.timesSold ??
      (velocity * (input.observationDays ?? 180));
    if (salesCount < CONFIG.MIN_DATA_REQUIREMENTS.MIN_SALES_FOR_VELOCITY) {
      confidence *= 1 - CONFIG.CONFIDENCE_PENALTIES.INSUFFICIENT_SALES;
    }

    return {
      score,
      weight,
      weightedScore: score * weight,
      confidence,
      notes: `${velocity.toFixed(3)} sales/day`,
    };
  }

  /**
   * Component 2: Price Momentum Score (25% weight)
   * Rising prices = increasing demand
   */
  private static calculatePriceMomentumScore(
    input: DemandCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.PRICE_MOMENTUM;

    // Calculate price change percentage
    let priceChange: number | undefined;

    if (
      input.firstPrice !== undefined && input.lastPrice !== undefined &&
      input.firstPrice > 0
    ) {
      priceChange = (input.lastPrice - input.firstPrice) / input.firstPrice;
    } else if (input.historicalPrices && input.historicalPrices.length >= 2) {
      const first = input.historicalPrices[0];
      const last = input.historicalPrices[input.historicalPrices.length - 1];
      if (first > 0) {
        priceChange = (last - first) / first;
      }
    }

    if (priceChange === undefined) {
      return {
        score: CONFIG.DEFAULTS.SCORE,
        weight,
        weightedScore: CONFIG.DEFAULTS.SCORE * weight,
        confidence: CONFIG.DEFAULTS.CONFIDENCE,
        notes: "No price history available",
      };
    }

    // Map price change to 0-100 score
    let score: number;

    if (priceChange >= CONFIG.PRICE_MOMENTUM.STRONG_UP) {
      score = 100;
    } else if (priceChange >= CONFIG.PRICE_MOMENTUM.MODERATE_UP) {
      score = 75 + ((priceChange - CONFIG.PRICE_MOMENTUM.MODERATE_UP) /
            (CONFIG.PRICE_MOMENTUM.STRONG_UP -
              CONFIG.PRICE_MOMENTUM.MODERATE_UP)) * 25;
    } else if (priceChange >= -CONFIG.PRICE_MOMENTUM.STABLE) {
      // Stable range: -2% to +2%
      score = 50 + (priceChange / CONFIG.PRICE_MOMENTUM.STABLE) * 25;
    } else if (priceChange >= CONFIG.PRICE_MOMENTUM.MODERATE_DOWN) {
      score = 25 + ((priceChange - CONFIG.PRICE_MOMENTUM.MODERATE_DOWN) /
            (CONFIG.PRICE_MOMENTUM.STABLE -
              CONFIG.PRICE_MOMENTUM.MODERATE_DOWN)) * 25;
    } else if (priceChange >= CONFIG.PRICE_MOMENTUM.STRONG_DOWN) {
      score = ((priceChange - CONFIG.PRICE_MOMENTUM.STRONG_DOWN) /
        (CONFIG.PRICE_MOMENTUM.MODERATE_DOWN -
          CONFIG.PRICE_MOMENTUM.STRONG_DOWN)) * 25;
    } else {
      score = 0; // Very strong decline
    }

    // Confidence based on price data quality
    const salesCount = input.timesSold ?? 0;
    let confidence = 1.0;
    if (salesCount < CONFIG.MIN_DATA_REQUIREMENTS.MIN_SALES_FOR_MOMENTUM) {
      confidence *= 1 - CONFIG.CONFIDENCE_PENALTIES.INSUFFICIENT_SALES;
    }

    return {
      score,
      weight,
      weightedScore: score * weight,
      confidence,
      notes: `${(priceChange * 100).toFixed(1)}% price change`,
    };
  }

  /**
   * Component 3: Market Depth Score (20% weight)
   * Fewer sellers = higher scarcity/demand
   */
  private static calculateMarketDepthScore(
    input: DemandCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.MARKET_DEPTH;

    if (input.availableLots === undefined || input.availableLots === null) {
      return {
        score: CONFIG.DEFAULTS.SCORE,
        weight,
        weightedScore: CONFIG.DEFAULTS.SCORE * weight,
        confidence: CONFIG.DEFAULTS.CONFIDENCE,
        notes: "No market depth data",
      };
    }

    const lots = input.availableLots;
    let score: number;

    // Inverse relationship: fewer sellers = higher score
    if (lots <= CONFIG.MARKET_DEPTH.SCARCE) {
      score = 100;
    } else if (lots <= CONFIG.MARKET_DEPTH.LIMITED) {
      score = 75 + ((CONFIG.MARKET_DEPTH.LIMITED - lots) /
            (CONFIG.MARKET_DEPTH.LIMITED - CONFIG.MARKET_DEPTH.SCARCE)) * 25;
    } else if (lots <= CONFIG.MARKET_DEPTH.COMPETITIVE) {
      score = 50 + ((CONFIG.MARKET_DEPTH.COMPETITIVE - lots) /
            (CONFIG.MARKET_DEPTH.COMPETITIVE - CONFIG.MARKET_DEPTH.LIMITED)) *
          25;
    } else if (lots <= CONFIG.MARKET_DEPTH.SATURATED) {
      score = 25 + ((CONFIG.MARKET_DEPTH.SATURATED - lots) /
            (CONFIG.MARKET_DEPTH.SATURATED - CONFIG.MARKET_DEPTH.COMPETITIVE)) *
          25;
    } else if (lots <= CONFIG.MARKET_DEPTH.OVERSATURATED) {
      score = ((CONFIG.MARKET_DEPTH.OVERSATURATED - lots) /
        (CONFIG.MARKET_DEPTH.OVERSATURATED - CONFIG.MARKET_DEPTH.SATURATED)) *
        25;
    } else {
      score = 0; // Extremely oversaturated
    }

    return {
      score,
      weight,
      weightedScore: score * weight,
      confidence: 1.0, // Market depth is objective data
      notes: `${lots} competing sellers`,
    };
  }

  /**
   * Component 4: Supply/Demand Ratio Score (15% weight)
   * Higher sales relative to supply = healthy demand
   */
  private static calculateSupplyDemandRatioScore(
    input: DemandCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.SUPPLY_DEMAND_RATIO;

    if (
      input.availableQty === undefined || input.availableQty === null ||
      input.availableQty === 0 ||
      input.timesSold === undefined || input.timesSold === null
    ) {
      return {
        score: CONFIG.DEFAULTS.SCORE,
        weight,
        weightedScore: CONFIG.DEFAULTS.SCORE * weight,
        confidence: CONFIG.DEFAULTS.CONFIDENCE,
        notes: "Insufficient supply/demand data",
      };
    }

    // Calculate ratio: sales / supply
    const ratio = input.timesSold / input.availableQty;
    let score: number;

    if (ratio >= CONFIG.SUPPLY_DEMAND_RATIO.EXCELLENT) {
      score = 100;
    } else if (ratio >= CONFIG.SUPPLY_DEMAND_RATIO.GOOD) {
      score = 75 + ((ratio - CONFIG.SUPPLY_DEMAND_RATIO.GOOD) /
            (CONFIG.SUPPLY_DEMAND_RATIO.EXCELLENT -
              CONFIG.SUPPLY_DEMAND_RATIO.GOOD)) * 25;
    } else if (ratio >= CONFIG.SUPPLY_DEMAND_RATIO.FAIR) {
      score = 50 + ((ratio - CONFIG.SUPPLY_DEMAND_RATIO.FAIR) /
            (CONFIG.SUPPLY_DEMAND_RATIO.GOOD -
              CONFIG.SUPPLY_DEMAND_RATIO.FAIR)) * 25;
    } else if (ratio >= CONFIG.SUPPLY_DEMAND_RATIO.POOR) {
      score = 25 + ((ratio - CONFIG.SUPPLY_DEMAND_RATIO.POOR) /
            (CONFIG.SUPPLY_DEMAND_RATIO.FAIR -
              CONFIG.SUPPLY_DEMAND_RATIO.POOR)) * 25;
    } else if (ratio >= CONFIG.SUPPLY_DEMAND_RATIO.STAGNANT) {
      score = 10 + ((ratio - CONFIG.SUPPLY_DEMAND_RATIO.STAGNANT) /
            (CONFIG.SUPPLY_DEMAND_RATIO.POOR -
              CONFIG.SUPPLY_DEMAND_RATIO.STAGNANT)) * 15;
    } else {
      score = Math.max(0, (ratio / CONFIG.SUPPLY_DEMAND_RATIO.STAGNANT) * 10);
    }

    return {
      score,
      weight,
      weightedScore: score * weight,
      confidence: 1.0,
      notes: `${(ratio * 100).toFixed(1)}% turnover`,
    };
  }

  /**
   * Component 5: Velocity Consistency Score (10% weight)
   * Steady sales = predictable demand
   */
  private static calculateVelocityConsistencyScore(
    input: DemandCalculatorInput,
  ): ComponentScore {
    const weight = CONFIG.WEIGHTS.VELOCITY_CONSISTENCY;

    // Need timestamp data for consistency calculation
    if (
      !input.salesTimestamps ||
      input.salesTimestamps.length <
        CONFIG.MIN_DATA_REQUIREMENTS.MIN_SALES_FOR_CONSISTENCY
    ) {
      return {
        score: CONFIG.DEFAULTS.SCORE,
        weight,
        weightedScore: CONFIG.DEFAULTS.SCORE * weight,
        confidence: CONFIG.DEFAULTS.CONFIDENCE * 0.5, // Lower confidence for default
        notes: "Insufficient data for consistency analysis",
      };
    }

    // Calculate days between sales
    const daysBetween: number[] = [];
    for (let i = 1; i < input.salesTimestamps.length; i++) {
      const diff = input.salesTimestamps[i].getTime() -
        input.salesTimestamps[i - 1].getTime();
      daysBetween.push(diff / (1000 * 60 * 60 * 24)); // Convert ms to days
    }

    // Calculate coefficient of variation (std dev / mean)
    const mean = daysBetween.reduce((a, b) => a + b, 0) / daysBetween.length;
    const variance =
      daysBetween.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) /
      daysBetween.length;
    const stdDev = Math.sqrt(variance);
    const cv = mean > 0 ? stdDev / mean : 1.0;

    // Map CV to score (lower CV = higher score = more consistent)
    let score: number;

    if (cv <= CONFIG.VELOCITY_CONSISTENCY.VERY_STEADY) {
      score = 100;
    } else if (cv <= CONFIG.VELOCITY_CONSISTENCY.STEADY) {
      score = 75 + ((CONFIG.VELOCITY_CONSISTENCY.STEADY - cv) /
            (CONFIG.VELOCITY_CONSISTENCY.STEADY -
              CONFIG.VELOCITY_CONSISTENCY.VERY_STEADY)) * 25;
    } else if (cv <= CONFIG.VELOCITY_CONSISTENCY.MODERATE) {
      score = 50 + ((CONFIG.VELOCITY_CONSISTENCY.MODERATE - cv) /
            (CONFIG.VELOCITY_CONSISTENCY.MODERATE -
              CONFIG.VELOCITY_CONSISTENCY.STEADY)) * 25;
    } else if (cv <= CONFIG.VELOCITY_CONSISTENCY.SPORADIC) {
      score = 25 + ((CONFIG.VELOCITY_CONSISTENCY.SPORADIC - cv) /
            (CONFIG.VELOCITY_CONSISTENCY.SPORADIC -
              CONFIG.VELOCITY_CONSISTENCY.MODERATE)) * 25;
    } else if (cv <= CONFIG.VELOCITY_CONSISTENCY.ERRATIC) {
      score = 10 + ((CONFIG.VELOCITY_CONSISTENCY.ERRATIC - cv) /
            (CONFIG.VELOCITY_CONSISTENCY.ERRATIC -
              CONFIG.VELOCITY_CONSISTENCY.SPORADIC)) * 15;
    } else {
      score = Math.max(0, 10 * (CONFIG.VELOCITY_CONSISTENCY.ERRATIC / cv));
    }

    return {
      score,
      weight,
      weightedScore: score * weight,
      confidence: 0.9, // Slightly lower confidence for statistical measure
      notes: `CV = ${cv.toFixed(2)} (${daysBetween.length} intervals)`,
    };
  }

  /**
   * Create default score when validation fails
   */
  private static createDefaultScore(
    _input: DemandCalculatorInput,
    _warnings: string[],
  ): DemandScore {
    const defaultScore = CONFIG.DEFAULTS.SCORE;
    const defaultConfidence = CONFIG.DEFAULTS.CONFIDENCE;
    const weight = CONFIG.WEIGHTS;

    return {
      score: defaultScore,
      confidence: defaultConfidence,
      components: {
        salesVelocity: {
          score: defaultScore,
          weight: weight.SALES_VELOCITY,
          weightedScore: defaultScore * weight.SALES_VELOCITY,
          confidence: defaultConfidence,
          notes: "(validation failed)",
        },
        priceMomentum: {
          score: defaultScore,
          weight: weight.PRICE_MOMENTUM,
          weightedScore: defaultScore * weight.PRICE_MOMENTUM,
          confidence: defaultConfidence,
          notes: "(validation failed)",
        },
        marketDepth: {
          score: defaultScore,
          weight: weight.MARKET_DEPTH,
          weightedScore: defaultScore * weight.MARKET_DEPTH,
          confidence: defaultConfidence,
          notes: "(validation failed)",
        },
        supplyDemandRatio: {
          score: defaultScore,
          weight: weight.SUPPLY_DEMAND_RATIO,
          weightedScore: defaultScore * weight.SUPPLY_DEMAND_RATIO,
          confidence: defaultConfidence,
          notes: "(validation failed)",
        },
        velocityConsistency: {
          score: defaultScore,
          weight: weight.VELOCITY_CONSISTENCY,
          weightedScore: defaultScore * weight.VELOCITY_CONSISTENCY,
          confidence: defaultConfidence,
          notes: "(validation failed)",
        },
      },
      dataQuality: {
        hasSalesData: false,
        hasPriceData: false,
        hasMarketDepth: false,
        observationPeriod: 0,
      },
    };
  }
}
