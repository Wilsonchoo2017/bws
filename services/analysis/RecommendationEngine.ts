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
    const recommendedBuyPriceResult = this.calculateRecommendedBuyPrice(
      input,
      strategyName as StrategyType,
      demandScore,
      availabilityScore,
      qualityScore,
    );

    if (recommendedBuyPriceResult) {
      const { recommendedBuyPrice, rejectionReason } = recommendedBuyPriceResult;

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

      // Store rejection reason if present
      if (rejectionReason) {
        // Add rejection reason to risks array for visibility
        if (!recommendation.risks.includes(rejectionReason)) {
          recommendation.risks.unshift(rejectionReason); // Add at beginning
        }
        // Also add to reasoning
        if (recommendation.overall.reasoning) {
          recommendation.overall.reasoning = `${rejectionReason}. ${recommendation.overall.reasoning}`;
        } else {
          recommendation.overall.reasoning = rejectionReason;
        }
      }
    }

    return recommendation;
  }

  /**
   * Calculate recommended buy price using ValueCalculator
   * Returns both the price result and any rejection reason
   */
  private calculateRecommendedBuyPrice(
    input: ProductAnalysisInput,
    strategy: StrategyType,
    demandScore: { value: number } | null,
    availabilityScore: { value: number } | null,
    qualityScore: { value: number } | null,
  ): {
    recommendedBuyPrice: {
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
  } | null;
    rejectionReason?: string;
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
      originalRetailPrice: input.pricing.originalRetailPrice, // For deal quality analysis
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
      availabilityScore: availabilityScore?.value, // For scarcity multiplier
      // Liquidity metrics
      salesVelocity: input.demand.bricklinkSalesVelocity,
      avgDaysBetweenSales: input.demand.bricklinkAvgDaysBetweenSales,
      timesSold: input.demand.bricklinkSixMonthNewTimesSold || input.demand.bricklinkTimesSold, // For zero sales penalty
      // Volatility metric
      priceVolatility: input.demand.bricklinkPriceVolatility,
      // Saturation metrics
      availableQty: input.demand.bricklinkCurrentNewQty,
      availableLots: input.demand.bricklinkCurrentNewLots,
      // NEW: Set characteristics for theme and PPD multipliers
      theme: input.quality.theme,
      partsCount: input.quality.partsCount,
    };

    // Calculate recommended buy price with breakdown
    const result = ValueCalculator.calculateRecommendedBuyPrice(valueInputs, {
      strategy,
      availabilityScore: availabilityScore?.value,
      demandScore: demandScore?.value,
    });

    // If null, check if there's a rejection reason in the breakdown
    if (!result) {
      // Try to get the rejection reason by recalculating with breakdown
      const { breakdown } = ValueCalculator.calculateIntrinsicValueWithBreakdown(
        valueInputs,
      );

      if (breakdown.rejection?.rejected) {
        return {
          recommendedBuyPrice: null,
          rejectionReason: breakdown.rejection.reason,
        };
      }

      return {
        recommendedBuyPrice: null,
        rejectionReason: "Insufficient data for value analysis",
      };
    }

    return {
      recommendedBuyPrice: result,
      rejectionReason: undefined,
    };
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

  /**
   * Detect if this is a pre-retirement opportunity
   * DEMAND-GATED: Only flag as opportunity if there's real demand
   *
   * Criteria:
   * - Set is retiring soon (limited time to accumulate)
   * - Demand score >= 50 (must have at least moderate demand)
   * - Quality score >= 40 (avoid poor quality sets)
   *
   * Philosophy: Retirement alone doesn't create value, DEMAND does.
   * A retiring set with no buyers is just old inventory!
   */
  isPreRetirementOpportunity(
    availability: { retiringSoon?: boolean; yearRetired?: number },
    demandScore?: number,
    qualityScore?: number,
  ): {
    isOpportunity: boolean;
    reason: string;
    urgency: "high" | "medium" | "low";
  } {
    const isRetiringSoon = availability.retiringSoon === true;
    const hasSufficientDemand = (demandScore ?? 0) >= 50;
    const hasDecentQuality = (qualityScore ?? 0) >= 40;

    if (!isRetiringSoon) {
      return {
        isOpportunity: false,
        reason: "Set is not retiring soon",
        urgency: "low",
      };
    }

    if (!hasSufficientDemand) {
      return {
        isOpportunity: false,
        reason:
          `Retiring soon but demand too low (${demandScore?.toFixed(0) ?? "unknown"}/100) - likely won't appreciate`,
        urgency: "low",
      };
    }

    if (!hasDecentQuality) {
      return {
        isOpportunity: false,
        reason:
          `Retiring soon with demand, but quality too low (${qualityScore?.toFixed(0) ?? "unknown"}/100)`,
        urgency: "low",
      };
    }

    // All criteria met - this is a PRE-RETIREMENT OPPORTUNITY
    let urgency: "high" | "medium" | "low" = "medium";
    let reason = "Set retiring soon with strong demand - accumulate before scarcity";

    // Adjust urgency based on demand strength
    if (demandScore! >= 70) {
      urgency = "high";
      reason =
        "EXCELLENT PRE-RETIREMENT OPPORTUNITY: Retiring soon with exceptional demand - accumulate aggressively";
    } else if (demandScore! >= 60) {
      urgency = "high";
      reason =
        "STRONG PRE-RETIREMENT OPPORTUNITY: Retiring soon with strong demand - accumulate now";
    }

    return {
      isOpportunity: true,
      reason,
      urgency,
    };
  }

  /**
   * Detect if set is in the "value appreciation phase"
   * Retired + Early stage (0-5 years) + Strong demand = Sweet spot for value growth
   *
   * Philosophy: Best time to hold is early retirement when:
   * 1. Supply stops (retired)
   * 2. Market hasn't fully absorbed available inventory yet
   * 3. Demand remains strong
   */
  isInAppreciationPhase(
    availability: { retiringSoon?: boolean; yearRetired?: number },
    demandScore?: number,
  ): {
    isInPhase: boolean;
    reason: string;
    phase: "market-flooded" | "stabilizing" | "appreciation" | "scarcity" | "vintage" | "none";
  } {
    const currentYear = new Date().getFullYear();
    const yearRetired = availability.yearRetired;
    const hasSufficientDemand = (demandScore ?? 0) >= 50;

    if (!yearRetired) {
      return {
        isInPhase: false,
        reason: "Set is not retired or retirement date unknown",
        phase: "none",
      };
    }

    const yearsPostRetirement = currentYear - yearRetired;

    if (!hasSufficientDemand) {
      return {
        isInPhase: false,
        reason:
          `Retired but demand too low (${demandScore?.toFixed(0) ?? "unknown"}/100) - won't appreciate without buyers`,
        phase: "none",
      };
    }

    // Determine phase based on years post-retirement
    if (yearsPostRetirement < 1) {
      return {
        isInPhase: false,
        reason:
          "Recently retired (<1 year) - market likely flooded, wait for stabilization",
        phase: "market-flooded",
      };
    } else if (yearsPostRetirement < 2) {
      return {
        isInPhase: true,
        reason:
          "STABILIZING PHASE (1-2 years retired): Good time to accumulate as market absorbs supply",
        phase: "stabilizing",
      };
    } else if (yearsPostRetirement < 5) {
      return {
        isInPhase: true,
        reason:
          "APPRECIATION PHASE (2-5 years retired): Prime value growth period with strong demand",
        phase: "appreciation",
      };
    } else if (yearsPostRetirement < 10) {
      return {
        isInPhase: true,
        reason:
          "SCARCITY PHASE (5-10 years retired): Limited supply drives premium prices",
        phase: "scarcity",
      };
    } else {
      return {
        isInPhase: true,
        reason:
          "VINTAGE PHASE (10+ years retired): Collector's item with premium pricing",
        phase: "vintage",
      };
    }
  }
}
