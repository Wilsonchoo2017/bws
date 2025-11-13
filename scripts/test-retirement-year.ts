/**
 * Test script for WorldBricks retirement year extraction
 * Tests set 7834 (Level Crossing) which should have "1980 - Retired 1982"
 */

import {
  closeHttpClient,
  getHttpClient,
} from "../services/http/HttpClientService.ts";
import { RateLimiterService } from "../services/rate-limiter/RateLimiterService.ts";
import { getWorldBricksRepository } from "../services/worldbricks/WorldBricksRepository.ts";
import { WorldBricksScraperService } from "../services/worldbricks/WorldBricksScraperService.ts";

async function testRetirementYear() {
  const httpClient = getHttpClient();
  const rateLimiter = new RateLimiterService();
  const repository = getWorldBricksRepository();
  const scraper = new WorldBricksScraperService(
    httpClient,
    rateLimiter,
    repository,
  );

  try {
    await httpClient.initialize();

    console.log("🧪 Testing WorldBricks Retirement Year Extraction");
    console.log("=".repeat(70));

    // Test 1: Set with retirement year
    console.log("\nTest 1: Set 7834 (Level Crossing)");
    console.log("Expected: Released 1980, Retired 1982");
    console.log("-".repeat(70));

    const result1 = await scraper.scrape({
      setNumber: "7834",
      saveToDb: true,
      skipRateLimit: true,
    });

    if (result1.success && result1.data) {
      console.log("\n✅ Scraping successful!");
      console.log("\nExtracted Data:");
      console.log(`  Set Number:     ${result1.data.set_number}`);
      console.log(`  Set Name:       ${result1.data.set_name}`);
      console.log(
        `  Year Released:  ${result1.data.year_released || "NOT FOUND ❌"}`,
      );
      console.log(
        `  Year Retired:   ${result1.data.year_retired || "NOT FOUND ❌"}`,
      );
      console.log(
        `  Parts Count:    ${result1.data.parts_count || "NOT FOUND"}`,
      );
      console.log(
        `  Description:    ${
          result1.data.description
            ? result1.data.description.substring(0, 100) + "..."
            : "NOT FOUND"
        }`,
      );

      if (result1.data.year_retired) {
        console.log("\n🎉 SUCCESS: Retirement year extracted correctly!");
      } else {
        console.log("\n⚠️  WARNING: Retirement year not found in data");
      }
    } else {
      console.error("\n❌ Test 1 failed:", result1.error);
    }

    // Test 2: Set without retirement year (modern set)
    console.log("\n" + "=".repeat(70));
    console.log("\nTest 2: Set 31009 (Small Cottage)");
    console.log("Expected: Released 2013, No retirement year");
    console.log("-".repeat(70));

    const result2 = await scraper.scrape({
      setNumber: "31009",
      saveToDb: false,
      skipRateLimit: true,
    });

    if (result2.success && result2.data) {
      console.log("\n✅ Scraping successful!");
      console.log("\nExtracted Data:");
      console.log(`  Set Number:     ${result2.data.set_number}`);
      console.log(`  Set Name:       ${result2.data.set_name}`);
      console.log(
        `  Year Released:  ${result2.data.year_released || "NOT FOUND ❌"}`,
      );
      console.log(
        `  Year Retired:   ${result2.data.year_retired || "None (expected)"}`,
      );
      console.log(
        `  Parts Count:    ${result2.data.parts_count || "NOT FOUND"}`,
      );

      if (!result2.data.year_retired && result2.data.year_released) {
        console.log(
          "\n✅ CORRECT: Modern set has release year but no retirement year",
        );
      }
    } else {
      console.error("\n❌ Test 2 failed:", result2.error);
    }

    // Summary
    console.log("\n" + "=".repeat(70));
    console.log("Test Summary");
    console.log("=".repeat(70));

    const stats = await repository.getStats();
    console.log(`Total sets in database:     ${stats.total}`);
    console.log(`Sets with year released:    ${stats.withYearReleased}`);
    console.log(`Sets with year retired:     ${stats.withYearRetired}`);

    console.log("\n✅ All tests completed!");
  } catch (error) {
    console.error("\n❌ Test failed with error:", error);
    throw error;
  } finally {
    await closeHttpClient();
    console.log("\n🔒 Cleanup complete");
  }
}

if (import.meta.main) {
  testRetirementYear().catch((error) => {
    console.error("Fatal error:", error);
    Deno.exit(1);
  });
}
