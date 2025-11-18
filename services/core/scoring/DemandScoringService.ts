/**
 * DemandScoringService - Unified demand scoring logic
 *
 * CONSOLIDATES:
 * - services/analysis/analyzers/DemandAnalyzer.ts (1030 lines)
 * - services/value-investing/DemandCalculator.ts (546 lines)
 *
 * SOLID Principles Applied:
 * - Single Responsibility: Only calculates demand scores
 * - Open/Closed: Easy to add new components via configuration
 * - Dependency Inversion: Accepts abstract input interface
 *
 * Scoring Components (weighted):
 * 1. Sales Velocity (30%) - Transactions per day
 * 2. Price Momentum (25%) - Price trend direction
 * 3. Market Depth (20%) - Number of competing sellers
 * 4. Supply/Demand Ratio (15%) - Sales vs available supply
 * 5. Velocity Consistency (10%) - Steady vs sporadic sales
 */

/**
 * Input data for demand scoring
 * Accepts data from multiple sources (BrickLink, Shopee, etc.)
 */
export interface DemandScoringInput {
  // Sales velocity metrics (PRIMARY)
  salesVelocity?: number; // Transactions per day
  timesSold?: number; // Total sales in observation period
  observationDays?: number; // Length of observation period (default 180)

  // Price momentum metrics (SECONDARY)
  currentPrice?: number; // Current average price (cents)
  firstPrice?: number; // Price at start of period (cents)
  lastPrice?: number; // Price at end of period (cents)
  historicalPrices?: number[]; // Array of historical prices (cents)

  // Market depth metrics (TERTIARY)
  availableLots?: number; // Number of competing sellers
  availableQty?: number; // Total units available for sale

  // Consistency metrics (OPTIONAL)
  salesTimestamps?: Date[]; // Individual sale dates for consistency calc

  // Legacy/additional data
  avgDaysBetweenSales?: number; // Alternative to velocity
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
 * Demand score result
 */
export interface DemandScoringResult {
  score: number; // Final 0-100 score
  confidence: number; // Overall confidence (0-1)

  components?: {
    salesVelocity: ComponentScore;
    priceMomentum: ComponentScore;
    marketDepth: ComponentScore;
    supplyDemandRatio: ComponentScore;
    velocityConsistency: ComponentScore;
  };

  metadata: {
    hasSalesData: boolean;
    hasPriceData: boolean;
    hasMarketDepth: boolean;
    observationPeriod: number; // days
  };
}

/**
 * Configuration for scoring weights
 */
const DEFAULT_WEIGHTS = {
  salesVelocity: 0.30, // 30% - Most important
  priceMomentum: 0.25, // 25% - Strong signal
  marketDepth: 0.20, // 20% - Competition matters
  supplyDemandRatio: 0.15, // 15% - Inventory balance
  velocityConsistency: 0.10, // 10% - Reliability indicator
} as const;

/**
 * DemandScoringService - Instance-based service for testability
 */
export class DemandScoringService {
  constructor(private weights = DEFAULT_WEIGHTS) {}

  /**
   * Calculate demand score from market data
   */
  calculateScore(input: DemandScoringInput): DemandScoringResult {
    // Detect available data
    const hasSalesData = (input.salesVelocity !== undefined && input.salesVelocity > 0) ||
      (input.timesSold !== undefined && input.timesSold > 0) ||
      (input.avgDaysBetweenSales !== undefined);

    const hasPriceData = input.currentPrice !== undefined ||
      (input.firstPrice !== undefined && input.lastPrice !== undefined) ||
      (input.historicalPrices !== undefined && input.historicalPrices.length > 0);

    const hasMarketDepth = input.availableLots !== undefined ||
      input.availableQty !== undefined;

    // If no data at all, return zero score
    if (!hasSalesData && !hasPriceData && !hasMarketDepth) {
      return {
        score: 0,
        confidence: 0,
        metadata: {
          hasSalesData: false,
          hasPriceData: false,
          hasMarketDepth: false,
          observationPeriod: input.observationDays ?? 180,
        },
      };
    }

    // Calculate components
    const components = {
      salesVelocity: this.calculateSalesVelocityScore(input),
      priceMomentum: this.calculatePriceMomentumScore(input),
      marketDepth: this.calculateMarketDepthScore(input),
      supplyDemandRatio: this.calculateSupplyDemandScore(input),
      velocityConsistency: this.calculateVelocityConsistencyScore(input),
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
        hasSalesData,
        hasPriceData,
        hasMarketDepth,
        observationPeriod: input.observationDays ?? 180,
      },
    };
  }

  /**
   * Component 1: Sales Velocity Score (30% weight)
   * Higher velocity = higher demand
   */
  private calculateSalesVelocityScore(
    input: DemandScoringInput,
  ): ComponentScore {
    // Calculate velocity if not provided
    let velocity = input.salesVelocity;
    if (!velocity && input.timesSold && input.observationDays) {
      velocity = input.timesSold / input.observationDays;
    }
    if (!velocity && input.avgDaysBetweenSales) {
      velocity = 1 / input.avgDaysBetweenSales;
    }

    if (!velocity || velocity <= 0) {
      return {
        score: 0,
        weight: this.weights.salesVelocity,
        weightedScore: 0,
        confidence: 0,
        notes: "No sales velocity data",
      };
    }

    // Score mapping (logarithmic scale):
    // 0.001 sales/day (1 sale per 1000 days) = 10 score
    // 0.01 sales/day (1 sale per 100 days) = 30 score
    // 0.1 sales/day (1 sale per 10 days) = 60 score
    // 0.5 sales/day (1 sale per 2 days) = 85 score
    // 1.0+ sales/day (daily sales) = 100 score

    const score = this.mapVelocityToScore(velocity);
    const confidence = input.timesSold && input.timesSold >= 10 ? 0.9 : 0.6;

    return {
      score,
      weight: this.weights.salesVelocity,
      weightedScore: score * this.weights.salesVelocity,
      confidence,
      notes: `${velocity.toFixed(3)} sales/day`,
    };
  }

  /**
   * Map velocity to 0-100 score using logarithmic scale
   */
  private mapVelocityToScore(velocity: number): number {
    if (velocity <= 0) return 0;
    if (velocity >= 1.0) return 100;

    // Logarithmic interpolation
    // velocity 0.001 -> 10
    // velocity 0.01 -> 30
    // velocity 0.1 -> 60
    // velocity 0.5 -> 85
    // velocity 1.0 -> 100

    const logVelocity = Math.log10(velocity);
    // log10(0.001) = -3, log10(1.0) = 0
    // Map [-3, 0] to [10, 100]

    const score = 10 + ((logVelocity + 3) / 3) * 90;
    return this.clamp(score, 0, 100);
  }

  /**
   * Component 2: Price Momentum Score (25% weight)
   * Rising prices = higher demand, falling = lower
   */
  private calculatePriceMomentumScore(
    input: DemandScoringInput,
  ): ComponentScore {
    // Need start and end prices for momentum
    const startPrice = input.firstPrice;
    const endPrice = input.lastPrice || input.currentPrice;

    if (!startPrice || !endPrice || startPrice <= 0) {
      return {
        score: 50, // Neutral when no data
        weight: this.weights.priceMomentum,
        weightedScore: 50 * this.weights.priceMomentum,
        confidence: 0.2, // Low confidence
        notes: "Insufficient price data",
      };
    }

    // Calculate price change percentage
    const priceChange = ((endPrice - startPrice) / startPrice) * 100;

    // Score mapping:
    // -20% or more decline = 0 score (very weak demand)
    // 0% change = 50 score (neutral)
    // +20% or more increase = 100 score (very strong demand)

    let score = 50 + (priceChange / 20) * 50;
    score = this.clamp(score, 0, 100);

    const confidence = input.historicalPrices && input.historicalPrices.length >= 5
      ? 0.8
      : 0.5;

    return {
      score,
      weight: this.weights.priceMomentum,
      weightedScore: score * this.weights.priceMomentum,
      confidence,
      notes: `${priceChange > 0 ? "+" : ""}${priceChange.toFixed(1)}% price change`,
    };
  }

  /**
   * Component 3: Market Depth Score (20% weight)
   * Fewer sellers = higher demand (scarcity)
   */
  private calculateMarketDepthScore(
    input: DemandScoringInput,
  ): ComponentScore {
    const lots = input.availableLots;

    if (!lots || lots <= 0) {
      return {
        score: 50, // Neutral when no data
        weight: this.weights.marketDepth,
        weightedScore: 50 * this.weights.marketDepth,
        confidence: 0.2,
        notes: "No market depth data",
      };
    }

    // Score mapping (inverse relationship):
    // 1-5 sellers = 100 score (very scarce)
    // 10 sellers = 80 score
    // 20 sellers = 60 score
    // 50 sellers = 40 score
    // 100+ sellers = 20 score (oversupplied)

    let score: number;
    if (lots <= 5) score = 100;
    else if (lots <= 10) score = 80;
    else if (lots <= 20) score = 60;
    else if (lots <= 50) score = 40;
    else if (lots <= 100) score = 20;
    else score = 10;

    return {
      score,
      weight: this.weights.marketDepth,
      weightedScore: score * this.weights.marketDepth,
      confidence: 0.7,
      notes: `${lots} competing sellers`,
    };
  }

  /**
   * Component 4: Supply/Demand Ratio Score (15% weight)
   * Lower inventory relative to sales = higher demand
   */
  private calculateSupplyDemandScore(
    input: DemandScoringInput,
  ): ComponentScore {
    const qty = input.availableQty;
    let velocity = input.salesVelocity;

    if (!velocity && input.timesSold && input.observationDays) {
      velocity = input.timesSold / input.observationDays;
    }

    if (!qty || !velocity || velocity <= 0) {
      return {
        score: 50, // Neutral
        weight: this.weights.supplyDemandRatio,
        weightedScore: 50 * this.weights.supplyDemandRatio,
        confidence: 0.2,
        notes: "Insufficient supply/demand data",
      };
    }

    // Calculate days of inventory
    const daysOfInventory = qty / velocity;

    // Score mapping:
    // < 30 days = 100 score (scarce supply)
    // 60 days = 80 score (healthy)
    // 180 days = 50 score (balanced)
    // 365 days = 30 score (oversupplied)
    // 720+ days = 10 score (dead inventory)

    let score: number;
    if (daysOfInventory < 30) score = 100;
    else if (daysOfInventory < 60) score = 80;
    else if (daysOfInventory < 180) score = 50;
    else if (daysOfInventory < 365) score = 30;
    else if (daysOfInventory < 720) score = 15;
    else score = 10;

    return {
      score,
      weight: this.weights.supplyDemandRatio,
      weightedScore: score * this.weights.supplyDemandRatio,
      confidence: 0.7,
      notes: `${Math.round(daysOfInventory)} days of inventory`,
    };
  }

  /**
   * Component 5: Velocity Consistency Score (10% weight)
   * Steady sales = higher confidence in demand
   */
  private calculateVelocityConsistencyScore(
    input: DemandScoringInput,
  ): ComponentScore {
    // This would ideally use salesTimestamps to calculate variance
    // For now, use a simplified approach

    if (!input.timesSold || input.timesSold < 5) {
      return {
        score: 50, // Neutral
        weight: this.weights.velocityConsistency,
        weightedScore: 50 * this.weights.velocityConsistency,
        confidence: 0.3,
        notes: "Insufficient data for consistency analysis",
      };
    }

    // Higher sale count = more likely to be consistent
    // This is a simplified heuristic
    const score = Math.min(input.timesSold * 2, 100);

    return {
      score,
      weight: this.weights.velocityConsistency,
      weightedScore: score * this.weights.velocityConsistency,
      confidence: 0.5,
      notes: `Based on ${input.timesSold} sales`,
    };
  }

  /**
   * Utility: Clamp value to range
   */
  private clamp(value: number, min: number, max: number): number {
    return Math.max(min, Math.min(max, value));
  }
}
