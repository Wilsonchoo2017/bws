/**
 * Queue Reset API endpoint
 *
 * POST /api/queue-reset
 * Resets the queue by:
 * 1. Waiting for active jobs to complete
 * 2. Clearing all waiting, completed, and failed jobs
 * 3. Running all schedulers to repopulate the queue
 */

import { getQueueService } from "../../services/queue/QueueService.ts";
import { getScheduler } from "../../services/scheduler/SchedulerService.ts";

export const handler = async (req: Request): Promise<Response> => {
  // Only allow POST requests
  if (req.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "Method not allowed" }),
      {
        status: 405,
        headers: { "Content-Type": "application/json" },
      },
    );
  }

  try {
    console.log("🔄 Queue reset requested...");

    const queueService = getQueueService();
    const schedulerService = getScheduler();

    // Check if queue is initialized
    if (!queueService.isReady()) {
      await queueService.initialize();
    }

    // Step 1: Reset the queue (wait for active jobs, then clean all jobs)
    console.log("🧹 Resetting queue...");
    const resetResult = await queueService.resetQueue();

    console.log("✅ Queue reset complete", resetResult);

    // Step 2: Run all schedulers to repopulate the queue
    console.log("🚀 Running schedulers to repopulate queue...");
    const schedulerResults = await schedulerService.runAll();

    console.log("✅ Schedulers complete", {
      bricklink: schedulerResults.bricklink.jobsEnqueued,
      reddit: schedulerResults.reddit.jobsEnqueued,
      worldbricks: schedulerResults.worldbricks.jobsEnqueued,
    });

    // Calculate total jobs added
    const totalJobsAdded = schedulerResults.bricklink.jobsEnqueued +
      schedulerResults.reddit.jobsEnqueued +
      schedulerResults.worldbricks.jobsEnqueued;

    // Return detailed summary
    return new Response(
      JSON.stringify({
        success: true,
        message: "Queue reset and repopulated successfully",
        cleared: {
          active: resetResult.active,
          waiting: resetResult.waiting,
          completed: resetResult.completed,
          failed: resetResult.failed,
          total: resetResult.active + resetResult.waiting +
            resetResult.completed + resetResult.failed,
        },
        repopulated: {
          bricklink: schedulerResults.bricklink.jobsEnqueued,
          reddit: schedulerResults.reddit.jobsEnqueued,
          worldbricks: schedulerResults.worldbricks.jobsEnqueued,
          total: totalJobsAdded,
        },
        errors: [
          ...schedulerResults.bricklink.errors,
          ...schedulerResults.reddit.errors,
          ...schedulerResults.worldbricks.errors,
        ],
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    console.error("❌ Queue reset failed:", error);

    return new Response(
      JSON.stringify({
        success: false,
        error: "Queue reset failed",
        message: error.message,
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
};
