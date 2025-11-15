/**
 * WorldBricksScraperService - High-level orchestrator for WorldBricks scraping
 *
 * Responsibilities (Single Responsibility Principle):
 * - Orchestrate WorldBricks scraping workflow
 * - Coordinate between HTTP client, parser, and repository
 * - Handle errors and retries
 * - Manage rate limiting
 * - Apply circuit breaker pattern
 * - URL construction with trial-and-error fallback
 *
 * This service follows SOLID principles:
 * - SRP: Only handles orchestration logic
 * - OCP: Can be extended without modifying core logic
 * - LSP: Can be substituted with mock for testing
 * - ISP: Focused interface for scraping operations
 * - DIP: Depends on abstractions (injected dependencies)
 */

import type { HttpClientService } from "../http/HttpClientService.ts";
import type { RateLimiterService } from "../rate-limiter/RateLimiterService.ts";
import type { WorldBricksRepository } from "./WorldBricksRepository.ts";
import {
  constructSearchUrl,
  isValidWorldBricksPage,
  parseSearchResults,
  parseWorldBricksHtml,
  type WorldBricksData,
} from "./WorldBricksParser.ts";
import { scraperLogger } from "../../utils/logger.ts";
import { BaseScraperService } from "../base/BaseScraperService.ts";

/**
 * Result of a scraping operation
 */
export interface ScrapeResult {
  success: boolean;
  data?: WorldBricksData;
  error?: string;
  retries?: number;
  saved?: boolean;
}

/**
 * Options for scraping a set
 */
export interface ScrapeOptions {
  setNumber: string;
  setName?: string;
  url?: string; // Optional explicit URL
  saveToDb?: boolean;
  skipRateLimit?: boolean;
}

/**
 * WorldBricksScraperService - Orchestrates the entire WorldBricks scraping workflow
 */
export class WorldBricksScraperService extends BaseScraperService {
  constructor(
    private httpClient: HttpClientService,
    rateLimiter: RateLimiterService,
    private repository: WorldBricksRepository,
  ) {
    super(rateLimiter, "worldbricks");
  }

  /**
   * Scrape a LEGO set from WorldBricks
   */
  async scrape(options: ScrapeOptions): Promise<ScrapeResult> {
    const {
      setNumber,
      setName: _setName,
      url,
      saveToDb = false,
      skipRateLimit = false,
    } = options;

    let targetUrl: string | null = url || null;
    let scrapeSessionId: number | null = null;

    // Create scrape session if saveToDb is true
    if (saveToDb) {
      scrapeSessionId = await this.createScrapeSession({
        source: "worldbricks",
        sourceUrl: url || `https://www.worldbricks.com search for ${setNumber}`,
      });
    }

    try {
      const data = await this.withRetryLogic(
        async (_attempt) => {
          // If no explicit URL provided, use search to find it
          if (!targetUrl) {
            scraperLogger.info("Searching for set on WorldBricks", {
              setNumber,
              source: "worldbricks",
            });

            const searchUrl = constructSearchUrl(setNumber);
            scraperLogger.info("Fetching WorldBricks search results", {
              setNumber,
              url: searchUrl,
              source: "worldbricks",
            });

            const searchResponse = await this.httpClient.simpleFetch({
              url: searchUrl,
              timeout: 30000,
            });

            if (searchResponse.status !== 200) {
              throw new Error(
                `Failed to fetch search results: HTTP ${searchResponse.status}`,
              );
            }

            // Save raw HTML for search results if saveToDb is true
            if (saveToDb && scrapeSessionId) {
              await this.saveRawHtml({
                scrapeSessionId,
                source: "worldbricks",
                sourceUrl: searchUrl,
                rawHtml: searchResponse.html,
                httpStatus: searchResponse.status,
              });
            }

            // Parse search results to find product URL
            targetUrl = parseSearchResults(searchResponse.html, setNumber);

            if (!targetUrl) {
              throw new Error(
                `Could not find set ${setNumber} in WorldBricks search results`,
              );
            }

            scraperLogger.info("Found product page in search results", {
              setNumber,
              url: targetUrl,
              source: "worldbricks",
            });
          }

          // Fetch WorldBricks product page
          scraperLogger.info("Fetching WorldBricks product page", {
            setNumber,
            url: targetUrl,
            source: "worldbricks",
          });
          const response = await this.httpClient.simpleFetch({
            url: targetUrl,
            timeout: 30000,
          });

          if (response.status !== 200) {
            throw new Error(
              `Failed to fetch WorldBricks page: HTTP ${response.status}`,
            );
          }

          // Save raw HTML for product page if saveToDb is true
          if (saveToDb && scrapeSessionId) {
            await this.saveRawHtml({
              scrapeSessionId,
              source: "worldbricks",
              sourceUrl: targetUrl,
              rawHtml: response.html,
              httpStatus: response.status,
            });
          }

          // Validate that it's a valid WorldBricks product page
          if (!isValidWorldBricksPage(response.html)) {
            throw new Error(
              "Page does not appear to be a valid WorldBricks product page",
            );
          }

          // Parse the HTML
          scraperLogger.info("Parsing WorldBricks data", {
            setNumber,
            url: targetUrl,
            source: "worldbricks",
          });
          const scraperData = parseWorldBricksHtml(response.html, targetUrl);

          // Validate that we got the correct set
          if (scraperData.set_number !== setNumber) {
            scraperLogger.warn("Set number mismatch detected", {
              expected: setNumber,
              actual: scraperData.set_number,
              url: targetUrl,
              source: "worldbricks",
            });
          }

          scraperLogger.info("Successfully scraped WorldBricks data", {
            setNumber: scraperData.set_number,
            setName: scraperData.set_name,
            yearReleased: scraperData.year_released,
            yearRetired: scraperData.year_retired,
            partsCount: scraperData.parts_count,
            source: "worldbricks",
          });

          // Save to database if requested
          if (saveToDb) {
            await this.saveToDatabase(scraperData, targetUrl);
          }

          return { data: scraperData, saved: saveToDb };
        },
        {
          url: url || `https://www.worldbricks.com search for ${setNumber}`,
          skipRateLimit,
          domain: "worldbricks.com",
          source: "worldbricks",
          context: { setNumber },
        },
      );

      return {
        success: true,
        data: data.data,
        saved: data.saved,
        retries: 0,
      };
    } catch (error) {
      return {
        success: false,
        error: error.message || "Unknown error occurred",
      };
    }
  }

  /**
   * Scrape multiple sets in batch
   */
  async scrapeBatch(
    sets: Array<{ setNumber: string; setName?: string; url?: string }>,
    options: { saveToDb?: boolean; delayBetweenRequests?: number } = {},
  ): Promise<ScrapeResult[]> {
    const { saveToDb = false, delayBetweenRequests = 2000 } = options;
    const results: ScrapeResult[] = [];

    scraperLogger.info("Starting WorldBricks batch scraping", {
      totalSets: sets.length,
      saveToDb,
      delayBetweenRequests,
      source: "worldbricks",
    });

    for (let i = 0; i < sets.length; i++) {
      const set = sets[i];

      scraperLogger.info("Processing set in batch", {
        setNumber: set.setNumber,
        progress: `${i + 1}/${sets.length}`,
        source: "worldbricks",
      });

      try {
        const result = await this.scrape({
          setNumber: set.setNumber,
          setName: set.setName,
          url: set.url,
          saveToDb,
        });

        results.push(result);

        // Add delay between requests (except for last one)
        if (i < sets.length - 1 && result.success) {
          scraperLogger.info("Waiting between batch requests", {
            delayMs: delayBetweenRequests,
            nextSet: sets[i + 1].setNumber,
            source: "worldbricks",
          });
          await this.delay(delayBetweenRequests);
        }
      } catch (error) {
        scraperLogger.error("Failed to scrape set in batch", {
          setNumber: set.setNumber,
          error: (error as Error).message,
          source: "worldbricks",
        });
        results.push({
          success: false,
          error: (error as Error).message,
        });
      }
    }

    const successCount = results.filter((r) => r.success).length;
    scraperLogger.info("Completed WorldBricks batch scraping", {
      totalSets: sets.length,
      successCount,
      failureCount: sets.length - successCount,
      source: "worldbricks",
    });

    return results;
  }

  /**
   * Save scraped data to database
   */
  private async saveToDatabase(
    data: WorldBricksData,
    sourceUrl: string,
  ): Promise<void> {
    try {
      scraperLogger.info("Saving WorldBricks data to database", {
        setNumber: data.set_number,
        setName: data.set_name,
        source: "worldbricks",
      });

      await this.repository.upsert(data.set_number, {
        setName: data.set_name,
        description: data.description,
        yearReleased: data.year_released,
        yearRetired: data.year_retired,
        designer: data.designer,
        partsCount: data.parts_count,
        dimensions: data.dimensions,
        imageUrl: data.image_url,
        sourceUrl,
        lastScrapedAt: new Date(),
        scrapeStatus: "success",
      });

      scraperLogger.info("Successfully saved WorldBricks data to database", {
        setNumber: data.set_number,
        source: "worldbricks",
      });
    } catch (error) {
      scraperLogger.error("Failed to save WorldBricks data to database", {
        setNumber: data.set_number,
        error: (error as Error).message,
        stack: (error as Error).stack,
        source: "worldbricks",
      });
      throw error;
    }
  }

}
