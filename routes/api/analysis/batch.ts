/**
 * API endpoint for batch product analysis
 * POST /api/analysis/batch
 * Body: { productIds: string[], strategy?: string }
 */

import { Handlers } from "$fresh/server.ts";
import { analysisService } from "../../../services/analysis/AnalysisService.ts";

interface BatchRequest {
  productIds: string[];
  strategy?: string;
}

export const handler: Handlers = {
  async POST(req) {
    try {
      const body: BatchRequest = await req.json();

      if (!body.productIds || !Array.isArray(body.productIds)) {
        return new Response(
          JSON.stringify({
            error: "Invalid request: productIds array is required",
          }),
          {
            status: 400,
            headers: {
              "Content-Type": "application/json",
            },
          },
        );
      }

      if (body.productIds.length === 0) {
        return new Response(
          JSON.stringify({
            error: "Invalid request: productIds array cannot be empty",
          }),
          {
            status: 400,
            headers: {
              "Content-Type": "application/json",
            },
          },
        );
      }

      if (body.productIds.length > 100) {
        return new Response(
          JSON.stringify({
            error: "Invalid request: maximum 100 products per batch",
          }),
          {
            status: 400,
            headers: {
              "Content-Type": "application/json",
            },
          },
        );
      }

      const results = await analysisService.analyzeProducts(
        body.productIds,
        body.strategy,
      );

      // Convert Map to object for JSON serialization
      const resultsObject = Object.fromEntries(results);

      return new Response(JSON.stringify(resultsObject), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      });
    } catch (error) {
      console.error("Batch analysis error:", error);

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
          code: isBricklinkDataError
            ? "INCOMPLETE_BRICKLINK_DATA"
            : "INTERNAL_ERROR",
        }),
        {
          status: statusCode,
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    }
  },
};
