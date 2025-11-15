#!/usr/bin/env -S deno run --allow-all
/**
 * Test WorldBricks scraping with simple HTTP fetch (no Puppeteer)
 */

import { getHttpClient } from "../services/http/HttpClientService.ts";
import { getRateLimiter } from "../services/rate-limiter/RateLimiterService.ts";
import { getWorldBricksRepository } from "../services/worldbricks/WorldBricksRepository.ts";
import { WorldBricksScraperService } from "../services/worldbricks/WorldBricksScraperService.ts";

async function main() {
  console.log("🧪 Testing WorldBricks Simple Fetch\n");

  try {
    const httpClient = getHttpClient();
    const rateLimiter = getRateLimiter();
    const repository = getWorldBricksRepository();

    const scraper = new WorldBricksScraperService(
      httpClient,
      rateLimiter,
      repository,
    );

    // Test with a known set
    const testSetNumber = "7819"; // Mail Wagon from your example
    console.log(`📦 Testing set: ${testSetNumber}\n`);

    const result = await scraper.scrape({
      setNumber: testSetNumber,
      saveToDb: false, // Don't save to DB during test
    });

    if (result.success && result.data) {
      console.log("\n✅ SUCCESS! WorldBricks data retrieved:");
      console.log(`   Set Number: ${result.data.set_number}`);
      console.log(`   Set Name: ${result.data.set_name}`);
      console.log(`   Year Released: ${result.data.year_released}`);
      console.log(`   Year Retired: ${result.data.year_retired}`);
      console.log(`   Designer: ${result.data.designer}`);
      console.log(`   Parts Count: ${result.data.parts_count}`);
      console.log(`   Dimensions: ${result.data.dimensions}`);
      console.log(
        `   Description: ${result.data.description?.substring(0, 100)}...`,
      );
    } else {
      console.error("\n❌ FAILED:", result.error);
    }
  } catch (error) {
    console.error("❌ Test failed:", error);
    Deno.exit(1);
  }
}

main();
