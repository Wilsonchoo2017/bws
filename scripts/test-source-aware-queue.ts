/**
 * Test script for source-aware queue implementation
 *
 * This script tests that:
 * 1. Jobs from different sources can run in parallel
 * 2. Workers skip locked sources and try next available job
 * 3. Source distribution is tracked correctly
 */

import { getQueueService } from "../services/queue/init.ts";
import { JobPriority } from "../services/queue/QueueService.ts";

const queueService = getQueueService();

async function testSourceAwareQueue() {
  console.log("🧪 Testing Source-Aware Queue Implementation\n");

  // Initialize queue
  console.log("1️⃣ Initializing queue service...");
  await queueService.initialize();
  console.log("✅ Queue initialized\n");

  // Check initial lock status
  console.log("2️⃣ Checking initial lock status...");
  const initialLocks = await queueService.getSourceLockStatus();
  console.log("Lock Status:", initialLocks);
  console.log("");

  // Add mixed jobs from different sources
  console.log("3️⃣ Adding mixed jobs from different sources...");

  // Add 3 BrickLink jobs
  await queueService.addScrapeJob({
    url: "https://www.bricklink.com/v2/catalog/catalogitem.page?S=10497-1",
    itemId: "10497-1",
    priority: JobPriority.NORMAL,
    saveToDb: false,
  });
  console.log("✅ Added BrickLink job 1 (10497-1)");

  await queueService.addScrapeJob({
    url: "https://www.bricklink.com/v2/catalog/catalogitem.page?S=10181-1",
    itemId: "10181-1",
    priority: JobPriority.NORMAL,
    saveToDb: false,
  });
  console.log("✅ Added BrickLink job 2 (10181-1)");

  await queueService.addScrapeJob({
    url: "https://www.bricklink.com/v2/catalog/catalogitem.page?S=10030-1",
    itemId: "10030-1",
    priority: JobPriority.NORMAL,
    saveToDb: false,
  });
  console.log("✅ Added BrickLink job 3 (10030-1)");

  // Add 2 WorldBricks jobs
  await queueService.addWorldBricksJob({
    setNumber: "10497-1",
    priority: JobPriority.NORMAL,
    saveToDb: false,
  });
  console.log("✅ Added WorldBricks job 1 (10497-1)");

  await queueService.addWorldBricksJob({
    setNumber: "10181-1",
    priority: JobPriority.NORMAL,
    saveToDb: false,
  });
  console.log("✅ Added WorldBricks job 2 (10181-1)");

  // Add 1 Reddit job
  await queueService.addRedditSearchJob({
    setNumber: "10497-1",
    priority: JobPriority.NORMAL,
    saveToDb: false,
  });
  console.log("✅ Added Reddit job 1 (10497-1)\n");

  // Wait a moment for jobs to be added
  await new Promise(resolve => setTimeout(resolve, 1000));

  // Check source distribution
  console.log("4️⃣ Checking source distribution in queue...");
  const distribution = await queueService.getSourceDistribution();
  console.log("Source Distribution:", distribution);
  console.log("");

  // Monitor queue for 30 seconds
  console.log("5️⃣ Monitoring queue for 30 seconds...");
  console.log("Watch for:");
  console.log("  - Jobs from different sources starting in parallel");
  console.log("  - Workers skipping locked sources");
  console.log("  - Lock status changes\n");

  for (let i = 0; i < 6; i++) {
    await new Promise(resolve => setTimeout(resolve, 5000));

    const counts = await queueService.getJobCounts();
    const locks = await queueService.getSourceLockStatus();

    console.log(`⏱️  T+${(i + 1) * 5}s:`);
    console.log(`   Waiting: ${counts.waiting} | Active: ${counts.active} | Delayed: ${counts.delayed} | Completed: ${counts.completed}`);
    console.log(`   Locks: BL=${locks.bricklink.locked ? '🔒' : '🔓'} WB=${locks.worldbricks.locked ? '🔒' : '🔓'} RD=${locks.reddit.locked ? '🔒' : '🔓'}`);
  }

  // Final statistics
  console.log("\n6️⃣ Final Statistics:");
  const finalCounts = await queueService.getJobCounts();
  console.log("Final Counts:", finalCounts);

  const finalLocks = await queueService.getSourceLockStatus();
  console.log("Final Locks:", finalLocks);

  console.log("\n✅ Test complete!");
  console.log("\n💡 Expected behavior:");
  console.log("   - Workers should process jobs from different sources in parallel");
  console.log("   - When a source is locked, workers should skip to next available source");
  console.log("   - Locked source jobs should be delayed and retried later");
  console.log("   - No worker should waste time polling for locks");
}

// Run test
testSourceAwareQueue()
  .catch(console.error);
