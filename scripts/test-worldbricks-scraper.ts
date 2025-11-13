/**
 * Test script for WorldBricks scraper
 *
 * Tests the complete scraping workflow:
 * 1. HttpClient fetches the page
 * 2. Parser extracts data
 * 3. Repository saves to database
 * 4. ScraperService orchestrates everything
 */

import {
  closeHttpClient,
  getHttpClient,
} from "../services/http/HttpClientService.ts";
import { RateLimiterService } from "../services/rate-limiter/RateLimiterService.ts";
import { getWorldBricksRepository } from "../services/worldbricks/WorldBricksRepository.ts";
import { WorldBricksScraperService } from "../services/worldbricks/WorldBricksScraperService.ts";

/**
 * Test sets to scrape
 */
const TEST_SETS = [
  {
    setNumber: "31009",
    setName: "Small Cottage",
    url:
      "https://www.worldbricks.com/en/instructions-number/30000/31000-31099/lego-set/31009-Small-Cottage.html",
  },
  // Add more test sets here if needed
];

async function testWorldBricksScraper() {
  console.log("🚀 Starting WorldBricks scraper test...\n");

  const httpClient = getHttpClient();
  const rateLimiter = new RateLimiterService();
  const repository = getWorldBricksRepository();
  const scraperService = new WorldBricksScraperService(
    httpClient,
    rateLimiter,
    repository,
  );

  try {
    // Initialize HTTP client
    await httpClient.initialize();

    console.log("=".repeat(60));
    console.log("TEST 1: Scrape WITHOUT saving to database");
    console.log("=".repeat(60));

    const result1 = await scraperService.scrape({
      setNumber: TEST_SETS[0].setNumber,
      setName: TEST_SETS[0].setName,
      url: TEST_SETS[0].url,
      saveToDb: false, // Don't save yet
      skipRateLimit: true, // Skip rate limiting for testing
    });

    if (result1.success && result1.data) {
      console.log("\n✅ Scraping successful!");
      console.log("\nExtracted Data:");
      console.log("-".repeat(60));
      console.log(`Set Number:     ${result1.data.set_number}`);
      console.log(`Set Name:       ${result1.data.set_name}`);
      console.log(
        `Year Released:  ${result1.data.year_released || "Not found"}`,
      );
      console.log(
        `Year Retired:   ${result1.data.year_retired || "Not found"}`,
      );
      console.log(`Parts Count:    ${result1.data.parts_count || "Not found"}`);
      console.log(`Designer:       ${result1.data.designer || "Not found"}`);
      console.log(`Dimensions:     ${result1.data.dimensions || "Not found"}`);
      console.log(
        `Image URL:      ${result1.data.image_url ? "Found" : "Not found"}`,
      );
      console.log(
        `Description:    ${
          result1.data.description
            ? result1.data.description.substring(0, 100) + "..."
            : "Not found"
        }`,
      );
      console.log("-".repeat(60));
    } else {
      console.error("\n❌ Scraping failed:", result1.error);
      return;
    }

    console.log("\n" + "=".repeat(60));
    console.log("TEST 2: Scrape WITH saving to database");
    console.log("=".repeat(60));

    const result2 = await scraperService.scrape({
      setNumber: TEST_SETS[0].setNumber,
      setName: TEST_SETS[0].setName,
      url: TEST_SETS[0].url,
      saveToDb: true, // Save to database
      skipRateLimit: true,
    });

    if (result2.success && result2.saved) {
      console.log("\n✅ Successfully saved to database!");

      // Verify it was saved
      const savedSet = await repository.findBySetNumber(TEST_SETS[0].setNumber);
      if (savedSet) {
        console.log("\n✅ Verified: Set found in database");
        console.log(`   Database ID: ${savedSet.id}`);
        console.log(`   Created At:  ${savedSet.createdAt}`);
        console.log(`   Updated At:  ${savedSet.updatedAt}`);
      } else {
        console.error("\n❌ Error: Set not found in database after save");
      }
    } else {
      console.error("\n❌ Failed to save to database:", result2.error);
    }

    console.log("\n" + "=".repeat(60));
    console.log("TEST 3: Repository statistics");
    console.log("=".repeat(60));

    const stats = await repository.getStats();
    console.log("\nDatabase Statistics:");
    console.log(`  Total Sets:               ${stats.total}`);
    console.log(`  With Year Released:       ${stats.withYearReleased}`);
    console.log(`  With Year Retired:        ${stats.withYearRetired}`);
    console.log(`  With Parts Count:         ${stats.withPartsCount}`);
    console.log(`  With Downloaded Images:   ${stats.withImages}`);
    console.log(`  Failed Scrapes:           ${stats.failedScrapes}`);

    console.log("\n" + "=".repeat(60));
    console.log("TEST 4: URL construction test");
    console.log("=".repeat(60));

    const { constructWorldBricksUrl } = await import(
      "../services/worldbricks/WorldBricksParser.ts"
    );

    const testCases = [
      { setNumber: "31009", setName: "Small Cottage" },
      { setNumber: "10307", setName: "Eiffel Tower" },
      { setNumber: "75192", setName: "Millennium Falcon" },
    ];

    for (const testCase of testCases) {
      const url = constructWorldBricksUrl(testCase.setNumber, testCase.setName);
      console.log(`\nSet ${testCase.setNumber} (${testCase.setName}):`);
      console.log(`  ${url}`);
    }

    console.log("\n" + "=".repeat(60));
    console.log("✅ All tests completed successfully!");
    console.log("=".repeat(60));
  } catch (error) {
    console.error("\n❌ Test failed with error:", error);
    throw error;
  } finally {
    // Cleanup
    await closeHttpClient();
    console.log("\n🔒 Test cleanup complete");
  }
}

// Run tests if this is the main module
if (import.meta.main) {
  testWorldBricksScraper().catch((error) => {
    console.error("Fatal error:", error);
    Deno.exit(1);
  });
}
