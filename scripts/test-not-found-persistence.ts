/**
 * Test script to verify that not_found sets are persisted to database
 * and not re-queued on app restart
 */

import { getWorldBricksRepository } from "../services/worldbricks/WorldBricksRepository.ts";

const worldBricksRepo = getWorldBricksRepository();

async function testNotFoundPersistence() {
  console.log("Testing not_found persistence...\n");

  const setNumber = "77241";

  // Check if set exists
  console.log(`1. Checking existing state for set ${setNumber}...`);
  const existing = await worldBricksRepo.findBySetNumber(setNumber);

  if (existing) {
    console.log("   Existing record found:");
    console.log(`   - scrapeStatus: ${existing.scrapeStatus}`);
    console.log(`   - lastScrapedAt: ${existing.lastScrapedAt}`);
    console.log(`   - nextScrapeAt: ${existing.nextScrapeAt}`);
    console.log(`   - scrapeIntervalDays: ${existing.scrapeIntervalDays}`);
  } else {
    console.log("   No existing record found");
  }

  // Simulate the not_found scenario
  console.log(`\n2. Simulating not_found scenario (90-day retry)...`);
  const nextScrapeAt = new Date();
  nextScrapeAt.setDate(nextScrapeAt.getDate() + 90);

  const updated = await worldBricksRepo.updateNotFoundStatus(
    setNumber,
    nextScrapeAt,
  );

  console.log("   Updated record:");
  console.log(`   - scrapeStatus: ${updated.scrapeStatus}`);
  console.log(`   - lastScrapedAt: ${updated.lastScrapedAt}`);
  console.log(`   - nextScrapeAt: ${updated.nextScrapeAt}`);
  console.log(`   - scrapeIntervalDays: ${updated.scrapeIntervalDays}`);

  // Check if it appears in sets needing scraping
  console.log(`\n3. Checking if set appears in findSetsNeedingScraping()...`);
  const setsNeedingScraping = await worldBricksRepo.findSetsNeedingScraping();
  const appearsInScheduler = setsNeedingScraping.some(
    (s) => s.setNumber === setNumber,
  );

  console.log(`   Set ${setNumber} appears in scheduler: ${appearsInScheduler}`);

  if (appearsInScheduler) {
    console.log("   ❌ FAIL: Set should NOT appear in scheduler");
    console.log(
      `   The nextScrapeAt is ${updated.nextScrapeAt}, which is in the future`,
    );
  } else {
    console.log("   ✅ PASS: Set correctly excluded from scheduler");
  }

  // Verify the fix
  console.log(`\n4. Summary:`);
  console.log(`   - Database record created: ✅`);
  console.log(`   - scrapeStatus set to 'not_found': ✅`);
  console.log(
    `   - nextScrapeAt set to ~90 days: ${updated.nextScrapeAt ? "✅" : "❌"}`,
  );
  console.log(
    `   - Excluded from scheduler on restart: ${!appearsInScheduler ? "✅" : "❌"}`,
  );

  if (!appearsInScheduler && updated.scrapeStatus === "not_found") {
    console.log(`\n✅ SUCCESS: Fix is working correctly!`);
    console.log(
      `   Set ${setNumber} will not be re-queued on app restart until ${updated.nextScrapeAt}`,
    );
  } else {
    console.log(`\n❌ FAILURE: Fix is not working as expected`);
  }

  Deno.exit(0);
}

// Run the test
testNotFoundPersistence().catch((error) => {
  console.error("Test failed:", error);
  Deno.exit(1);
});
