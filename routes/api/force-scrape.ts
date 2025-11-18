/**
 * API endpoint for force scraping items
 *
 * POST /api/force-scrape - Force immediate scraping bypassing all checks
 */

import { Handlers } from "$fresh/server.ts";
import { getQueueService } from "../../services/queue/init.ts";
import {
  asBricklinkItemId,
  buildBricklinkCatalogUrl,
} from "../../types/lego-set.ts";
import { JobPriority } from "../../services/queue/QueueService.ts";

export const handler: Handlers = {
  /**
   * POST - Force scrape specific items
   */
  async POST(req) {
    try {
      const body = await req.json();
      const { itemIds } = body as { itemIds: string[] };

      if (!itemIds || !Array.isArray(itemIds) || itemIds.length === 0) {
        return new Response(
          JSON.stringify({
            success: false,
            error: "itemIds array is required and must not be empty",
          }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      console.log(`🔥 Force scrape requested for ${itemIds.length} items`);

      const queueService = getQueueService();

      if (!queueService.isReady()) {
        return new Response(
          JSON.stringify({
            success: false,
            error: "Queue service is not available",
          }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      // Prepare jobs with force flag
      const jobs = itemIds.map((itemId) => {
        const trimmedId = itemId.trim();
        const bricklinkItemId = asBricklinkItemId(trimmedId);
        return {
          url: buildBricklinkCatalogUrl(bricklinkItemId),
          itemId: trimmedId,
          saveToDb: true,
          priority: JobPriority.HIGH,
          force: true, // Bypass all checks
        };
      });

      // Enqueue all jobs in bulk
      const addedJobs = await queueService.addScrapeJobsBulk(jobs);

      console.log(`✅ Force enqueued ${addedJobs.length} jobs`);

      return new Response(
        JSON.stringify({
          success: true,
          message: `Successfully force-enqueued ${addedJobs.length} jobs`,
          result: {
            jobsEnqueued: addedJobs.length,
            itemIds,
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    } catch (error) {
      console.error("❌ Force scrape failed:", error);

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
