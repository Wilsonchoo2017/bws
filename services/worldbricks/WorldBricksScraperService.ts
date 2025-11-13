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
  type WorldBricksData,
  parseWorldBricksHtml,
  constructWorldBricksUrl,
  constructSearchUrl,
  parseSearchResults,
  isValidWorldBricksPage,
} from "./WorldBricksParser.ts";
import { calculateBackoff, RETRY_CONFIG } from "../../config/scraper.config.ts";

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
 * Circuit breaker state
 */
interface CircuitBreakerState {
  failures: number;
  lastFailureTime: number;
  isOpen: boolean;
}

const CIRCUIT_BREAKER_THRESHOLD = 5; // Open after 5 consecutive failures
const CIRCUIT_BREAKER_TIMEOUT = 5 * 60 * 1000; // Reset after 5 minutes

/**
 * WorldBricksScraperService - Orchestrates the entire WorldBricks scraping workflow
 */
export class WorldBricksScraperService {
  private circuitBreaker: CircuitBreakerState = {
    failures: 0,
    lastFailureTime: 0,
    isOpen: false,
  };

  constructor(
    private httpClient: HttpClientService,
    private rateLimiter: RateLimiterService,
    private repository: WorldBricksRepository,
  ) {}

  /**
   * Scrape a LEGO set from WorldBricks
   */
  async scrape(options: ScrapeOptions): Promise<ScrapeResult> {
    const { setNumber, setName, url, saveToDb = false, skipRateLimit = false } = options;

    // Check circuit breaker
    if (this.isCircuitOpen()) {
      return {
        success: false,
        error: "Circuit breaker is open. Too many recent failures.",
      };
    }

    let lastError: Error | null = null;
    let retries = 0;
    let targetUrl: string | null = url || null;

    // Retry loop with exponential backoff
    for (let attempt = 1; attempt <= RETRY_CONFIG.MAX_RETRIES; attempt++) {
      try {
        retries = attempt - 1;

        console.log(
          `🔄 Scraping attempt ${attempt}/${RETRY_CONFIG.MAX_RETRIES}: Set ${setNumber}`,
        );

        // If no explicit URL provided, use search to find it
        if (!targetUrl) {
          console.log(`🔍 Searching for set ${setNumber} on WorldBricks...`);

          // Rate limiting for search request
          if (!skipRateLimit) {
            await this.rateLimiter.waitForNextRequest({
              domain: "worldbricks.com",
            });
          }

          const searchUrl = constructSearchUrl(setNumber);
          console.log(`📥 Fetching search results: ${searchUrl}`);

          const searchResponse = await this.httpClient.fetch({
            url: searchUrl,
            timeout: 30000,
          });

          if (searchResponse.status !== 200) {
            throw new Error(
              `Failed to fetch search results: HTTP ${searchResponse.status}`,
            );
          }

          // Parse search results to find product URL
          targetUrl = parseSearchResults(searchResponse.html, setNumber);

          if (!targetUrl) {
            throw new Error(
              `Could not find set ${setNumber} in WorldBricks search results`,
            );
          }

          console.log(`✅ Found product page: ${targetUrl}`);
        }

        // Rate limiting (unless skipped)
        if (!skipRateLimit) {
          await this.rateLimiter.waitForNextRequest({
            domain: "worldbricks.com",
          });
        }

        // Fetch WorldBricks product page
        console.log(`📥 Fetching WorldBricks page: ${targetUrl}`);
        const response = await this.httpClient.fetch({
          url: targetUrl,
          timeout: 30000,
        });

        if (response.status !== 200) {
          throw new Error(
            `Failed to fetch WorldBricks page: HTTP ${response.status}`,
          );
        }

        // Validate that it's a valid WorldBricks product page
        if (!isValidWorldBricksPage(response.html)) {
          throw new Error("Page does not appear to be a valid WorldBricks product page");
        }

        // Parse the HTML
        console.log(`🔍 Parsing WorldBricks data for set ${setNumber}...`);
        const data = parseWorldBricksHtml(response.html, targetUrl);

        // Validate that we got the correct set
        if (data.set_number !== setNumber) {
          console.warn(
            `⚠️  Set number mismatch: Expected ${setNumber}, got ${data.set_number}`,
          );
        }

        console.log(`✅ Successfully scraped: ${data.set_number} - ${data.set_name}`);
        console.log(`   Year Released: ${data.year_released || "Unknown"}`);
        console.log(`   Year Retired: ${data.year_retired || "Unknown"}`);
        console.log(`   Parts Count: ${data.parts_count || "Unknown"}`);

        // Save to database if requested
        let saved = false;
        if (saveToDb) {
          await this.saveToDatabase(data, targetUrl);
          saved = true;
        }

        // Reset circuit breaker on success
        this.resetCircuitBreaker();

        return {
          success: true,
          data,
          retries,
          saved,
        };
      } catch (error) {
        lastError = error as Error;
        console.error(`❌ Scraping attempt ${attempt} failed:`, error.message);

        // If not the last attempt, wait with exponential backoff
        if (attempt < RETRY_CONFIG.MAX_RETRIES) {
          const backoffDelay = calculateBackoff(attempt);
          console.log(
            `⏳ Waiting ${backoffDelay / 1000}s before retry...`,
          );
          await this.delay(backoffDelay);
        }
      }
    }

    // All retries failed
    this.recordFailure();

    return {
      success: false,
      error: lastError?.message || "Unknown error occurred",
      retries,
    };
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

    for (let i = 0; i < sets.length; i++) {
      const set = sets[i];

      console.log(`\n📦 Processing set ${i + 1}/${sets.length}: ${set.setNumber}`);

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
          console.log(`⏳ Waiting ${delayBetweenRequests}ms before next request...`);
          await this.delay(delayBetweenRequests);
        }
      } catch (error) {
        console.error(`Failed to scrape set ${set.setNumber}:`, error);
        results.push({
          success: false,
          error: (error as Error).message,
        });
      }
    }

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
      console.log(`💾 Saving to database: ${data.set_number}`);

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

      console.log(`✅ Successfully saved to database`);
    } catch (error) {
      console.error(`❌ Failed to save to database:`, error);
      throw error;
    }
  }

  /**
   * Check if circuit breaker is open
   */
  private isCircuitOpen(): boolean {
    if (!this.circuitBreaker.isOpen) {
      return false;
    }

    // Check if timeout has passed
    const now = Date.now();
    const timeSinceLastFailure = now - this.circuitBreaker.lastFailureTime;

    if (timeSinceLastFailure > CIRCUIT_BREAKER_TIMEOUT) {
      // Reset circuit breaker after timeout
      this.resetCircuitBreaker();
      return false;
    }

    return true;
  }

  /**
   * Record a failure and potentially open circuit breaker
   */
  private recordFailure(): void {
    this.circuitBreaker.failures++;
    this.circuitBreaker.lastFailureTime = Date.now();

    if (this.circuitBreaker.failures >= CIRCUIT_BREAKER_THRESHOLD) {
      console.warn(
        `⚠️  Circuit breaker opened after ${this.circuitBreaker.failures} failures`,
      );
      this.circuitBreaker.isOpen = true;
    }
  }

  /**
   * Reset circuit breaker after successful request
   */
  private resetCircuitBreaker(): void {
    if (this.circuitBreaker.failures > 0 || this.circuitBreaker.isOpen) {
      console.log(`✅ Circuit breaker reset`);
    }

    this.circuitBreaker.failures = 0;
    this.circuitBreaker.isOpen = false;
  }

  /**
   * Delay helper function
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Get circuit breaker status (for monitoring)
   */
  getCircuitBreakerStatus(): CircuitBreakerState {
    return { ...this.circuitBreaker };
  }
}
