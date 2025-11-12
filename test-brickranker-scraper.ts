/**
 * Test script for BrickRanker retirement tracker scraper
 *
 * Run with: deno run --allow-all test-brickranker-scraper.ts
 */

import { getHttpClient } from "./services/http/HttpClientService.ts";
import { getRateLimiter } from "./services/rate-limiter/RateLimiterService.ts";
import { getBrickRankerRepository } from "./services/brickranker/BrickRankerRepository.ts";
import { createBrickRankerScraperService } from "./services/brickranker/BrickRankerScraperService.ts";

async function main() {
  console.log("🚀 Testing BrickRanker Retirement Tracker Scraper\n");

  try {
    // Create service dependencies
    const httpClient = getHttpClient();
    const rateLimiter = getRateLimiter();
    const repository = getBrickRankerRepository();

    // Create scraper service
    const scraper = createBrickRankerScraperService(
      httpClient,
      rateLimiter,
      repository,
    );

    console.log("📥 Starting scrape (without saving to database)...\n");

    // Test scrape without saving to DB first
    const result = await scraper.scrape({
      saveToDb: false,
      skipRateLimit: true, // Skip rate limiting for testing
    });

    if (result.success && result.data) {
      console.log("\n✅ Scrape successful!");
      console.log(`📊 Total items found: ${result.data.totalItems}`);
      console.log(`🎨 Themes found: ${result.data.themes.join(", ")}`);
      console.log(`🔄 Retries: ${result.retries || 0}\n`);

      // Show sample items from each theme
      const itemsByTheme = new Map<string, number>();
      for (const item of result.data.items) {
        itemsByTheme.set(item.theme, (itemsByTheme.get(item.theme) || 0) + 1);
      }

      console.log("📋 Items per theme:");
      for (const [theme, count] of itemsByTheme) {
        console.log(`  - ${theme}: ${count} items`);
      }

      // Show first 5 items as examples
      console.log("\n🔍 Sample items (first 5):");
      for (let i = 0; i < Math.min(5, result.data.items.length); i++) {
        const item = result.data.items[i];
        console.log(`  ${i + 1}. [${item.setNumber}] ${item.setName}`);
        console.log(`     Theme: ${item.theme}`);
        console.log(`     Year: ${item.yearReleased || "N/A"}`);
        console.log(`     Retiring Soon: ${item.retiringSoon ? "Yes" : "No"}`);
        console.log(
          `     Expected Retirement: ${item.expectedRetirementDate || "N/A"}`,
        );
        console.log();
      }

      // Ask if user wants to save to database
      console.log("💾 Do you want to save these items to the database? (y/n)");
      console.log(
        "   Note: This will create/update records in brickranker_retirement_items table",
      );
      console.log("   Press Ctrl+C to exit without saving\n");

      // Wait for user input (simple version - just proceed for now in automated test)
      console.log("   Skipping database save in automated test mode.");
      console.log("   To save to database, use: scraper.scrapeAndSave()");
    } else {
      console.log("\n❌ Scrape failed!");
      console.log(`Error: ${result.error}`);
      console.log(`Retries: ${result.retries || 0}`);
    }

    // Close resources
    await scraper.close();
    console.log("\n✅ Test complete!");
  } catch (error) {
    console.error("\n❌ Test failed with error:", error);
    throw error;
  }
}

// Run the test
if (import.meta.main) {
  main().catch((error) => {
    console.error("Fatal error:", error);
    Deno.exit(1);
  });
}
