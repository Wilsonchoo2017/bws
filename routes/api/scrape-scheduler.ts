/**
 * Scheduler API endpoint
 *
 * Triggers the automated scraping scheduler
 * Can be called manually or via cron job
 */

import { FreshContext } from "$fresh/server.ts";
import { getScheduler } from "../../services/scheduler/SchedulerService.ts";
import { createJsonResponse } from "../../utils/api-helpers.ts";

export const handler = {
  /**
   * POST /api/scrape-scheduler - Trigger scheduler run
   */
  async POST(_req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const scheduler = getScheduler();
      const results = await scheduler.runAll();

      // Check if any scheduler failed
      const hasFailures = !results.bricklink.success ||
        !results.reddit.success ||
        !results.worldbricks.success;

      if (hasFailures) {
        const allErrors = [
          ...results.bricklink.errors,
          ...results.reddit.errors,
          ...results.worldbricks.errors,
        ];
        return createJsonResponse(
          {
            error: `Scheduler run had failures: ${allErrors.join(", ")}`,
            results,
          },
          500,
        );
      }

      // Calculate totals
      const totalItemsFound = results.bricklink.itemsFound +
        results.reddit.itemsFound +
        results.worldbricks.itemsFound;
      const totalJobsEnqueued = results.bricklink.jobsEnqueued +
        results.reddit.jobsEnqueued +
        results.worldbricks.jobsEnqueued;

      return createJsonResponse({
        message: "All schedulers completed successfully",
        summary: {
          totalItemsFound,
          totalJobsEnqueued,
          timestamp: new Date(),
        },
        results,
      });
    } catch (error) {
      console.error("Error running scheduler:", error);
      return createJsonResponse(
        {
          error: error instanceof Error ? error.message : "Unknown error",
        },
        500,
      );
    }
  },

  /**
   * GET /api/scrape-scheduler - Preview items that will be scraped
   */
  async GET(_req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const scheduler = getScheduler();
      const preview = await scheduler.previewAll();

      return createJsonResponse({
        message: "Preview of items needing scraping",
        preview,
      });
    } catch (error) {
      console.error("Error getting scheduler preview:", error);
      return createJsonResponse(
        {
          error: error instanceof Error ? error.message : "Unknown error",
        },
        500,
      );
    }
  },
};
