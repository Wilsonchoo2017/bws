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
      console.error("Analysis error:", error);

      const errorMessage = error instanceof Error
        ? error.message
        : "Unknown error";

      return new Response(
        JSON.stringify({
          error: errorMessage,
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
