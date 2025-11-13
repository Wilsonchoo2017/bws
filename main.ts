/// <reference no-default-lib="true" />
/// <reference lib="dom" />
/// <reference lib="dom.iterable" />
/// <reference lib="dom.asynciterable" />
/// <reference lib="deno.ns" />

import "$std/dotenv/load.ts";

import { start } from "$fresh/server.ts";
import manifest from "./fresh.gen.ts";
import config from "./fresh.config.ts";
import { initializeQueue } from "./services/queue/init.ts";
import { getScheduler } from "./services/scheduler/SchedulerService.ts";
import { getMissingDataDetector } from "./services/missing-data/MissingDataDetectorService.ts";
import { logger } from "./utils/logger.ts";

// Initialize BullMQ queue service for background scraping jobs
await initializeQueue();

/**
 * Check if it's time to run a daily task (at 2 AM)
 */
function shouldRunDailyScheduler(lastRun: Date | null): boolean {
  const now = new Date();
  const hour = now.getHours();

  // Run if it's 2 AM and we haven't run today
  if (hour === 2) {
    if (!lastRun) return true;

    const lastRunDate = lastRun.toDateString();
    const nowDate = now.toDateString();
    return lastRunDate !== nowDate;
  }

  return false;
}

/**
 * Check if it's time to run the 6-hour missing data detector
 */
function shouldRunMissingDataDetector(lastRun: Date | null): boolean {
  if (!lastRun) return true;

  const now = new Date();
  const sixHours = 6 * 60 * 60 * 1000;
  return now.getTime() - lastRun.getTime() >= sixHours;
}

// Track last run times
let lastSchedulerRun: Date | null = null;
let lastMissingDataRun: Date | null = null;

// Run the missing data detector immediately on startup
logger.info("Running initial missing data detection...");
getMissingDataDetector().run().then((result) => {
  logger.info(
    `Initial missing data detection: ${result.jobsEnqueued} jobs enqueued`,
    {
      jobsEnqueued: result.jobsEnqueued,
    },
  );
  lastMissingDataRun = new Date();
}).catch((error) => {
  logger.error("Initial missing data detection failed", {
    error: error.message,
    stack: error.stack,
  });
});

// Run all schedulers immediately on startup
logger.info(
  "Running initial scheduler check (Bricklink, Reddit, WorldBricks)...",
);
getScheduler().runAll().then((result) => {
  const totalJobsEnqueued = result.bricklink.jobsEnqueued +
    result.reddit.jobsEnqueued +
    result.worldbricks.jobsEnqueued;
  const allErrors = [
    ...result.bricklink.errors,
    ...result.reddit.errors,
    ...result.worldbricks.errors,
  ];

  logger.info(
    `Initial scheduler run complete: ${totalJobsEnqueued} jobs enqueued, ${allErrors.length} errors`,
    {
      jobsEnqueued: totalJobsEnqueued,
      errorCount: allErrors.length,
      breakdown: {
        bricklink: result.bricklink.jobsEnqueued,
        reddit: result.reddit.jobsEnqueued,
        worldbricks: result.worldbricks.jobsEnqueued,
      },
    },
  );
  lastSchedulerRun = new Date();
}).catch((error) => {
  logger.error("Initial scheduler run failed", {
    error: error.message,
    stack: error.stack,
  });
});

// Set up periodic checks (every hour)
setInterval(async () => {
  // Check if daily scheduler should run (at 2 AM)
  if (shouldRunDailyScheduler(lastSchedulerRun)) {
    logger.info("Running daily schedulers (Bricklink, Reddit, WorldBricks)...");
    try {
      const scheduler = getScheduler();
      const result = await scheduler.runAll();

      const totalJobsEnqueued = result.bricklink.jobsEnqueued +
        result.reddit.jobsEnqueued +
        result.worldbricks.jobsEnqueued;
      const allErrors = [
        ...result.bricklink.errors,
        ...result.reddit.errors,
        ...result.worldbricks.errors,
      ];

      logger.info(
        `All schedulers completed: ${totalJobsEnqueued} jobs enqueued, ${allErrors.length} errors`,
        {
          jobsEnqueued: totalJobsEnqueued,
          errorCount: allErrors.length,
          breakdown: {
            bricklink: result.bricklink.jobsEnqueued,
            reddit: result.reddit.jobsEnqueued,
            worldbricks: result.worldbricks.jobsEnqueued,
          },
        },
      );
      lastSchedulerRun = new Date();
    } catch (error) {
      logger.error("Schedulers failed", {
        error: error.message,
        stack: error.stack,
      });
    }
  }

  // Check if missing data detector should run (every 6 hours)
  if (shouldRunMissingDataDetector(lastMissingDataRun)) {
    logger.info("Running missing data detector...");
    try {
      const detector = getMissingDataDetector();
      const result = await detector.run();
      logger.info(
        `Missing data detection completed: ${result.jobsEnqueued} jobs enqueued, ${result.errors.length} errors`,
        {
          jobsEnqueued: result.jobsEnqueued,
          errorCount: result.errors.length,
        },
      );
      lastMissingDataRun = new Date();
    } catch (error) {
      logger.error("Missing data detection failed", {
        error: error.message,
        stack: error.stack,
      });
    }
  }
}, 60 * 60 * 1000); // Check every hour

logger.info("Automatic schedulers configured:");
logger.info(
  "   - Bricklink, Reddit, WorldBricks schedulers: On startup + Daily at 2 AM",
);
logger.info("   - Missing data detector: On startup + Every 6 hours");

await start(manifest, config);
