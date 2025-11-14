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
import { ValueInvestingService } from "../../../services/value-investing/ValueInvestingService.ts";

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

      // Use ValueInvestingService to get the complete analysis
      const analysisService = new AnalysisService();
      const valueService = new ValueInvestingService(analysisService);

      const { opportunities } = await valueService.getValueOpportunities([product]);

      if (opportunities.length === 0) {
        return new Response(
          JSON.stringify({ error: "Insufficient data for value analysis" }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      const valueProduct = opportunities[0];

      // Return the intrinsic value data formatted for the IntrinsicValueCard
      const response = {
        valueMetrics: valueProduct.valueMetrics,
        action: valueProduct.action,
        risks: valueProduct.risks,
        opportunities: valueProduct.opportunities,
        analyzedAt: new Date().toISOString(),
        currency: valueProduct.currency,
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
