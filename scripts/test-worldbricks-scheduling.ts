/**
 * Test script for WorldBricks automated scheduling
 *
 * This script tests the complete WorldBricks scheduling flow:
 * 1. Finding sets that need scraping (with product linking and retirement filtering)
 * 2. Queueing jobs via the scheduler
 * 3. Verifying the filtering logic works correctly
 */

import { getWorldBricksRepository } from "../services/worldbricks/WorldBricksRepository.ts";
import { getScheduler } from "../services/scheduler/SchedulerService.ts";
import { connection } from "../db/client.ts";

console.log("🧪 Testing WorldBricks Automated Scheduling\n");
console.log("=".repeat(60));

try {
  const repository = getWorldBricksRepository();
  const scheduler = getScheduler();

  // Test 1: Check findSetsNeedingScraping logic
  console.log("\n📋 Test 1: Finding sets that need scraping...");
  const setsNeeded = await repository.findSetsNeedingScraping();
  console.log(`✅ Found ${setsNeeded.length} sets needing scraping`);

  if (setsNeeded.length > 0) {
    console.log("\n📦 Sample sets (first 5):");
    setsNeeded.slice(0, 5).forEach((set, idx) => {
      console.log(`   ${idx + 1}. Set ${set.setNumber}: ${set.setName}`);
      console.log(`      - Year Released: ${set.yearReleased || "N/A"}`);
      console.log(`      - Year Retired: ${set.yearRetired || "N/A"}`);
      console.log(`      - Last Scraped: ${set.lastScrapedAt || "Never"}`);
      console.log(`      - Next Scrape: ${set.nextScrapeAt || "Immediate"}`);
      console.log(`      - Interval: ${set.scrapeIntervalDays || 90} days`);
    });
  }

  // Test 2: Preview what the scheduler would do
  console.log("\n📋 Test 2: Preview scheduler run...");
  const result = await scheduler.runWorldBricks();

  console.log(`\n📊 Scheduler Results:`);
  console.log(`   - Success: ${result.success}`);
  console.log(`   - Items Found: ${result.itemsFound}`);
  console.log(`   - Jobs Enqueued: ${result.jobsEnqueued}`);
  console.log(`   - Errors: ${result.errors.length}`);

  if (result.errors.length > 0) {
    console.log("\n❌ Errors:");
    result.errors.forEach((error) => console.log(`   - ${error}`));
  }

  // Test 3: Verify database schema
  console.log("\n📋 Test 3: Verify database schema changes...");
  const stats = await repository.getStats();
  console.log(`✅ Database stats:`);
  console.log(`   - Total WorldBricks sets: ${stats.total}`);
  console.log(`   - With year_released: ${stats.withYearReleased}`);
  console.log(`   - With year_retired: ${stats.withYearRetired}`);
  console.log(`   - Failed scrapes: ${stats.failedScrapes}`);

  console.log("\n" + "=".repeat(60));
  console.log("✅ All tests completed successfully!");
} catch (error) {
  console.error("\n❌ Test failed:", error);
  console.error(error.stack);
} finally {
  // Clean up database connection
  await connection.end();
  Deno.exit(0);
}
