/**
 * BaseScraperService - Base class for all scraper services
 *
 * Responsibilities (Single Responsibility Principle):
 * - Provide common retry logic with exponential backoff
 * - Circuit breaker integration
 * - Error handling and logging
 * - Rate limiting coordination
 *
 * This base class follows DRY (Don't Repeat Yourself) by extracting
 * common patterns from all scraper services into a reusable abstraction.
 */

import type { RateLimiterService } from "../rate-limiter/RateLimiterService.ts";
import { calculateBackoff, RETRY_CONFIG } from "../../config/scraper.config.ts";
import {
  createCircuitBreaker,
  type RedisCircuitBreaker,
} from "../../utils/RedisCircuitBreaker.ts";
import { scraperLogger } from "../../utils/logger.ts";
import { db } from "../../db/client.ts";
import { scrapeSessions } from "../../db/schema.ts";
import { rawDataService } from "../raw-data/index.ts";
import { MaintenanceError } from "../../types/errors/MaintenanceError.ts";
import { SetNotFoundError } from "../../types/errors/SetNotFoundError.ts";

/**
 * Options for retry logic
 */
export interface RetryOptions {
  url: string;
  skipRateLimit?: boolean;
  domain: string;
  source: string;
  context?: Record<string, unknown>; // Additional context for logging
}

/**
 * Valid source values for scraping sessions
 */
export type ScraperSource =
  | "shopee"
  | "toysrus"
  | "brickeconomy"
  | "bricklink"
  | "worldbricks"
  | "brickranker"
  | "reddit"
  | "self";

/**
 * Options for creating a scrape session
 */
export interface SessionOptions {
  source: ScraperSource;
  sourceUrl: string;
}

/**
 * Options for saving raw HTML data
 */
export interface RawDataOptions {
  scrapeSessionId: number;
  source: ScraperSource;
  sourceUrl: string;
  rawHtml: string;
  httpStatus: number;
}

/**
 * BaseScraperService - Provides common scraper functionality
 */
export abstract class BaseScraperService {
  protected circuitBreaker: RedisCircuitBreaker;

  constructor(
    protected rateLimiter: RateLimiterService,
    circuitBreakerName: string,
  ) {
    this.circuitBreaker = createCircuitBreaker(circuitBreakerName);
  }

  /**
   * Execute an operation with retry logic and exponential backoff
   *
   * @param operation - The async operation to execute with retries
   * @param options - Retry configuration options
   * @returns Promise that resolves with the operation result or rejects after all retries fail
   */
  protected async withRetryLogic<T>(
    operation: (attempt: number) => Promise<T>,
    options: RetryOptions,
  ): Promise<T> {
    const { url, skipRateLimit = false, domain, source, context = {} } =
      options;

    // Check circuit breaker
    if (await this.circuitBreaker.isCircuitOpen()) {
      scraperLogger.warn(`${source} circuit breaker is open`, {
        ...context,
        source,
      });
      throw new Error("Circuit breaker is open. Too many recent failures.");
    }

    let lastError: Error | null = null;

    // Retry loop with exponential backoff
    for (let attempt = 1; attempt <= RETRY_CONFIG.MAX_RETRIES; attempt++) {
      try {
        scraperLogger.info(
          `Scraping attempt ${attempt}/${RETRY_CONFIG.MAX_RETRIES}: ${url}`,
          {
            attempt,
            maxRetries: RETRY_CONFIG.MAX_RETRIES,
            url,
            source,
            ...context,
          },
        );

        // Rate limiting (unless skipped)
        if (!skipRateLimit) {
          await this.rateLimiter.waitForNextRequest({ domain });
        }

        // Execute the operation
        const result = await operation(attempt);

        // Reset circuit breaker on success
        await this.circuitBreaker.recordSuccess();

        return result;
      } catch (error) {
        lastError = error as Error;

        // Handle maintenance errors specially - don't count toward circuit breaker
        if (MaintenanceError.isMaintenanceError(error)) {
          scraperLogger.warn(
            `Maintenance detected: ${error.message}`,
            {
              attempt,
              estimatedDurationMs: error.estimatedDurationMs,
              estimatedEndTime: error.getEstimatedEndTime(),
              url,
              source,
              ...context,
            },
          );
          // Re-throw immediately without retrying or counting toward circuit breaker
          throw error;
        }

        // Handle set not found errors - permanent failure, no retry needed
        if (SetNotFoundError.isSetNotFoundError(error)) {
          scraperLogger.warn(
            `Set not found (permanent failure): ${error.message}`,
            {
              attempt,
              setNumber: error.setNumber,
              source: error.source,
              url,
              ...context,
            },
          );
          // Re-throw immediately without retrying or counting toward circuit breaker
          throw error;
        }

        scraperLogger.error(
          `Scraping attempt ${attempt} failed: ${error.message}`,
          {
            attempt,
            error: error.message,
            stack: error.stack,
            url,
            source,
            ...context,
          },
        );

        // If not the last attempt, wait with exponential backoff
        if (attempt < RETRY_CONFIG.MAX_RETRIES) {
          const backoffDelay = calculateBackoff(attempt);
          scraperLogger.info(
            `⏳ Waiting ${backoffDelay / 1000}s before retry...`,
            {
              backoffMs: backoffDelay,
              backoffSeconds: backoffDelay / 1000,
              nextAttempt: attempt + 1,
              source,
              ...context,
            },
          );
          await this.delay(backoffDelay);
        }
      }
    }

    // All retries failed
    await this.circuitBreaker.recordFailure();

    scraperLogger.error(`All scraping attempts failed`, {
      url,
      totalAttempts: RETRY_CONFIG.MAX_RETRIES,
      finalError: lastError?.message || "Unknown error",
      source,
      ...context,
    });

    throw lastError || new Error("Unknown error occurred");
  }

  /**
   * Create a scrape session in the database
   *
   * @param options - Session creation options
   * @returns The created session ID, or null if creation failed
   */
  protected async createScrapeSession(
    options: SessionOptions,
  ): Promise<number | null> {
    try {
      const [session] = await db.insert(scrapeSessions).values({
        source: options.source,
        sourceUrl: options.sourceUrl,
        productsFound: 0,
        productsStored: 0,
        status: "success",
      }).returning();
      return session.id;
    } catch (error) {
      scraperLogger.error("Failed to create scrape session", {
        source: options.source,
        error: error.message,
      });
      return null;
    }
  }

  /**
   * Save raw HTML data to the database
   *
   * @param options - Raw data saving options
   */
  protected async saveRawHtml(options: RawDataOptions): Promise<void> {
    try {
      await rawDataService.saveRawData({
        scrapeSessionId: options.scrapeSessionId,
        source: options.source,
        sourceUrl: options.sourceUrl,
        rawHtml: options.rawHtml,
        contentType: "text/html",
        httpStatus: options.httpStatus,
      });
    } catch (error) {
      scraperLogger.error("Failed to save raw HTML", {
        source: options.source,
        error: error.message,
      });
      // Don't throw - raw data saving is not critical
    }
  }

  /**
   * Get circuit breaker status (for monitoring/debugging)
   */
  async getCircuitBreakerStatus() {
    return await this.circuitBreaker.getState();
  }

  /**
   * Delay helper
   */
  protected delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
