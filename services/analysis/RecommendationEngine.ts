/**
 * RecommendationEngine - Coordinates analyzers and strategies
 * Follows Dependency Inversion: depends on abstractions (IAnalyzer, IStrategy)
 */

import type {
  AvailabilityData,
  DemandData,
  DimensionalScores,
  IAnalyzer,
  IStrategy,
  ProductAnalysisInput,
  ProductRecommendation,
  QualityData,
} from "./types.ts";
import {
  type StrategyType,
  ValueCalculator,
} from "../value-investing/ValueCalculator.ts";
import type { IntrinsicValueInputs } from "../../types/value-investing.ts";
import { asCents } from "../../types/price.ts";

export class RecommendationEngine {
  private demandAnalyzer: IAnalyzer<DemandData>;
  private availabilityAnalyzer: IAnalyzer<AvailabilityData>;
  private qualityAnalyzer: IAnalyzer<QualityData>;
  private strategies: Map<string, IStrategy>;

  constructor(
    demandAnalyzer: IAnalyzer<DemandData>,
    availabilityAnalyzer: IAnalyzer<AvailabilityData>,
    qualityAnalyzer: IAnalyzer<QualityData>,
    strategies: IStrategy[],
  ) {
    this.demandAnalyzer = demandAnalyzer;
    this.availabilityAnalyzer = availabilityAnalyzer;
    this.qualityAnalyzer = qualityAnalyzer;

    // Build strategy registry
    this.strategies = new Map();
    for (const strategy of strategies) {
      this.strategies.set(strategy.getName(), strategy);
    }
  }

  /**
   * Analyze a product and generate recommendation
   */
  async analyze(
    input: ProductAnalysisInput,
    strategyName: string,
  ): Promise<ProductRecommendation> {
    // Get the selected strategy
    const strategy = this.strategies.get(strategyName);
    if (!strategy) {
      throw new Error(`Unknown strategy: ${strategyName}`);
    }

    // Run all analyzers in parallel
    const [demandScore, availabilityScore, qualityScore] = await Promise.all([
      this.demandAnalyzer.analyze(input.demand),
      this.availabilityAnalyzer.analyze(input.availability),
      this.qualityAnalyzer.analyze(input.quality),
    ]);

    // Build dimensional scores
    const scores: DimensionalScores = {
      demand: demandScore,
      availability: availabilityScore,
      quality: qualityScore,
    };

    // Use strategy to interpret scores and generate recommendation
    const recommendation = strategy.interpret(scores);

    // Calculate recommended buy price using ValueCalculator
    const recommendedBuyPrice = this.calculateRecommendedBuyPrice(
      input,
      strategyName as StrategyType,
      demandScore,
      availabilityScore,
      qualityScore,
    );

    if (recommendedBuyPrice) {
      // No conversion needed - ValueCalculator now works in CENTS
      // Cast to Cents branded type
      recommendation.recommendedBuyPrice = {
        price: asCents(recommendedBuyPrice.price),
        reasoning: recommendedBuyPrice.reasoning,
        confidence: recommendedBuyPrice.confidence,
        breakdown: recommendedBuyPrice.breakdown
          ? {
            ...recommendedBuyPrice.breakdown,
            intrinsicValue: asCents(
              recommendedBuyPrice.breakdown.intrinsicValue,
            ),
          }
          : undefined,
      };
    }

    return recommendation;
  }

  /**
   * Calculate recommended buy price using ValueCalculator
   */
  private calculateRecommendedBuyPrice(
    input: ProductAnalysisInput,
    strategy: StrategyType,
    demandScore: { value: number } | null,
    availabilityScore: { value: number } | null,
    qualityScore: { value: number } | null,
  ): {
    price: number;
    reasoning: string;
    confidence: number;
    breakdown?: {
      intrinsicValue: number;
      baseMargin: number;
      adjustedMargin: number;
      marginAdjustments: Array<{ reason: string; value: number }>;
      inputs: {
        msrp?: number;
        bricklinkAvgPrice?: number;
        bricklinkMaxPrice?: number;
        retirementStatus?: string;
        demandScore?: number;
        qualityScore?: number;
        availabilityScore?: number;
      };
    };
  } | null {
    // Determine retirement status with time-decay support
    // IMPROVED: Use WorldBricks yearRetired for accurate calculation
    let retirementStatus: "active" | "retiring_soon" | "retired" | undefined;
    let yearsPostRetirement: number | undefined;

    const currentYear = new Date().getFullYear();

    if (input.availability.retiringSoon) {
      retirementStatus = "retiring_soon";
    } else if (input.availability.yearRetired) {
      // BEST: We have official retirement year from WorldBricks
      retirementStatus = "retired";
      yearsPostRetirement = currentYear - input.availability.yearRetired;
    } else if (input.availability.yearReleased) {
      // Fallback: Estimate based on age (LEGO sets typically 2-3 years before retirement)
      const yearsOld = currentYear - input.availability.yearReleased;

      if (yearsOld > 3) {
        // Likely retired
        retirementStatus = "retired";
        yearsPostRetirement = yearsOld - 3; // Approximate years post-retirement
      } else {
        retirementStatus = "active";
      }
    }

    // Prepare inputs for ValueCalculator with ALL IMPROVEMENTS
    const valueInputs: IntrinsicValueInputs = {
      // FUNDAMENTAL VALUE (MSRP-based)
      msrp: input.pricing.originalRetailPrice, // CRITICAL: Original retail price
      currentRetailPrice: input.pricing.currentRetailPrice,
      // Market prices (for comparison only)
      bricklinkAvgPrice: input.pricing.bricklink?.current.newAvg,
      bricklinkMaxPrice: input.pricing.bricklink?.current.newMax,
      // Retirement data
      retirementStatus,
      yearsPostRetirement,
      yearReleased: input.availability.yearReleased,
      // Analysis scores
      demandScore: demandScore?.value,
      qualityScore: qualityScore?.value,
      // Liquidity metrics
      salesVelocity: input.demand.bricklinkSalesVelocity,
      avgDaysBetweenSales: input.demand.bricklinkAvgDaysBetweenSales,
      // Volatility metric
      priceVolatility: input.demand.bricklinkPriceVolatility,
      // Saturation metrics
      availableQty: input.demand.bricklinkCurrentNewQty,
      availableLots: input.demand.bricklinkCurrentNewLots,
      // NEW: Set characteristics for theme and PPD multipliers
      theme: input.quality.theme,
      partsCount: input.quality.partsCount,
    };

    // Calculate recommended buy price
    return ValueCalculator.calculateRecommendedBuyPrice(valueInputs, {
      strategy,
      availabilityScore: availabilityScore?.value,
      demandScore: demandScore?.value,
    });
  }

  /**
   * Get list of available strategies
   */
  getAvailableStrategies(): Array<{ name: string; description: string }> {
    return Array.from(this.strategies.values()).map((strategy) => ({
      name: strategy.getName(),
      description: strategy.getDescription(),
    }));
  }

  /**
   * Get a specific strategy
   */
  getStrategy(name: string): IStrategy | undefined {
    return this.strategies.get(name);
  }

  /**
   * Add or replace a strategy (Open/Closed Principle - open for extension)
   */
  registerStrategy(strategy: IStrategy): void {
    this.strategies.set(strategy.getName(), strategy);
  }

  /**
   * Get analyzer info
   */
  getAnalyzerInfo(): Array<{ name: string; description: string }> {
    return [
      {
        name: this.demandAnalyzer.getName(),
        description: this.demandAnalyzer.getDescription(),
      },
      {
        name: this.availabilityAnalyzer.getName(),
        description: this.availabilityAnalyzer.getDescription(),
      },
      {
        name: this.qualityAnalyzer.getName(),
        description: this.qualityAnalyzer.getDescription(),
      },
    ];
  }
}
