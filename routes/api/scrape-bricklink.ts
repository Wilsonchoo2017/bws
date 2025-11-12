/**
 * Bricklink scraping API endpoint - Refactored to use queue system
 *
 * This route now follows SOLID principles:
 * - SRP: Only handles HTTP request/response
 * - OCP: Extensible without modification
 * - DIP: Depends on abstractions (QueueService)
 *
 * All scraping is done asynchronously through the job queue.
 */

import { FreshContext } from "$fresh/server.ts";
import { getQueueService, isQueueReady } from "../../services/queue/init.ts";
import { parseBricklinkUrl } from "../../services/bricklink/BricklinkParser.ts";
import {
  createJsonResponse,
  createValidationErrorResponse,
} from "../../utils/api-helpers.ts";

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    const url = new URL(req.url);
    const bricklinkUrl = url.searchParams.get("url");
    const saveToDb = url.searchParams.get("save") !== "false"; // Default to true

    // Validate URL parameter
    if (!bricklinkUrl) {
      return createValidationErrorResponse("Missing 'url' query parameter");
    }

    // Validate Bricklink URL format
    let itemInfo;
    try {
      itemInfo = parseBricklinkUrl(bricklinkUrl);
    } catch (error) {
      return createValidationErrorResponse(
        `Invalid Bricklink URL: ${error.message}`,
      );
    }

    // Check if queue is available
    if (!isQueueReady()) {
      return createJsonResponse(
        {
          error:
            "Scraping queue is not available. Please ensure Redis is running and the queue service is initialized.",
        },
        503,
      );
    }

    // Enqueue the scraping job
    const queueService = getQueueService();
    const job = await queueService.addScrapeJob({
      url: bricklinkUrl,
      itemId: itemInfo.itemId,
      saveToDb,
    });

    // Return job information
    return createJsonResponse({
      message: "Scraping job enqueued successfully",
      job: {
        id: job.id,
        itemId: itemInfo.itemId,
        itemType: itemInfo.itemType,
        url: bricklinkUrl,
        saveToDb,
        status: "queued",
      },
      note: "Use the /api/scrape-queue-status endpoint to check the job status",
    });
  } catch (error) {
    console.error("Error enqueueing scrape job:", error);
    return createJsonResponse(
      {
        error: error instanceof Error ? error.message : "Unknown error",
      },
      500,
    );
  }
};
