/**
 * Clear Queue Script
 *
 * This script clears jobs from the BullMQ queue.
 *
 * Usage:
 *   deno run -A scripts/clear-queue.ts [--force]
 *
 * Options:
 *   --force    Skip confirmation prompt
 *   - Clears all waiting jobs by default
 *   - Can also clear failed, completed, or ALL jobs
 */

import { Queue } from "bullmq";
import { Redis } from "ioredis";
import { QUEUE_CONFIG, REDIS_CONFIG } from "../config/scraper.config.ts";

// ANSI color codes for pretty output
const colors = {
  reset: "\x1b[0m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  magenta: "\x1b[35m",
  cyan: "\x1b[36m",
};

async function main() {
  const forceMode = Deno.args.includes("--force");
  console.log(`${colors.cyan}🧹 Queue Cleanup Script${colors.reset}\n`);

  // Create Redis connection
  const connection = new Redis({
    host: REDIS_CONFIG.HOST,
    port: REDIS_CONFIG.PORT,
    password: REDIS_CONFIG.PASSWORD,
    db: REDIS_CONFIG.DB,
    maxRetriesPerRequest: REDIS_CONFIG.MAX_RETRIES_PER_REQUEST,
  });

  // Test connection
  try {
    await connection.ping();
    console.log(`${colors.green}✓${colors.reset} Connected to Redis\n`);
  } catch (error) {
    console.error(
      `${colors.red}✗ Failed to connect to Redis:${colors.reset}`,
      error,
    );
    Deno.exit(1);
  }

  // Create queue instance
  const queue = new Queue(QUEUE_CONFIG.QUEUE_NAME, {
    connection,
  });

  try {
    // Get current job counts
    console.log(`${colors.blue}📊 Current Queue Status:${colors.reset}`);
    const beforeCounts = await queue.getJobCounts();
    console.log(`   Waiting:   ${colors.yellow}${beforeCounts.waiting || 0}${colors.reset}`);
    console.log(`   Active:    ${colors.cyan}${beforeCounts.active || 0}${colors.reset}`);
    console.log(`   Completed: ${colors.green}${beforeCounts.completed || 0}${colors.reset}`);
    console.log(`   Failed:    ${colors.red}${beforeCounts.failed || 0}${colors.reset}`);
    console.log(`   Delayed:   ${colors.magenta}${beforeCounts.delayed || 0}${colors.reset}`);
    console.log();

    // Confirm action
    const totalToRemove = (beforeCounts.waiting || 0) +
                          (beforeCounts.failed || 0) +
                          (beforeCounts.completed || 0) +
                          (beforeCounts.delayed || 0);

    if (totalToRemove === 0) {
      console.log(`${colors.green}✓ Queue is already empty!${colors.reset}`);
      await queue.close();
      await connection.quit();
      return;
    }

    console.log(`${colors.yellow}⚠️  Warning: This will remove ${totalToRemove} jobs${colors.reset}`);
    console.log(`${colors.yellow}   (Active jobs will be preserved)${colors.reset}\n`);

    // Prompt for confirmation (unless force mode)
    if (!forceMode) {
      const confirmation = prompt(
        `${colors.red}Are you sure you want to clear the queue? (yes/no):${colors.reset} `,
      );

      if (confirmation?.toLowerCase() !== "yes") {
        console.log(`\n${colors.yellow}✗ Operation cancelled${colors.reset}`);
        await queue.close();
        await connection.quit();
        return;
      }
    } else {
      console.log(`${colors.yellow}🚀 Force mode enabled - skipping confirmation${colors.reset}\n`);
    }

    console.log(`\n${colors.cyan}🧹 Clearing queue...${colors.reset}\n`);

    // Clear different types of jobs
    let totalCleaned = 0;

    // Clear waiting jobs
    if (beforeCounts.waiting && beforeCounts.waiting > 0) {
      console.log(`${colors.yellow}→${colors.reset} Clearing ${beforeCounts.waiting} waiting jobs...`);
      const waitingJobs = await queue.getWaiting(0, beforeCounts.waiting);
      for (const job of waitingJobs) {
        await job.remove();
      }
      totalCleaned += beforeCounts.waiting;
      console.log(`${colors.green}✓${colors.reset} Cleared waiting jobs`);
    }

    // Clear delayed jobs
    if (beforeCounts.delayed && beforeCounts.delayed > 0) {
      console.log(`${colors.yellow}→${colors.reset} Clearing ${beforeCounts.delayed} delayed jobs...`);
      const delayedJobs = await queue.getDelayed(0, beforeCounts.delayed);
      for (const job of delayedJobs) {
        await job.remove();
      }
      totalCleaned += beforeCounts.delayed;
      console.log(`${colors.green}✓${colors.reset} Cleared delayed jobs`);
    }

    // Clean failed jobs (older than 0 seconds, up to 10000 jobs)
    if (beforeCounts.failed && beforeCounts.failed > 0) {
      console.log(`${colors.yellow}→${colors.reset} Cleaning ${beforeCounts.failed} failed jobs...`);
      const failedCleaned = await queue.clean(0, 10000, "failed");
      totalCleaned += failedCleaned.length;
      console.log(`${colors.green}✓${colors.reset} Cleaned ${failedCleaned.length} failed jobs`);
    }

    // Clean completed jobs (older than 0 seconds, up to 10000 jobs)
    if (beforeCounts.completed && beforeCounts.completed > 0) {
      console.log(`${colors.yellow}→${colors.reset} Cleaning ${beforeCounts.completed} completed jobs...`);
      const completedCleaned = await queue.clean(0, 10000, "completed");
      totalCleaned += completedCleaned.length;
      console.log(`${colors.green}✓${colors.reset} Cleaned ${completedCleaned.length} completed jobs`);
    }

    console.log();

    // Get final counts
    const afterCounts = await queue.getJobCounts();
    console.log(`${colors.green}✓ Queue cleaned successfully!${colors.reset}\n`);
    console.log(`${colors.blue}📊 Final Queue Status:${colors.reset}`);
    console.log(`   Waiting:   ${colors.yellow}${afterCounts.waiting || 0}${colors.reset}`);
    console.log(`   Active:    ${colors.cyan}${afterCounts.active || 0}${colors.reset} (preserved)`);
    console.log(`   Completed: ${colors.green}${afterCounts.completed || 0}${colors.reset}`);
    console.log(`   Failed:    ${colors.red}${afterCounts.failed || 0}${colors.reset}`);
    console.log(`   Delayed:   ${colors.magenta}${afterCounts.delayed || 0}${colors.reset}`);
    console.log();
    console.log(`${colors.cyan}📈 Summary:${colors.reset}`);
    console.log(`   Total jobs removed: ${colors.green}${totalCleaned}${colors.reset}`);
    console.log(`   Active jobs preserved: ${colors.cyan}${afterCounts.active || 0}${colors.reset}`);
  } catch (error) {
    console.error(`${colors.red}✗ Error clearing queue:${colors.reset}`, error);
    Deno.exit(1);
  } finally {
    await queue.close();
    await connection.quit();
    console.log(`\n${colors.green}✓ Done!${colors.reset}`);
  }
}

// Run the script
main();
