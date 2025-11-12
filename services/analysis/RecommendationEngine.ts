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
  PricingData,
  ProductAnalysisInput,
  ProductRecommendation,
  QualityData,
} from "./types.ts";

export class RecommendationEngine {
  private pricingAnalyzer: IAnalyzer<PricingData>;
  private demandAnalyzer: IAnalyzer<DemandData>;
  private availabilityAnalyzer: IAnalyzer<AvailabilityData>;
  private qualityAnalyzer: IAnalyzer<QualityData>;
  private strategies: Map<string, IStrategy>;

  constructor(
    pricingAnalyzer: IAnalyzer<PricingData>,
    demandAnalyzer: IAnalyzer<DemandData>,
    availabilityAnalyzer: IAnalyzer<AvailabilityData>,
    qualityAnalyzer: IAnalyzer<QualityData>,
    strategies: IStrategy[],
  ) {
    this.pricingAnalyzer = pricingAnalyzer;
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
    const [pricingScore, demandScore, availabilityScore, qualityScore] =
      await Promise.all([
        this.pricingAnalyzer.analyze(input.pricing),
        this.demandAnalyzer.analyze(input.demand),
        this.availabilityAnalyzer.analyze(input.availability),
        this.qualityAnalyzer.analyze(input.quality),
      ]);

    // Build dimensional scores
    const scores: DimensionalScores = {
      pricing: pricingScore,
      demand: demandScore,
      availability: availabilityScore,
      quality: qualityScore,
    };

    // Use strategy to interpret scores and generate recommendation
    const recommendation = strategy.interpret(scores);

    return recommendation;
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
        name: this.pricingAnalyzer.getName(),
        description: this.pricingAnalyzer.getDescription(),
      },
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
