/**
 * BricklinkScraperService - High-level orchestrator for Bricklink scraping
 *
 * Responsibilities (Single Responsibility Principle):
 * - Orchestrate scraping workflow
 * - Coordinate between HTTP client, parser, and repository
 * - Handle errors and retries
 * - Manage rate limiting
 * - Apply circuit breaker pattern
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
import type { BricklinkRepository } from "./BricklinkRepository.ts";
import {
  type BricklinkData,
  buildPriceGuideUrl,
  hasAnyPricingChanged,
  parseBricklinkUrl,
  parseItemInfo,
  parsePriceGuide,
} from "./BricklinkParser.ts";
import { calculateBackoff, RETRY_CONFIG } from "../../config/scraper.config.ts";

/**
 * Result of a scraping operation
 */
export interface ScrapeResult {
  success: boolean;
  data?: BricklinkData;
  error?: string;
  retries?: number;
  saved?: boolean;
}

/**
 * Options for scraping
 */
export interface ScrapeOptions {
  url: string;
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
 * BricklinkScraperService - Orchestrates the entire scraping workflow
 */
export class BricklinkScraperService {
  private circuitBreaker: CircuitBreakerState = {
    failures: 0,
    lastFailureTime: 0,
    isOpen: false,
  };

  constructor(
    private httpClient: HttpClientService,
    private rateLimiter: RateLimiterService,
    private repository: BricklinkRepository,
  ) {}

  /**
   * Scrape a Bricklink item
   */
  async scrape(options: ScrapeOptions): Promise<ScrapeResult> {
    const { url, saveToDb = false, skipRateLimit = false } = options;

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
          `🔄 Scraping attempt ${attempt}/${RETRY_CONFIG.MAX_RETRIES}: ${url}`,
        );

        // Rate limiting (unless skipped)
        if (!skipRateLimit) {
          await this.rateLimiter.waitForNextRequest({
            domain: "bricklink.com",
          });
        }

        // Parse URL to extract item info
        const { itemType, itemId } = parseBricklinkUrl(url);

        // Fetch item page
        console.log(`📥 Fetching item page...`);
        const itemResponse = await this.httpClient.fetch({
          url,
          waitForSelector: "h1#item-name-title",
        });

        if (itemResponse.status !== 200) {
          throw new Error(
            `Failed to fetch item page: HTTP ${itemResponse.status}`,
          );
        }

        // Parse item info
        const { title, weight } = parseItemInfo(itemResponse.html);

        // Build price guide URL
        const priceGuideUrl = buildPriceGuideUrl(itemType, itemId);

        // Rate limiting between requests
        if (!skipRateLimit) {
          await this.rateLimiter.waitForNextRequest({
            domain: "bricklink.com",
          });
        }

        // Fetch price guide page
        console.log(`📥 Fetching price guide...`);
        const priceResponse = await this.httpClient.fetch({
          url: priceGuideUrl,
          waitForSelector: "#id-main-legacy-table",
        });

        if (priceResponse.status !== 200) {
          throw new Error(
            `Failed to fetch price guide: HTTP ${priceResponse.status}`,
          );
        }

        // Parse price guide
        const pricingData = parsePriceGuide(priceResponse.html);

        // Build complete data object
        const data: BricklinkData = {
          item_id: itemId,
          item_type: itemType,
          title,
          weight,
          ...pricingData,
        };

        console.log(`✅ Successfully scraped: ${itemId} - ${title}`);

        // Save to database if requested
        let saved = false;
        if (saveToDb) {
          await this.saveToDatabase(data);
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
      error: lastError?.message || "Unknown error",
      retries: RETRY_CONFIG.MAX_RETRIES,
    };
  }

  /**
   * Save scraped data to database
   */
  private async saveToDatabase(data: BricklinkData): Promise<void> {
    try {
      // Upsert the item
      const { item, isNew } = await this.repository.upsert(
        data.item_id,
        {
          itemType: data.item_type,
          title: data.title,
          weight: data.weight,
          sixMonthNew: data.six_month_new,
          sixMonthUsed: data.six_month_used,
          currentNew: data.current_new,
          currentUsed: data.current_used,
        },
      );

      // Update scraping timestamps
      await this.repository.updateScrapingTimestamps(
        data.item_id,
        item.scrapeIntervalDays,
      );

      if (isNew) {
        // New item - always create initial price history
        console.log(`💾 Created new item: ${data.item_id}`);
        await this.repository.createPriceHistory({
          itemId: data.item_id,
          sixMonthNew: data.six_month_new,
          sixMonthUsed: data.six_month_used,
          currentNew: data.current_new,
          currentUsed: data.current_used,
        });
      } else {
        // Existing item - check if prices changed
        if (item.watchStatus === "active") {
          const hasChanged = hasAnyPricingChanged(
            {
              six_month_new: item
                .sixMonthNew as unknown as BricklinkData["six_month_new"],
              six_month_used: item
                .sixMonthUsed as unknown as BricklinkData["six_month_used"],
              current_new: item
                .currentNew as unknown as BricklinkData["current_new"],
              current_used: item
                .currentUsed as unknown as BricklinkData["current_used"],
            },
            data,
          );

          if (hasChanged) {
            console.log(`📊 Price changed for: ${data.item_id}`);
            await this.repository.createPriceHistory({
              itemId: data.item_id,
              sixMonthNew: data.six_month_new,
              sixMonthUsed: data.six_month_used,
              currentNew: data.current_new,
              currentUsed: data.current_used,
            });
          } else {
            console.log(`📊 No price change for: ${data.item_id}`);
          }
        }
      }

      console.log(`✅ Saved to database: ${data.item_id}`);
    } catch (error) {
      console.error(`❌ Database save failed:`, error);
      throw new Error(`Database save failed: ${error.message}`);
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
 * Factory function to create BricklinkScraperService with dependencies
 */
export function createBricklinkScraperService(
  httpClient: HttpClientService,
  rateLimiter: RateLimiterService,
  repository: BricklinkRepository,
): BricklinkScraperService {
  return new BricklinkScraperService(httpClient, rateLimiter, repository);
}
