/**
 * AnalysisService - Main service orchestrator for product analysis
 * REFACTORED to follow SOLID principles:
 * - Single Responsibility: Only coordinates analysis flow
 * - Dependency Inversion: Depends on repository interfaces, not concrete implementations
 * - Open/Closed: Easy to extend without modification
 */

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
import { WorldBricksRepository } from "./repositories/WorldBricksRepository.ts";

// Queue service for auto-enrichment
import { QueueService } from "../queue/QueueService.ts";

import type { ProductRecommendation } from "./types.ts";

export class AnalysisService {
  private recommendationEngine: RecommendationEngine;
  private dataAggregationService: DataAggregationService;
  private productRepo: ProductRepository;
  private defaultStrategy = "Investment Focus";

  constructor(queueService?: QueueService) {
    // Initialize repositories (Dependency Injection)
    this.productRepo = new ProductRepository();
    const bricklinkRepo = new BricklinkRepository();
    const redditRepo = new RedditRepository();
    const retirementRepo = new RetirementRepository();
    const worldBricksRepo = new WorldBricksRepository();

    // Initialize data aggregation service with repositories + queue service
    this.dataAggregationService = new DataAggregationService(
      this.productRepo,
      bricklinkRepo,
      redditRepo,
      retirementRepo,
      worldBricksRepo,
      queueService, // Enable auto-queueing of missing WorldBricks data
    );

    // Initialize analyzers
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
   * Analyze multiple products using batch operations (OPTIMIZED)
   * Solves N+1 query problem by using batch data fetching
   * @param productIds - Array of product IDs to analyze
   * @param strategyName - Optional strategy name
   * @returns Map of productId -> ProductRecommendation
   */
  async analyzeProducts(
    productIds: string[],
    strategyName?: string,
  ): Promise<Map<string, ProductRecommendation>> {
    if (productIds.length === 0) return new Map();

    const results = new Map<string, ProductRecommendation>();
    const strategy = strategyName || this.defaultStrategy;

    try {
      // Step 1: Batch fetch all products (1 query)
      const products = await this.productRepo.findByProductIds(productIds);

      // Step 2: Batch aggregate all related data (3 queries instead of 3*N!)
      const aggregatedDataMap = await this.dataAggregationService
        .aggregateProductsData(products);

      // Step 3: Run analysis for each product
      for (const [productId, input] of aggregatedDataMap.entries()) {
        try {
          const recommendation = await this.recommendationEngine.analyze(
            input,
            strategy,
          );
          results.set(productId, recommendation);
        } catch (error) {
          console.warn(
            `[AnalysisService] Failed to analyze product ${productId}:`,
            error instanceof Error ? error.message : error,
          );
          // Skip failed analyses
        }
      }

      console.info(
        `[AnalysisService] Batch analysis complete: ${results.size}/${productIds.length} successful`,
      );

      return results;
    } catch (error) {
      console.error(
        "[AnalysisService] Batch analysis failed:",
        error instanceof Error ? error.message : error,
      );
      return results; // Return partial results
    }
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

// Export singleton instance with QueueService for auto-enrichment
import { getQueueService } from "../queue/QueueService.ts";

// Lazy initialization to avoid circular dependencies
let analysisServiceInstance: AnalysisService | null = null;

export function getAnalysisService(): AnalysisService {
  if (!analysisServiceInstance) {
    try {
      // Try to get QueueService for auto-enrichment
      const queueService = getQueueService();
      analysisServiceInstance = new AnalysisService(queueService);
    } catch (error) {
      // Fall back to no queue service if not available
      console.warn(
        "[AnalysisService] QueueService not available, auto-enrichment disabled:",
        error,
      );
      analysisServiceInstance = new AnalysisService();
    }
  }
  return analysisServiceInstance;
}

// Export singleton instance (backward compatibility)
export const analysisService = getAnalysisService();
