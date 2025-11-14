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

      const analysisResults = await analysisService.analyzeProducts([product.productId]);
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
        return new Response(
          JSON.stringify({
            error: "Insufficient data for value analysis",
            analysis: {
              action: analysis.action,
              risks: analysis.risks,
              opportunities: analysis.opportunities,
              strategy: analysis.strategy,
              reasoning: analysis.overall.reasoning,
            }
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
      const targetPriceCents: Cents = asCents(analysis.recommendedBuyPrice.price);

      // Calculate intrinsic value from breakdown if available, otherwise estimate
      const intrinsicValueCents: Cents = analysis.recommendedBuyPrice.breakdown?.intrinsicValue
        ? asCents(analysis.recommendedBuyPrice.breakdown.intrinsicValue)
        : asCents(Math.round(analysis.recommendedBuyPrice.price / (1 - 0.25))); // Estimate assuming 25% margin

      const valueMetrics = {
        currentPrice: currentPriceCents,
        targetPrice: targetPriceCents,
        intrinsicValue: intrinsicValueCents,
        marginOfSafety: ((intrinsicValueCents - currentPriceCents) / intrinsicValueCents) * 100,
        expectedROI: ((intrinsicValueCents - currentPriceCents) / currentPriceCents) * 100,
        timeHorizon: analysis.timeHorizon || "Unknown",
      };

      // Return the intrinsic value data formatted for the IntrinsicValueCard
      const response = {
        valueMetrics,
        action: analysis.action,
        risks: analysis.risks || [],
        opportunities: analysis.opportunities || [],
        analyzedAt: new Date().toISOString(),
        currency: product.currency || "MYR",
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

      return new Response(
        JSON.stringify({
          error: errorMessage,
          productId,
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
  },
};
