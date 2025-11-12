/**
 * AnalysisService - Main service orchestrator for product analysis
 * REFACTORED to follow SOLID principles:
 * - Single Responsibility: Only coordinates analysis flow
 * - Dependency Inversion: Depends on repository interfaces, not concrete implementations
 * - Open/Closed: Easy to extend without modification
 */

import { PricingAnalyzer } from "./analyzers/PricingAnalyzer.ts";
import { DemandAnalyzer } from "./analyzers/DemandAnalyzer.ts";
import { AvailabilityAnalyzer } from "./analyzers/AvailabilityAnalyzer.ts";
import { QualityAnalyzer } from "./analyzers/QualityAnalyzer.ts";

import { BargainHunterStrategy } from "./strategies/BargainHunterStrategy.ts";
import { InvestmentFocusStrategy } from "./strategies/InvestmentFocusStrategy.ts";
import { QuickFlipStrategy } from "./strategies/QuickFlipStrategy.ts";

import { RecommendationEngine } from "./RecommendationEngine.ts";
import { DataAggregationService } from "./DataAggregationService.ts";

// Repository imports
import { ProductRepository } from "./repositories/ProductRepository.ts";
import { BricklinkRepository } from "./repositories/BricklinkRepository.ts";
import { RedditRepository } from "./repositories/RedditRepository.ts";
import { RetirementRepository } from "./repositories/RetirementRepository.ts";

import type { ProductRecommendation } from "./types.ts";

export class AnalysisService {
  private recommendationEngine: RecommendationEngine;
  private dataAggregationService: DataAggregationService;
  private defaultStrategy = "Investment Focus";

  constructor() {
    // Initialize repositories (Dependency Injection)
    const productRepo = new ProductRepository();
    const bricklinkRepo = new BricklinkRepository();
    const redditRepo = new RedditRepository();
    const retirementRepo = new RetirementRepository();

    // Initialize data aggregation service with repositories
    this.dataAggregationService = new DataAggregationService(
      productRepo,
      bricklinkRepo,
      redditRepo,
      retirementRepo,
    );

    // Initialize analyzers
    const pricingAnalyzer = new PricingAnalyzer();
    const demandAnalyzer = new DemandAnalyzer();
    const availabilityAnalyzer = new AvailabilityAnalyzer();
    const qualityAnalyzer = new QualityAnalyzer();

    // Initialize strategies
    const strategies = [
      new BargainHunterStrategy(),
      new InvestmentFocusStrategy(),
      new QuickFlipStrategy(),
    ];

    // Initialize recommendation engine
    this.recommendationEngine = new RecommendationEngine(
      pricingAnalyzer,
      demandAnalyzer,
      availabilityAnalyzer,
      qualityAnalyzer,
      strategies,
    );
  }

  /**
   * Analyze a product using the specified strategy
   * Single Responsibility: Coordinate analysis flow only
   */
  async analyzeProduct(
    productId: string,
    strategyName?: string,
  ): Promise<ProductRecommendation> {
    // Step 1: Aggregate data from all sources (delegated to DataAggregationService)
    const input = await this.dataAggregationService.aggregateProductData(
      productId,
    );

    // Step 2: Run analysis with selected strategy (delegated to RecommendationEngine)
    const strategy = strategyName || this.defaultStrategy;
    return await this.recommendationEngine.analyze(input, strategy);
  }

  /**
   * Analyze multiple products in parallel
   */
  async analyzeProducts(
    productIds: string[],
    strategyName?: string,
  ): Promise<Map<string, ProductRecommendation>> {
    const results = new Map<string, ProductRecommendation>();

    // Analyze in parallel using Promise.allSettled
    const analyses = await Promise.allSettled(
      productIds.map((id) => this.analyzeProduct(id, strategyName)),
    );

    // Collect successful results
    analyses.forEach((result, index) => {
      if (result.status === "fulfilled") {
        results.set(productIds[index], result.value);
      }
    });

    return results;
  }

  /**
   * Get available strategies
   */
  getAvailableStrategies() {
    return this.recommendationEngine.getAvailableStrategies();
  }

  /**
   * Get analyzer information
   */
  getAnalyzerInfo() {
    return this.recommendationEngine.getAnalyzerInfo();
  }
}

// Export singleton instance
export const analysisService = new AnalysisService();
