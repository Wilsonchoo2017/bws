/**
 * Reddit search API endpoint - Refactored to use queue system
 *
 * This route now follows SOLID principles:
 * - SRP: Only handles HTTP request/response
 * - OCP: Extensible without modification
 * - DIP: Depends on abstractions (QueueService)
 *
 * All searching is done asynchronously through the job queue.
 */

import { FreshContext } from "$fresh/server.ts";
import { getQueueService, isQueueReady } from "../../services/queue/init.ts";
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
    const setNumber = url.searchParams.get("set");
    const subreddit = url.searchParams.get("subreddit") || "lego";
    const saveToDb = url.searchParams.get("save") !== "false"; // Default to true

    // Validate set parameter
    if (!setNumber) {
      return createValidationErrorResponse("Missing 'set' query parameter");
    }

    // Check if queue is available
    if (!isQueueReady()) {
      return createJsonResponse(
        {
          error:
            "Search queue is not available. Please ensure Redis is running and the queue service is initialized.",
        },
        503,
      );
    }

    // Enqueue the Reddit search job
    const queueService = getQueueService();
    const job = await queueService.addRedditSearchJob({
      setNumber,
      subreddit,
      saveToDb,
    });

    // Return job information
    return createJsonResponse({
      message: "Reddit search job enqueued successfully",
      job: {
        id: job.id,
        setNumber,
        subreddit,
        saveToDb,
        status: "queued",
      },
      note:
        "Use the /api/scrape-queue-status endpoint to check the job status, or /api/reddit-results?set=" +
        setNumber + " to view results",
    });
  } catch (error) {
    console.error("Error enqueueing Reddit search job:", error);
    return createJsonResponse(
      {
        error: error instanceof Error ? error.message : "Unknown error",
      },
      500,
    );
  }
};
