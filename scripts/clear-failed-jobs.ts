/**
 * Script to clear failed/stalled jobs from the BullMQ queue
 * Run this script after updating the LOCK_DURATION configuration
 */

import { load } from "$std/dotenv/mod.ts";
import { Queue } from "bullmq";
import { Redis } from "ioredis";
import { QUEUE_CONFIG, REDIS_CONFIG } from "../config/scraper.config.ts";

// Load environment variables with allowEmptyValues
await load({ export: true, allowEmptyValues: true });

async function clearFailedJobs() {
  console.log("🧹 Clearing failed/stalled jobs from queue...\n");

  const connection = new Redis({
    host: REDIS_CONFIG.HOST,
    port: REDIS_CONFIG.PORT,
    password: REDIS_CONFIG.PASSWORD,
    db: REDIS_CONFIG.DB,
    maxRetriesPerRequest: REDIS_CONFIG.MAX_RETRIES_PER_REQUEST,
  });

  try {
    // Test connection
    await connection.ping();
    console.log("✅ Connected to Redis\n");

    const queue = new Queue(QUEUE_CONFIG.QUEUE_NAME, {
      connection,
    });

    // Get counts before cleanup
    const failedCount = await queue.getFailedCount();
    const activeCount = await queue.getActiveCount();
    const waitingCount = await queue.getWaitingCount();
    const delayedCount = await queue.getDelayedCount();

    console.log("📊 Queue status before cleanup:");
    console.log(`   - Failed jobs: ${failedCount}`);
    console.log(`   - Active jobs: ${activeCount}`);
    console.log(`   - Waiting jobs: ${waitingCount}`);
    console.log(`   - Delayed jobs: ${delayedCount}\n`);

    // Clean failed jobs
    if (failedCount > 0) {
      console.log(`🗑️  Cleaning ${failedCount} failed jobs...`);
      await queue.clean(0, 1000, "failed");
      console.log("✅ Failed jobs cleaned\n");
    }

    // Clean stalled jobs (if any are in active state but actually stalled)
    // This will move stalled jobs back to waiting or failed
    if (activeCount > 0) {
      console.log("🔍 Checking for stalled jobs in active state...");
      const activeJobs = await queue.getActive();
      console.log(`   Found ${activeJobs.length} active jobs`);

      // List active jobs
      if (activeJobs.length > 0) {
        console.log("\n   Active jobs:");
        for (const job of activeJobs) {
          console.log(
            `   - Job ${job.id}: ${job.name} (item: ${
              job.data.itemId || "N/A"
            })`,
          );
        }
        console.log("\n   Note: These jobs may be legitimately processing.");
        console.log(
          "   If they're stuck, they'll be marked as stalled by the worker.\n",
        );
      }
    }

    // Get counts after cleanup
    const failedCountAfter = await queue.getFailedCount();
    const activeCountAfter = await queue.getActiveCount();
    const waitingCountAfter = await queue.getWaitingCount();
    const delayedCountAfter = await queue.getDelayedCount();

    console.log("📊 Queue status after cleanup:");
    console.log(`   - Failed jobs: ${failedCountAfter}`);
    console.log(`   - Active jobs: ${activeCountAfter}`);
    console.log(`   - Waiting jobs: ${waitingCountAfter}`);
    console.log(`   - Delayed jobs: ${delayedCountAfter}\n`);

    console.log("✅ Queue cleanup completed!");
    console.log("\n💡 Next steps:");
    console.log(
      "   1. Restart your application to apply the new LOCK_DURATION",
    );
    console.log(
      "   2. Monitor the /queue page to ensure jobs complete successfully",
    );
    console.log(
      "   3. Check logs in ./logs/ directory for detailed job execution info\n",
    );

    await queue.close();
    await connection.quit();
  } catch (error) {
    console.error("❌ Error clearing failed jobs:", error);
    await connection.quit();
    Deno.exit(1);
  }
}

// Run the cleanup
await clearFailedJobs();
