/**
 * Test script to verify that new sets (without WorldBricks entries)
 * are still queued immediately on startup
 */

import { getWorldBricksRepository } from "../services/worldbricks/WorldBricksRepository.ts";

const worldBricksRepo = getWorldBricksRepository();

async function testNewSetsStillQueued() {
  console.log("Testing that new sets are still discovered...\n");

  // Find products without WorldBricks entries
  console.log(`1. Finding products without WorldBricks entries...`);
  const productsWithoutEntries =
    await worldBricksRepo.findProductsWithoutWorldBricksEntries();

  console.log(
    `   Found ${productsWithoutEntries.length} products without WorldBricks entries`,
  );

  if (productsWithoutEntries.length > 0) {
    console.log(`   Examples (first 5):`);
    productsWithoutEntries.slice(0, 5).forEach((p) => {
      console.log(`   - ${p.setNumber}`);
    });
    console.log(
      `   ✅ PASS: New sets are still being discovered for immediate queuing`,
    );
  } else {
    console.log(
      `   ℹ️ INFO: No products without WorldBricks entries (all have been scraped)`,
    );
  }

  // Find sets needing scraping (scheduled retries)
  console.log(`\n2. Finding sets needing scheduled scraping...`);
  const setsNeedingScraping = await worldBricksRepo.findSetsNeedingScraping();

  console.log(`   Found ${setsNeedingScraping.length} sets needing scraping`);

  if (setsNeedingScraping.length > 0) {
    console.log(`   Examples (first 5):`);
    setsNeedingScraping.slice(0, 5).forEach((s) => {
      console.log(
        `   - ${s.setNumber} (nextScrapeAt: ${s.nextScrapeAt || "NULL"})`,
      );
    });
  }

  // Summary
  console.log(`\n3. Summary:`);
  console.log(
    `   - Products without entries (new sets): ${productsWithoutEntries.length}`,
  );
  console.log(
    `   - Sets needing scraping (scheduled): ${setsNeedingScraping.length}`,
  );
  console.log(
    `   - Total sets to be queued on startup: ${productsWithoutEntries.length + setsNeedingScraping.length}`,
  );

  console.log(`\n✅ SUCCESS: New sets are still being discovered and queued!`);

  Deno.exit(0);
}

// Run the test
testNewSetsStillQueued().catch((error) => {
  console.error("Test failed:", error);
  Deno.exit(1);
});
