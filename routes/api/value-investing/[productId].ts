/**
 * API endpoint for intrinsic value analysis
 * GET /api/value-investing/:productId
 *
 * This endpoint reuses the existing value investing infrastructure
 * to provide consistent intrinsic value metrics.
 */

import { Handlers } from "$fresh/server.ts";
import { eq } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import { products } from "../../../db/schema.ts";
import { AnalysisService } from "../../../services/analysis/AnalysisService.ts";
import { asCents, type Cents } from "../../../types/price.ts";
import { ValueCalculator } from "../../../services/value-investing/ValueCalculator.ts";
import type { IntrinsicValueInputs } from "../../../types/value-investing.ts";
import { PostRetirementValueProjector } from "../../../services/value-investing/PostRetirementValueProjector.ts";
import type { DataQualityResult } from "../../../services/value-investing/DataQualityValidator.ts";

export const handler: Handlers = {
  async GET(_req, ctx) {
    const { productId } = ctx.params;

    try {
      // Fetch the product
      const [product] = await db
        .select()
        .from(products)
        .where(eq(products.productId, productId))
        .limit(1);

      if (!product) {
        return new Response(
          JSON.stringify({ error: "Product not found" }),
          {
            status: 404,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      // Get the product analysis directly from AnalysisService
      const analysisService = new AnalysisService();

      const analysisResults = await analysisService.analyzeProducts([
        product.productId,
      ]);
      const analysis = analysisResults.get(product.productId);

      if (!analysis) {
        return new Response(
          JSON.stringify({ error: "No analysis available for this product" }),
          {
            status: 404,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      // Check if we have enough data for value analysis
      if (!analysis.recommendedBuyPrice) {
        // Extract rejection reason if available
        const rejectionReason = analysis.overall?.reasoning ||
          analysis.risks?.[0] ||
          "Insufficient data for value analysis";

        return new Response(
          JSON.stringify({
            error: "Cannot calculate intrinsic value",
            reason: rejectionReason,
            details: {
              action: analysis.action,
              risks: analysis.risks,
              opportunities: analysis.opportunities,
              strategy: analysis.strategy,
              reasoning: analysis.overall.reasoning,
            },
          }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      // Calculate value metrics from the analysis
      // IMPORTANT: ALL prices are in CENTS throughout the system
      // - product.price is in CENTS (from database)
      // - analysis.recommendedBuyPrice.price is in CENTS (from ValueCalculator)
      // - IntrinsicValueCard expects all prices in CENTS (converts to dollars for display)
      const currentPriceCents: Cents = asCents(product.price!);
      const targetPriceCents: Cents = asCents(
        analysis.recommendedBuyPrice.price,
      );

      // Calculate intrinsic value from breakdown if available, otherwise estimate
      const intrinsicValueCents: Cents =
        analysis.recommendedBuyPrice.breakdown?.intrinsicValue
          ? asCents(analysis.recommendedBuyPrice.breakdown.intrinsicValue)
          : asCents(
            Math.round(analysis.recommendedBuyPrice.price / (1 - 0.25)),
          ); // Estimate assuming 25% margin

      // Calculate deal quality metrics
      const dealQualityInputs: IntrinsicValueInputs = {
        currentRetailPrice: currentPriceCents,
        originalRetailPrice: product.priceBeforeDiscount
          ? asCents(product.priceBeforeDiscount)
          : undefined,
        bricklinkAvgPrice: analysis.recommendedBuyPrice.breakdown?.inputs
            .bricklinkAvgPrice
          ? asCents(
            analysis.recommendedBuyPrice.breakdown.inputs.bricklinkAvgPrice,
          )
          : undefined,
        msrp: analysis.recommendedBuyPrice.breakdown?.inputs.msrp
          ? asCents(analysis.recommendedBuyPrice.breakdown.inputs.msrp)
          : undefined,
      };

      const dealQuality = ValueCalculator.calculateDealQuality(
        dealQualityInputs,
        intrinsicValueCents,
      );

      // Extract data quality from calculation breakdown (if using enhanced calculator)
      const calculationBreakdown = (analysis.recommendedBuyPrice.breakdown as {
        calculationBreakdown?:
          import("../../../types/value-investing.ts").IntrinsicValueBreakdown;
        dataQuality?: DataQualityResult;
      })?.calculationBreakdown;

      const dataQualityRaw = (analysis.recommendedBuyPrice.breakdown as {
        dataQuality?: DataQualityResult;
      })?.dataQuality;

      // Calculate months of inventory for market supply context
      // Note: dimensionalScores may not be available, use breakdown inputs as fallback
      // deno-lint-ignore no-explicit-any
      const availableQty = (analysis as any).dimensionalScores?.demand?.dataPoints
        ?.bricklinkCurrentNewQty;
      // deno-lint-ignore no-explicit-any
      const salesVelocity = (analysis as any).dimensionalScores?.demand?.dataPoints
        ?.bricklinkSalesVelocity;

      const bricklinkData = (availableQty !== undefined && salesVelocity !== undefined)
        ? { availableQty, salesVelocity }
        : null;

      const monthsOfInventory = bricklinkData
        ? PostRetirementValueProjector.calculateMonthsOfInventory(
          // deno-lint-ignore no-explicit-any
          bricklinkData as any,
        )
        : null;

      // Calculate future value projections (if we have sufficient data)
      let valueProjection = null;
      if (
        dataQualityRaw?.canCalculate &&
        analysis.recommendedBuyPrice.breakdown?.inputs
      ) {
        const worldBricksData = {
          status: analysis.recommendedBuyPrice.breakdown.inputs.retirementStatus,
          yearRetired: undefined, // Would need to extract from product data
          theme: undefined, // Would need to extract from product data
        };

        const demandScore = analysis.recommendedBuyPrice.breakdown.inputs
          .demandScore ?? 0;
        const qualityScore = analysis.recommendedBuyPrice.breakdown.inputs
          .qualityScore ?? 0;

        try {
          const projection = PostRetirementValueProjector.projectFutureValue(
            intrinsicValueCents,
            // deno-lint-ignore no-explicit-any
            bricklinkData as any,
            // deno-lint-ignore no-explicit-any
            worldBricksData as any,
            demandScore,
            qualityScore,
          );

          valueProjection = {
            currentValue: projection.currentValue,
            oneYearValue: projection.oneYearValue,
            threeYearValue: projection.threeYearValue,
            fiveYearValue: projection.fiveYearValue,
            expectedCAGR: projection.expectedCAGR,
            supplyExhaustionMonths: projection.supplyExhaustionMonths,
            monthsOfInventory,
            projectionConfidence: projection.projectionConfidence,
            assumptions: projection.assumptions,
            risks: projection.risks,
          };
        } catch (error) {
          console.warn("Could not calculate value projections:", error);
        }
      }

      // Detect pre-retirement catalyst
      let catalyst = null;
      // deno-lint-ignore no-explicit-any
      const availabilityData = (analysis as any).dimensionalScores?.availability
        ?.dataPoints;
      if (availabilityData) {
        const retiringSoon = availabilityData.retiringSoon === true;
        const demandScore = analysis.recommendedBuyPrice.breakdown?.inputs
          ?.demandScore ?? 0;

        const isOpportunity = PostRetirementValueProjector
          .isPreRetirementOpportunity(
            { retiringSoon },
            demandScore,
          );

        if (isOpportunity) {
          catalyst = {
            isPreRetirementOpportunity: true,
            urgency: demandScore >= 70
              ? "high"
              : demandScore >= 60
              ? "medium"
              : "low",
            reason:
              "Set retiring soon with strong demand - accumulate before scarcity",
          };
        }
      }

      // Detect appreciation phase
      let appreciationPhase = null;
      if (
        availabilityData?.yearRetired &&
        analysis.recommendedBuyPrice.breakdown?.inputs?.demandScore
      ) {
        const currentYear = new Date().getFullYear();
        const yearsPostRetirement = currentYear - availabilityData.yearRetired;
        const demandScore = analysis.recommendedBuyPrice.breakdown.inputs
          .demandScore;

        if (demandScore >= 50) {
          if (yearsPostRetirement < 1) {
            appreciationPhase = {
              phase: "market-flooded",
              description:
                "Recently retired - market likely flooded, wait for stabilization",
            };
          } else if (yearsPostRetirement < 2) {
            appreciationPhase = {
              phase: "stabilizing",
              description:
                "Good time to accumulate as market absorbs supply",
            };
          } else if (yearsPostRetirement < 5) {
            appreciationPhase = {
              phase: "appreciation",
              description: "Prime value growth period with strong demand",
            };
          } else if (yearsPostRetirement < 10) {
            appreciationPhase = {
              phase: "scarcity",
              description: "Limited supply drives premium prices",
            };
          } else {
            appreciationPhase = {
              phase: "vintage",
              description: "Collector's item with premium pricing",
            };
          }
        }
      }

      // Format data quality for API response
      const dataQuality = dataQualityRaw
        ? {
          canCalculate: dataQualityRaw.canCalculate,
          qualityScore: dataQualityRaw.qualityScore,
          confidenceLevel: dataQualityRaw.confidenceLevel,
          explanation: dataQualityRaw.explanation,
          missingCriticalData: dataQualityRaw.missingCriticalData,
          missingOptionalData: dataQualityRaw.missingOptionalData,
          breakdown: dataQualityRaw.breakdown,
        }
        : null;

      const valueMetrics = {
        currentPrice: currentPriceCents,
        targetPrice: targetPriceCents,
        intrinsicValue: intrinsicValueCents,
        marginOfSafety:
          ((intrinsicValueCents - currentPriceCents) / intrinsicValueCents) *
          100,
        expectedROI:
          ((intrinsicValueCents - currentPriceCents) / currentPriceCents) * 100,
        timeHorizon: analysis.timeHorizon || "Unknown",
        // Deal quality metrics
        dealQualityScore: dealQuality?.dealQualityScore,
        dealQualityLabel: dealQuality?.dealQualityLabel,
        dealRecommendation: dealQuality?.recommendation,
        retailDiscountPercent: dealQuality?.retailDiscountPercent,
        priceToMarketRatio: dealQuality?.priceToMarketRatio,
        priceToValueRatio: dealQuality?.priceToValueRatio,
        // Detailed calculation breakdown for step-by-step intrinsic value calculation
        calculationBreakdown,
        // ENHANCED: Future value projections
        valueProjection,
        // ENHANCED: Data quality assessment
        dataQuality,
        // ENHANCED: Months of inventory for market supply context
        monthsOfInventory,
      };

      // Return the intrinsic value data formatted for the IntrinsicValueCard
      const response = {
        valueMetrics,
        action: analysis.action,
        risks: analysis.risks || [],
        opportunities: analysis.opportunities || [],
        analyzedAt: new Date().toISOString(),
        currency: product.currency || "MYR",
        // Include calculation breakdown for formula display
        breakdown: analysis.recommendedBuyPrice.breakdown,
        reasoning: analysis.recommendedBuyPrice.reasoning,
        confidence: analysis.recommendedBuyPrice.confidence,
        // ENHANCED: Catalyst and phase detection
        catalyst,
        appreciationPhase,
        // Include quality, demand, and availability score breakdowns with multiplier info
        dimensionalScores: {
          quality: analysis.dimensions.quality
            ? {
              score: analysis.dimensions.quality.value,
              confidence: analysis.dimensions.quality.confidence,
              reasoning: analysis.dimensions.quality.reasoning,
              breakdown: analysis.dimensions.quality.breakdown,
            }
            : null,
          demand: analysis.dimensions.demand
            ? {
              score: analysis.dimensions.demand.value,
              confidence: analysis.dimensions.demand.confidence,
              reasoning: analysis.dimensions.demand.reasoning,
              breakdown: analysis.dimensions.demand.breakdown,
            }
            : null,
          availability: analysis.dimensions.availability
            ? {
              score: analysis.dimensions.availability.value,
              confidence: analysis.dimensions.availability.confidence,
              reasoning: analysis.dimensions.availability.reasoning,
              breakdown: analysis.dimensions.availability.breakdown,
            }
            : null,
        },
        // Legacy fields for backward compatibility
        qualityScoreBreakdown: analysis.dimensions.quality?.dataPoints
          ?.qualityScoreBreakdown,
        demandScoreBreakdown: analysis.dimensions.demand?.dataPoints
          ?.demandScoreBreakdown,
        availabilityScoreBreakdown: analysis.dimensions.availability?.breakdown,
      };

      return new Response(JSON.stringify(response), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      console.error("=== Value Investing Analysis Error ===");
      console.error("Product ID:", productId);
      console.error("Error:", error);
      if (error instanceof Error) {
        console.error("Stack:", error.stack);
      }
      console.error("====================================");

      const errorMessage = error instanceof Error
        ? error.message
        : "Unknown error";

      // Check if error is due to incomplete Bricklink data
      const isBricklinkDataError = errorMessage.includes(
        "Complete Bricklink sales data is required",
      );
      const statusCode = isBricklinkDataError ? 422 : 500;

      return new Response(
        JSON.stringify({
          error: errorMessage,
          productId,
          code: isBricklinkDataError
            ? "INCOMPLETE_BRICKLINK_DATA"
            : "INTERNAL_ERROR",
        }),
        {
          status: statusCode,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
  },
};
