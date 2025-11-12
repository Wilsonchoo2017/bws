/**
 * Queue status monitoring API endpoint
 *
 * Provides information about scraping jobs in the queue
 */

import { FreshContext } from "$fresh/server.ts";
import { getQueueService, isQueueReady } from "../../services/queue/init.ts";
import { createJsonResponse } from "../../utils/api-helpers.ts";

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    const url = new URL(req.url);
    const jobId = url.searchParams.get("job_id");

    // Check if queue is available
    if (!isQueueReady()) {
      return createJsonResponse(
        {
          error:
            "Queue service is not available. Please ensure Redis is running.",
        },
        503,
      );
    }

    const queueService = getQueueService();

    // Get specific job if job_id is provided
    if (jobId) {
      const job = await queueService.getJob(jobId);

      if (!job) {
        return createJsonResponse({ error: `Job ${jobId} not found` }, 404);
      }

      const state = await job.getState();
      const progress = job.progress;
      const failedReason = job.failedReason;

      return createJsonResponse({
        job: {
          id: job.id,
          name: job.name,
          data: job.data,
          state,
          progress,
          failedReason,
          attemptsMade: job.attemptsMade,
          processedOn: job.processedOn,
          finishedOn: job.finishedOn,
          timestamp: job.timestamp,
        },
      });
    }

    // Get queue statistics
    const counts = await queueService.getJobCounts();

    // Get worker status
    const workerStatus = queueService.getWorkerStatus();

    // Get sample jobs from each category
    const waiting = await queueService.getWaitingJobs(0, 5);
    const active = await queueService.getActiveJobs(0, 5);
    const completed = await queueService.getCompletedJobs(0, 5);
    const failed = await queueService.getFailedJobs(0, 5);

    return createJsonResponse({
      queue: {
        name: "bricklink-scraper",
        counts,
      },
      workerStatus: {
        isAlive: workerStatus.isAlive,
        isPaused: workerStatus.isPaused,
        isRunning: workerStatus.isRunning,
      },
      jobs: {
        waiting: waiting.map((j) => ({
          id: j.id,
          name: j.name,
          data: j.data,
          timestamp: j.timestamp,
        })),
        active: active.map((j) => ({
          id: j.id,
          name: j.name,
          data: j.data,
          progress: j.progress,
          processedOn: j.processedOn,
          attemptsMade: j.attemptsMade,
        })),
        completed: completed.map((j) => ({
          id: j.id,
          name: j.name,
          data: j.data,
          finishedOn: j.finishedOn,
          returnvalue: j.returnvalue,
        })),
        failed: failed.map((j) => ({
          id: j.id,
          name: j.name,
          data: j.data,
          failedReason: j.failedReason,
          attemptsMade: j.attemptsMade,
          finishedOn: j.finishedOn,
        })),
      },
    });
  } catch (error) {
    console.error("Error fetching queue status:", error);
    return createJsonResponse(
      {
        error: error instanceof Error ? error.message : "Unknown error",
      },
      500,
    );
  }
};
