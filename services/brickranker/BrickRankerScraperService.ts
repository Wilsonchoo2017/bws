/**
 * BrickRankerScraperService - High-level orchestrator for BrickRanker retirement tracker scraping
 *
 * Responsibilities (Single Responsibility Principle):
 * - Orchestrate scraping workflow for retirement tracker
 * - Coordinate between HTTP client, parser, and repository
 * - Handle errors and retries
 * - Manage rate limiting
 * - Apply circuit breaker pattern
 * - Batch process all retirement items on page
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
import type { BrickRankerRepository } from "./BrickRankerRepository.ts";
import {
  type BrickRankerParseResult,
  isValidBrickRankerUrl,
  parseRetirementTrackerPage,
  type RetirementItemData,
} from "./BrickRankerParser.ts";
import {
  BRICKRANKER_CONFIG,
  calculateBackoff,
  RETRY_CONFIG,
} from "../../config/scraper.config.ts";

/**
 * Result of a scraping operation
 */
export interface ScrapeResult {
  success: boolean;
  data?: BrickRankerParseResult;
  error?: string;
  retries?: number;
  saved?: boolean;
  stats?: {
    created: number;
    updated: number;
    total: number;
  };
}

/**
 * Options for scraping
 */
export interface ScrapeOptions {
  url?: string; // Optional, defaults to BRICKRANKER_CONFIG.BASE_URL
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

/**
 * BrickRankerScraperService - Orchestrates the entire scraping workflow
 */
export class BrickRankerScraperService {
  private circuitBreaker: CircuitBreakerState = {
    failures: 0,
    lastFailureTime: 0,
    isOpen: false,
  };

  constructor(
    private httpClient: HttpClientService,
    private rateLimiter: RateLimiterService,
    private repository: BrickRankerRepository,
  ) {}

  /**
   * Scrape the BrickRanker retirement tracker page
   */
  async scrape(options: ScrapeOptions = {}): Promise<ScrapeResult> {
    const {
      url = BRICKRANKER_CONFIG.BASE_URL,
      saveToDb = false,
      skipRateLimit = false,
    } = options;

    // Validate URL
    if (!isValidBrickRankerUrl(url)) {
      return {
        success: false,
        error: `Invalid BrickRanker URL: ${url}`,
      };
    }

    // Check circuit breaker
    if (this.isCircuitOpen()) {
      return {
        success: false,
        error: "Circuit breaker is open. Too many recent failures.",
      };
    }

    let lastError: Error | null = null;
    let retries = 0;

    // Retry loop with exponential backoff
    for (let attempt = 1; attempt <= RETRY_CONFIG.MAX_RETRIES; attempt++) {
      try {
        retries = attempt - 1;

        console.log(
          `🔄 Scraping BrickRanker attempt ${attempt}/${RETRY_CONFIG.MAX_RETRIES}: ${url}`,
        );

        // Rate limiting (unless skipped)
        if (!skipRateLimit) {
          await this.rateLimiter.waitForNextRequest({
            domain: "brickranker.com",
          });
        }

        // Fetch retirement tracker page
        console.log(`📥 Fetching retirement tracker page...`);
        const response = await this.httpClient.fetch({
          url,
          waitForSelector: "table", // Wait for tables to load
        });

        if (response.status !== 200) {
          throw new Error(
            `Failed to fetch retirement tracker page: HTTP ${response.status}`,
          );
        }

        // Parse the page to extract all retirement items
        console.log(`🔍 Parsing retirement data...`);
        const data = parseRetirementTrackerPage(response.html);

        console.log(
          `✅ Successfully parsed ${data.totalItems} items across ${data.themes.length} themes`,
        );
        console.log(`📋 Themes found: ${data.themes.join(", ")}`);

        // Save to database if requested
        let saved = false;
        let stats = undefined;
        if (saveToDb) {
          stats = await this.saveToDatabase(data.items);
          saved = true;
        }

        // Reset circuit breaker on success
        this.resetCircuitBreaker();

        return {
          success: true,
          data,
          retries,
          saved,
          stats,
        };
      } catch (error) {
        lastError = error as Error;
        console.error(
          `❌ Scraping attempt ${attempt} failed:`,
          error.message,
        );

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
      error: lastError?.message || "Unknown error",
      retries: RETRY_CONFIG.MAX_RETRIES,
    };
  }

  /**
   * Save scraped data to database (batch upsert)
   */
  private async saveToDatabase(
    items: RetirementItemData[],
  ): Promise<{ created: number; updated: number; total: number }> {
    try {
      console.log(`💾 Saving ${items.length} items to database...`);

      // Batch upsert all items
      const stats = await this.repository.batchUpsert(items);

      console.log(
        `✅ Database save complete: ${stats.created} created, ${stats.updated} updated, ${stats.total} total`,
      );

      return stats;
    } catch (error) {
      console.error(`❌ Database save failed:`, error);
      throw new Error(`Database save failed: ${error.message}`);
    }
  }

  /**
   * Scrape and save to database (convenience method)
   */
  async scrapeAndSave(
    options: Omit<ScrapeOptions, "saveToDb"> = {},
  ): Promise<ScrapeResult> {
    return await this.scrape({ ...options, saveToDb: true });
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

    if (timeSinceLastFailure >= RETRY_CONFIG.CIRCUIT_BREAKER_TIMEOUT) {
      // Reset circuit breaker
      console.log("🔄 Circuit breaker timeout passed. Resetting...");
      this.resetCircuitBreaker();
      return false;
    }

    return true;
  }

  /**
   * Record a failure for circuit breaker
   */
  private recordFailure(): void {
    this.circuitBreaker.failures++;
    this.circuitBreaker.lastFailureTime = Date.now();

    if (
      this.circuitBreaker.failures >= RETRY_CONFIG.CIRCUIT_BREAKER_THRESHOLD
    ) {
      this.circuitBreaker.isOpen = true;
      console.error(
        `⚠️ Circuit breaker opened after ${this.circuitBreaker.failures} failures`,
      );
    }
  }

  /**
   * Reset circuit breaker
   */
  private resetCircuitBreaker(): void {
    if (this.circuitBreaker.failures > 0 || this.circuitBreaker.isOpen) {
      console.log("✅ Circuit breaker reset");
    }
    this.circuitBreaker = {
      failures: 0,
      lastFailureTime: 0,
      isOpen: false,
    };
  }

  /**
   * Get circuit breaker status
   */
  getCircuitBreakerStatus(): CircuitBreakerState {
    return { ...this.circuitBreaker };
  }

  /**
   * Delay helper
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Close all resources
   */
  async close(): Promise<void> {
    await this.httpClient.close();
  }
}

/**
 * Factory function to create BrickRankerScraperService with dependencies
 */
export function createBrickRankerScraperService(
  httpClient: HttpClientService,
  rateLimiter: RateLimiterService,
  repository: BrickRankerRepository,
): BrickRankerScraperService {
  return new BrickRankerScraperService(httpClient, rateLimiter, repository);
}
