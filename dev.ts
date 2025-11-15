#!/usr/bin/env -S deno run -A --watch=static/,routes/

import dev from "$fresh/dev.ts";
import config from "./fresh.config.ts";

import { load } from "$std/dotenv/mod.ts";
import { initializeQueue } from "./services/queue/init.ts";
import { getScheduler } from "./services/scheduler/SchedulerService.ts";
import { getMissingDataDetector } from "./services/missing-data/MissingDataDetectorService.ts";

// Load environment variables with allowEmptyValues
await load({ export: true, allowEmptyValues: true });

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
console.log("🔍 Running initial missing data detection...");
getMissingDataDetector().run().then((result) => {
  console.log(
    `✅ Initial missing data detection: ${result.jobsEnqueued} jobs enqueued`,
  );
  lastMissingDataRun = new Date();
}).catch((error) => {
  console.error("❌ Initial missing data detection failed:", error);
});

// Set up periodic checks (every hour)
setInterval(async () => {
  // Check if daily scheduler should run (at 2 AM)
  if (shouldRunDailyScheduler(lastSchedulerRun)) {
    console.log("🕐 Running daily Bricklink scheduler...");
    try {
      const scheduler = getScheduler();
      const result = await scheduler.run();
      console.log(
        `✅ Scheduler completed: ${result.jobsEnqueued} jobs enqueued, ${result.errors.length} errors`,
      );
      lastSchedulerRun = new Date();
    } catch (error) {
      console.error("❌ Scheduler failed:", error);
    }
  }

  // Check if missing data detector should run (every 6 hours)
  if (shouldRunMissingDataDetector(lastMissingDataRun)) {
    console.log("🔍 Running missing data detector...");
    try {
      const detector = getMissingDataDetector();
      const result = await detector.run();
      console.log(
        `✅ Missing data detection completed: ${result.jobsEnqueued} jobs enqueued, ${result.errors.length} errors`,
      );
      lastMissingDataRun = new Date();
    } catch (error) {
      console.error("❌ Missing data detection failed:", error);
    }
  }
}, 60 * 60 * 1000); // Check every hour

console.log("✅ Automatic schedulers configured:");
console.log("   - Bricklink scheduler: Daily at 2 AM");
console.log("   - Missing data detector: Every 6 hours");

await dev(import.meta.url, "./main.ts", config);
