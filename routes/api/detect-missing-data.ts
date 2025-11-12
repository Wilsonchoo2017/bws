/**
 * API endpoint for manually triggering missing data detection
 *
 * POST /api/detect-missing-data - Run the missing data detector immediately
 * GET /api/detect-missing-data - Preview what would be detected
 */

import { Handlers } from "$fresh/server.ts";
import { getMissingDataDetector } from "../../services/missing-data/MissingDataDetectorService.ts";

export const handler: Handlers = {
  /**
   * POST - Run the missing data detector
   */
  async POST(_req) {
    try {
      console.log("📨 Manual missing data detection triggered");

      const detector = getMissingDataDetector();
      const result = await detector.run();

      return new Response(
        JSON.stringify({
          success: result.success,
          message: result.success
            ? `Missing data detection completed successfully`
            : "Missing data detection failed",
          result: {
            productsChecked: result.productsChecked,
            missingBricklinkData: result.missingBricklinkData,
            jobsEnqueued: result.jobsEnqueued,
            errors: result.errors,
            timestamp: result.timestamp,
            productsWithMissingData: result.productsWithMissingData,
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    } catch (error) {
      console.error("❌ Manual missing data detection failed:", error);

      return new Response(
        JSON.stringify({
          success: false,
          error: error instanceof Error
            ? error.message
            : "Unknown error occurred",
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
  },

  /**
   * GET - Preview what would be detected
   */
  async GET(_req) {
    try {
      const detector = getMissingDataDetector();
      const preview = await detector.preview();

      return new Response(
        JSON.stringify({
          success: true,
          preview: {
            productsWithLegoSets: preview.productsWithLegoSets,
            productsWithBricklinkData: preview.productsWithBricklinkData,
            productsMissingBricklinkData: preview.productsMissingBricklinkData,
            sampleMissingProducts: preview.sampleMissingProducts,
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    } catch (error) {
      console.error("❌ Failed to preview missing data:", error);

      return new Response(
        JSON.stringify({
          success: false,
          error: error instanceof Error
            ? error.message
            : "Unknown error occurred",
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
  },
};
