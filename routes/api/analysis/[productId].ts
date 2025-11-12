/**
 * API endpoint for single product analysis
 * GET /api/analysis/:productId?strategy=<strategyName>
 */

import { Handlers } from "$fresh/server.ts";
import { analysisService } from "../../../services/analysis/AnalysisService.ts";

export const handler: Handlers = {
  async GET(req, ctx) {
    const { productId } = ctx.params;
    const url = new URL(req.url);
    const strategy = url.searchParams.get("strategy") || undefined;

    try {
      const recommendation = await analysisService.analyzeProduct(
        productId,
        strategy,
      );

      return new Response(JSON.stringify(recommendation), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      });
    } catch (error) {
      // Log detailed error information to server console
      console.error("=== Analysis Error ===");
      console.error("Product ID:", productId);
      console.error("Strategy:", strategy);
      console.error("Error:", error);
      if (error instanceof Error) {
        console.error("Stack:", error.stack);
      }
      console.error("===================");

      const errorMessage = error instanceof Error
        ? error.message
        : "Unknown error";

      return new Response(
        JSON.stringify({
          error: errorMessage,
          productId,
          details: error instanceof Error ? error.stack : undefined,
        }),
        {
          status: error instanceof Error && errorMessage.includes("not found")
            ? 404
            : 500,
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    }
  },
};
