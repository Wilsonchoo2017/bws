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
      const result = await scheduler.run();

      if (!result.success) {
        return createJsonResponse(
          {
            error: `Scheduler run failed: ${result.errors.join(", ")}`,
          },
          500,
        );
      }

      return createJsonResponse({
        message: "Scheduler run completed successfully",
        result: {
          itemsFound: result.itemsFound,
          jobsEnqueued: result.jobsEnqueued,
          errors: result.errors,
          timestamp: result.timestamp,
        },
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
      const preview = await scheduler.preview();

      return createJsonResponse({
        message: "Preview of items needing scraping",
        preview: {
          count: preview.count,
          items: preview.items,
        },
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
