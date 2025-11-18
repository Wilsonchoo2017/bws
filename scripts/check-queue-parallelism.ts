#!/usr/bin/env -S deno run --allow-net --allow-env --allow-read

/**
 * Diagnostic script to check queue parallelism
 *
 * This script:
 * 1. Checks current Redis locks
 * 2. Enqueues test jobs from different sources
 * 3. Monitors parallel execution
 *
 * Usage:
 *   deno run --allow-net --allow-env --allow-read scripts/check-queue-parallelism.ts
 */

import { Redis } from "ioredis";
import { QUEUE_CONFIG, REDIS_CONFIG } from "../config/scraper.config.ts";
import "jsr:@std/dotenv/load";

async function checkRedisLocks() {
  console.log("🔍 Checking current Redis locks...\n");

  const client = new Redis(REDIS_CONFIG);

  try {
    // Check for all lock keys
    const lockKeys = [
      "bricklink:scrape:lock",
      "worldbricks:scrape:lock",
      "reddit:scrape:lock",
    ];

    for (const key of lockKeys) {
      const exists = await client.exists(key);
      const ttl = exists ? await client.ttl(key) : -1;

      if (exists) {
        console.log(`🔒 ${key}: LOCKED (TTL: ${ttl}s)`);
      } else {
        console.log(`🔓 ${key}: UNLOCKED`);
      }
    }

    console.log("\n");
  } finally {
    client.disconnect();
  }
}

async function checkActiveJobs() {
  console.log("📊 Checking active jobs in queue...\n");

  const client = new Redis(REDIS_CONFIG);

  try {
    // Check BullMQ queue keys
    const queueName = QUEUE_CONFIG.QUEUE_NAME;

    // Get active jobs
    const activeKey = `bull:${queueName}:active`;
    const activeJobs = await client.lrange(activeKey, 0, -1);

    console.log(`Active jobs: ${activeJobs.length}`);

    if (activeJobs.length > 0) {
      console.log("\nActive job IDs:");
      for (const jobData of activeJobs) {
        try {
          const parsed = JSON.parse(jobData);
          console.log(`  - Job ID: ${parsed.id}, Type: ${parsed.name}`);
        } catch {
          console.log(`  - ${jobData.substring(0, 50)}...`);
        }
      }
    }

    // Get waiting jobs count
    const waitingKey = `bull:${queueName}:wait`;
    const waitingCount = await client.llen(waitingKey);
    console.log(`\nWaiting jobs: ${waitingCount}`);

    // Get delayed jobs count
    const delayedKey = `bull:${queueName}:delayed`;
    const delayedCount = await client.zcard(delayedKey);
    console.log(`Delayed jobs: ${delayedCount}`);

    console.log("\n");
  } finally {
    client.disconnect();
  }
}

// deno-lint-ignore require-await
async function monitorLogs() {
  console.log("📝 Monitor your application logs to see parallel execution patterns\n");
  console.log("Look for these log patterns:\n");
  console.log("  🚀 Job X is now active (STARTED) - shows when jobs start");
  console.log("  🔒 Acquired [source] scraping lock - shows lock acquisition");
  console.log("  ⏳ Waiting for [source] lock - shows lock contention");
  console.log("  🔓 Released [source] scraping lock - shows lock release");
  console.log("  ✅ Job X completed successfully (FINISHED) - shows job completion\n");
  console.log("If jobs from different sources run in parallel, you'll see:");
  console.log("  🚀 Job 1 (BrickLink) STARTED");
  console.log("  🔒 Acquired Bricklink lock");
  console.log("  🚀 Job 2 (Reddit) STARTED     ← Running in parallel!");
  console.log("  🔒 Acquired Reddit lock       ← Different lock, no waiting");
  console.log("  🚀 Job 3 (WorldBricks) STARTED ← Also in parallel!");
  console.log("  🔒 Acquired WorldBricks lock   ← Different lock\n");
  console.log("If jobs from the SAME source don't run in parallel:");
  console.log("  🚀 Job 1 (BrickLink) STARTED");
  console.log("  🔒 Acquired Bricklink lock");
  console.log("  🚀 Job 2 (BrickLink) STARTED");
  console.log("  ⏳ Waiting for Bricklink lock  ← Job 2 waits for Job 1\n");
}

// Main execution
console.log("=== Queue Parallelism Diagnostic Tool ===\n");

await checkRedisLocks();
await checkActiveJobs();
await monitorLogs();

console.log("💡 Recommendations:\n");
console.log("1. Check your application logs while jobs are running");
console.log("2. Look for timestamps on 'STARTED' logs - if close together, they're parallel");
console.log("3. Use the queue dashboard UI to visually see active jobs");
console.log("4. Run this script periodically while processing jobs\n");
