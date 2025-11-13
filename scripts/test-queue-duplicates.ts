/**
 * Test Queue Duplicate Prevention
 *
 * This script tests that the queue service properly prevents duplicate jobs
 * from being added to the queue.
 *
 * Usage:
 *   deno run -A scripts/test-queue-duplicates.ts
 */

import { getQueueService, JobPriority } from "../services/queue/QueueService.ts";

// ANSI color codes
const colors = {
  reset: "\x1b[0m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  cyan: "\x1b[36m",
};

async function main() {
  console.log(`${colors.cyan}🧪 Testing Queue Duplicate Prevention${colors.reset}\n`);

  const queueService = getQueueService();

  // Initialize queue
  try {
    await queueService.initialize();
    console.log(`${colors.green}✓${colors.reset} Queue initialized\n`);
  } catch (error) {
    console.error(`${colors.red}✗ Failed to initialize queue:${colors.reset}`, error);
    Deno.exit(1);
  }

  // Test 1: Try adding the same job twice (HIGH priority)
  console.log(`${colors.blue}Test 1: Adding same HIGH priority job twice${colors.reset}`);

  const testItemId = "10332-1";
  const testUrl = `https://www.bricklink.com/v2/catalog/catalogitem.page?S=${testItemId}`;

  try {
    const job1 = await queueService.addScrapeJob({
      url: testUrl,
      itemId: testItemId,
      saveToDb: true,
      priority: JobPriority.HIGH,
    });
    console.log(`${colors.green}✓${colors.reset} First job added: ${job1.id}`);

    // Try to add the same job again
    const job2 = await queueService.addScrapeJob({
      url: testUrl,
      itemId: testItemId,
      saveToDb: true,
      priority: JobPriority.HIGH,
    });

    if (job1.id === job2.id) {
      console.log(`${colors.green}✓${colors.reset} Duplicate detected - returned existing job: ${job2.id}`);
    } else {
      console.log(`${colors.red}✗${colors.reset} FAIL: Different job IDs - duplicate was not prevented!`);
      console.log(`  Job 1: ${job1.id}`);
      console.log(`  Job 2: ${job2.id}`);
    }
  } catch (error) {
    console.log(`${colors.red}✗${colors.reset} Test failed: ${error.message}`);
  }

  console.log();

  // Test 2: Try adding multiple jobs in bulk
  console.log(`${colors.blue}Test 2: Adding bulk jobs (some duplicates)${colors.reset}`);

  const bulkJobs = [
    { url: "https://www.bricklink.com/v2/catalog/catalogitem.page?S=10123-1", itemId: "10123-1", saveToDb: true, priority: JobPriority.MEDIUM },
    { url: "https://www.bricklink.com/v2/catalog/catalogitem.page?S=10124-1", itemId: "10124-1", saveToDb: true, priority: JobPriority.MEDIUM },
    { url: "https://www.bricklink.com/v2/catalog/catalogitem.page?S=10123-1", itemId: "10123-1", saveToDb: true, priority: JobPriority.MEDIUM }, // Duplicate
  ];

  try {
    const addedJobs = await queueService.addScrapeJobsBulk(bulkJobs);
    console.log(`${colors.green}✓${colors.reset} Added ${addedJobs.length} jobs (expected 2, got ${addedJobs.length})`);

    if (addedJobs.length === 2) {
      console.log(`${colors.green}✓${colors.reset} Duplicate filtering worked correctly`);
    } else {
      console.log(`${colors.yellow}⚠${colors.reset} Expected 2 jobs but got ${addedJobs.length}`);
    }
  } catch (error) {
    console.log(`${colors.red}✗${colors.reset} Test failed: ${error.message}`);
  }

  console.log();

  // Test 3: Check final queue status
  console.log(`${colors.blue}Test 3: Final Queue Status${colors.reset}`);
  const counts = await queueService.getJobCounts();
  console.log(`   Waiting:   ${colors.yellow}${counts.waiting || 0}${colors.reset}`);
  console.log(`   Active:    ${colors.cyan}${counts.active || 0}${colors.reset}`);
  console.log(`   Completed: ${colors.green}${counts.completed || 0}${colors.reset}`);
  console.log(`   Failed:    ${colors.red}${counts.failed || 0}${colors.reset}`);
  console.log(`   Delayed:   ${colors.yellow}${counts.delayed || 0}${colors.reset}`);

  console.log();
  console.log(`${colors.green}✓ Tests complete!${colors.reset}`);

  // Clean up test jobs
  console.log(`\n${colors.yellow}Cleaning up test jobs...${colors.reset}`);
  await queueService.cleanOldJobs();

  // Shutdown
  await queueService.shutdown();
  console.log(`${colors.green}✓ Queue shutdown complete${colors.reset}`);
}

// Run the script
main().catch(console.error);
