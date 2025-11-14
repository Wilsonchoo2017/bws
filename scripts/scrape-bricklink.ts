#!/usr/bin/env -S deno run -A

/**
 * CLI script to scrape a BrickLink item
 * Usage: deno run -A scripts/scrape-bricklink.ts <item-id>
 * Example: deno run -A scripts/scrape-bricklink.ts 60321-1
 */

import { createBricklinkScraperService } from "../services/bricklink/BricklinkScraperService.ts";
import { getHttpClient } from "../services/http/HttpClientService.ts";
import { getRateLimiter } from "../services/rate-limiter/RateLimiterService.ts";
import { BricklinkRepository } from "../services/bricklink/BricklinkRepository.ts";
import { scraperLogger } from "../utils/logger.ts";

async function main() {
  const itemId = Deno.args[0];

  if (!itemId) {
    console.error("Usage: deno run -A scripts/scrape-bricklink.ts <item-id>");
    console.error("Example: deno run -A scripts/scrape-bricklink.ts 60321-1");
    Deno.exit(1);
  }

  const itemType = "S"; // Assuming sets - could be made configurable
  const url = `https://www.bricklink.com/v2/catalog/catalogitem.page?${itemType}=${itemId}`;

  scraperLogger.info(`Starting scrape for BrickLink item: ${itemId}`);
  scraperLogger.info(`URL: ${url}`);

  const httpClient = getHttpClient();
  const rateLimiter = getRateLimiter();
  const repository = new BricklinkRepository();
  const scraper = createBricklinkScraperService(
    httpClient,
    rateLimiter,
    repository,
  );

  try {
    const result = await scraper.scrape({
      url,
      saveToDb: true,
      skipRateLimit: false,
    });

    if (result.success) {
      scraperLogger.info(`Successfully scraped item: ${itemId}`);
      scraperLogger.info(`Title: ${result.data?.title}`);
      scraperLogger.info(`Saved to database: ${result.saved}`);
      console.log("\nScrape successful!");
      console.log(`Item: ${result.data?.title}`);
      console.log(`Pricing data saved: ${result.saved}`);
    } else {
      scraperLogger.error(`Scrape failed: ${result.error}`);
      console.error(`\nScrape failed: ${result.error}`);
      Deno.exit(1);
    }
  } catch (error) {
    scraperLogger.error(`Unexpected error: ${error.message}`, {
      error: error.message,
      stack: error.stack,
    });
    console.error(`\nUnexpected error: ${error.message}`);
    Deno.exit(1);
  } finally {
    await scraper.close();
  }
}

main();
