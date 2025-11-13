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
    const [demandScore, availabilityScore, qualityScore] =
      await Promise.all([
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
    );

    if (recommendedBuyPrice) {
      recommendation.recommendedBuyPrice = recommendedBuyPrice;
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
  ): { price: number; reasoning: string; confidence: number } | null {
    // Prepare inputs for ValueCalculator
    const valueInputs: IntrinsicValueInputs = {
      bricklinkAvgPrice: input.pricing.bricklink?.current.newAvg,
      bricklinkMaxPrice: input.pricing.bricklink?.current.newMax,
      retirementStatus: input.availability.retiringSoon
        ? "retiring_soon"
        : undefined,
      demandScore: demandScore?.value,
      qualityScore: undefined, // Not used in intrinsic value calculation currently
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
