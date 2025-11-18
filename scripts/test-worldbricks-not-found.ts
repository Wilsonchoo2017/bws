/**
 * Test script to verify SetNotFoundError handling for WorldBricks scraper
 * Tests that set 77243 (which doesn't exist in WorldBricks) is handled correctly
 */

import { getHttpClient } from "../services/http/HttpClientService.ts";
import { getRateLimiter } from "../services/rate-limiter/RateLimiterService.ts";
import { getWorldBricksRepository } from "../services/worldbricks/WorldBricksRepository.ts";
import { WorldBricksScraperService } from "../services/worldbricks/WorldBricksScraperService.ts";
import { SetNotFoundError } from "../types/errors/SetNotFoundError.ts";

async function testSetNotFoundError() {
  console.log("Testing SetNotFoundError handling for set 77243...\n");

  const httpClient = getHttpClient();
  const rateLimiter = getRateLimiter();
  const repository = getWorldBricksRepository();

  const scraper = new WorldBricksScraperService(
    httpClient,
    rateLimiter,
    repository,
  );

  try {
    console.log("Attempting to scrape set 77243 from WorldBricks...");
    const result = await scraper.scrape({
      setNumber: "77243",
      saveToDb: false,
      skipRateLimit: true,
    });

    console.log("❌ FAIL: Expected SetNotFoundError to be thrown, but got result:", result);
    Deno.exit(1);
  } catch (error) {
    if (SetNotFoundError.isSetNotFoundError(error)) {
      console.log("✅ PASS: SetNotFoundError was correctly thrown");
      console.log("   Set Number:", error.setNumber);
      console.log("   Source:", error.source);
      console.log("   Message:", error.message);
      console.log("   Detected At:", error.detectedAt.toISOString());
      console.log("\n✅ The error type is preserved correctly!");
      Deno.exit(0);
    } else {
      console.log("❌ FAIL: Expected SetNotFoundError but got different error type:");
      console.log("   Error type:", error.constructor.name);
      console.log("   Message:", error.message);
      console.log("   Stack:", error.stack);
      Deno.exit(1);
    }
  }
}

testSetNotFoundError();
