/**
 * API endpoint for available analysis strategies
 * GET /api/analysis/strategies
 */

import { Handlers } from "$fresh/server.ts";
import { analysisService } from "../../../services/analysis/AnalysisService.ts";

export const handler: Handlers = {
  GET() {
    try {
      const strategies = analysisService.getAvailableStrategies();
      const analyzers = analysisService.getAnalyzerInfo();

      return new Response(
        JSON.stringify({
          strategies,
          analyzers,
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    } catch (error) {
      console.error("Strategies error:", error);

      return new Response(
        JSON.stringify({
          error: error instanceof Error ? error.message : "Unknown error",
        }),
        {
          status: 500,
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    }
  },
};
