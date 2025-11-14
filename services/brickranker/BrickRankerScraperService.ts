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
import { imageDownloadService } from "../image/ImageDownloadService.ts";
import { imageStorageService } from "../image/ImageStorageService.ts";
import {
  IMAGE_CONFIG,
  ImageDownloadStatus,
} from "../../config/image.config.ts";
import {
  BRICKRANKER_CONFIG,
  calculateBackoff,
  RETRY_CONFIG,
} from "../../config/scraper.config.ts";
import {
  createCircuitBreaker,
  type RedisCircuitBreaker,
} from "../../utils/RedisCircuitBreaker.ts";
import { scraperLogger } from "../../utils/logger.ts";
import { rawDataService } from "../raw-data/index.ts";
import { db } from "../../db/client.ts";
import { scrapeSessions } from "../../db/schema.ts";

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
 * BrickRankerScraperService - Orchestrates the entire scraping workflow
 */
export class BrickRankerScraperService {
  private circuitBreaker: RedisCircuitBreaker;

  constructor(
    private httpClient: HttpClientService,
    private rateLimiter: RateLimiterService,
    private repository: BrickRankerRepository,
  ) {
    // Initialize Redis-based circuit breaker for distributed state
    this.circuitBreaker = createCircuitBreaker("brickranker");
  }

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
      scraperLogger.error("Invalid BrickRanker URL provided", {
        url,
        source: "brickranker",
      });
      return {
        success: false,
        error: `Invalid BrickRanker URL: ${url}`,
      };
    }

    // Check circuit breaker
    if (await this.circuitBreaker.isCircuitOpen()) {
      scraperLogger.warn("BrickRanker circuit breaker is open", {
        url,
        source: "brickranker",
      });
      return {
        success: false,
        error: "Circuit breaker is open. Too many recent failures.",
      };
    }

    let lastError: Error | null = null;
    let retries = 0;
    let scrapeSessionId: number | null = null;

    // Create scrape session if saveToDb is true
    if (saveToDb) {
      const [session] = await db.insert(scrapeSessions).values({
        source: "brickranker",
        sourceUrl: url,
        productsFound: 0,
        productsStored: 0,
        status: "success",
      }).returning();
      scrapeSessionId = session.id;
    }

    // Retry loop with exponential backoff
    for (let attempt = 1; attempt <= RETRY_CONFIG.MAX_RETRIES; attempt++) {
      try {
        retries = attempt - 1;

        scraperLogger.info("Starting BrickRanker scraping attempt", {
          url,
          attempt,
          maxRetries: RETRY_CONFIG.MAX_RETRIES,
          source: "brickranker",
        });

        // Rate limiting (unless skipped)
        if (!skipRateLimit) {
          await this.rateLimiter.waitForNextRequest({
            domain: "brickranker.com",
          });
        }

        // Fetch retirement tracker page
        scraperLogger.info("Fetching BrickRanker retirement tracker page", {
          url,
          source: "brickranker",
        });
        const response = await this.httpClient.fetch({
          url,
          waitForSelector: "table", // Wait for tables to load
        });

        if (response.status !== 200) {
          throw new Error(
            `Failed to fetch retirement tracker page: HTTP ${response.status}`,
          );
        }

        // Save raw HTML if saveToDb is true
        if (saveToDb && scrapeSessionId) {
          await rawDataService.saveRawData({
            scrapeSessionId,
            source: "brickranker",
            sourceUrl: url,
            rawHtml: response.html,
            contentType: "text/html",
            httpStatus: response.status,
          });
        }

        // Parse the page to extract all retirement items
        scraperLogger.info("Parsing BrickRanker retirement data", {
          url,
          source: "brickranker",
        });
        const data = parseRetirementTrackerPage(response.html);

        scraperLogger.info("Successfully parsed BrickRanker data", {
          totalItems: data.totalItems,
          themesCount: data.themes.length,
          themes: data.themes.join(", "),
          source: "brickranker",
        });

        // Save to database if requested
        let saved = false;
        let stats = undefined;
        if (saveToDb) {
          stats = await this.saveToDatabase(data.items);
          saved = true;
        }

        // Reset circuit breaker on success
        await this.circuitBreaker.recordSuccess();

        return {
          success: true,
          data,
          retries,
          saved,
          stats,
        };
      } catch (error) {
        lastError = error as Error;
        scraperLogger.error("BrickRanker scraping attempt failed", {
          url,
          attempt,
          maxRetries: RETRY_CONFIG.MAX_RETRIES,
          error: error.message,
          stack: error.stack,
          source: "brickranker",
        });

        // If not the last attempt, wait with exponential backoff
        if (attempt < RETRY_CONFIG.MAX_RETRIES) {
          const backoffDelay = calculateBackoff(attempt);
          scraperLogger.info("Waiting before retry with exponential backoff", {
            url,
            backoffMs: backoffDelay,
            backoffSeconds: backoffDelay / 1000,
            nextAttempt: attempt + 1,
            source: "brickranker",
          });
          await this.delay(backoffDelay);
        }
      }
    }

    // All retries failed
    await this.circuitBreaker.recordFailure();

    scraperLogger.error("All BrickRanker scraping attempts failed", {
      url,
      totalAttempts: RETRY_CONFIG.MAX_RETRIES,
      finalError: lastError?.message || "Unknown error",
      source: "brickranker",
    });

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
      scraperLogger.info("Saving BrickRanker data to database", {
        itemsCount: items.length,
        source: "brickranker",
      });

      // Download images for all items with imageUrl
      const itemsWithImages = await this.downloadImagesForItems(items);

      // Batch upsert all items
      const stats = await this.repository.batchUpsert(itemsWithImages);

      scraperLogger.info("BrickRanker database save complete", {
        created: stats.created,
        updated: stats.updated,
        total: stats.total,
        source: "brickranker",
      });

      return stats;
    } catch (error) {
      scraperLogger.error("BrickRanker database save failed", {
        error: (error as Error).message,
        stack: (error as Error).stack,
        source: "brickranker",
      });
      throw new Error(`Database save failed: ${error.message}`);
    }
  }

  /**
   * Download images for items that have imageUrl
   */
  private async downloadImagesForItems(
    items: RetirementItemData[],
  ): Promise<
    Array<
      RetirementItemData & {
        localImagePath?: string;
        imageDownloadStatus?: string;
      }
    >
  > {
    const results: Array<
      RetirementItemData & {
        localImagePath?: string;
        imageDownloadStatus?: string;
      }
    > = [];

    for (const item of items) {
      if (!item.imageUrl || !IMAGE_CONFIG.FEATURES.ENABLE_DEDUPLICATION) {
        // No image URL or feature disabled
        results.push({
          ...item,
          imageDownloadStatus: ImageDownloadStatus.SKIPPED,
        });
        continue;
      }

      try {
        scraperLogger.info("Downloading image for BrickRanker item", {
          setNumber: item.setNumber,
          imageUrl: item.imageUrl,
          source: "brickranker",
        });

        const imageData = await imageDownloadService.download(item.imageUrl, {
          timeoutMs: IMAGE_CONFIG.DOWNLOAD.TIMEOUT_MS,
          maxRetries: IMAGE_CONFIG.DOWNLOAD.MAX_RETRIES,
          retryDelayMs: IMAGE_CONFIG.DOWNLOAD.RETRY_DELAY_MS,
          allowedFormats: IMAGE_CONFIG.VALIDATION.ALLOWED_FORMATS,
        });

        const storageResult = await imageStorageService.store(
          imageData.data,
          item.imageUrl,
          imageData.extension,
          item.setNumber,
        );

        results.push({
          ...item,
          localImagePath: storageResult.relativePath,
          imageDownloadStatus: ImageDownloadStatus.COMPLETED,
        });

        scraperLogger.info("Image stored for BrickRanker item", {
          setNumber: item.setNumber,
          localImagePath: storageResult.relativePath,
          source: "brickranker",
        });
      } catch (error) {
        scraperLogger.error("Image download failed for BrickRanker item", {
          setNumber: item.setNumber,
          error: (error as Error).message,
          source: "brickranker",
        });
        results.push({
          ...item,
          imageDownloadStatus: ImageDownloadStatus.FAILED,
        });

        // Continue with other images even if one fails
        if (!IMAGE_CONFIG.FEATURES.FALLBACK_TO_EXTERNAL) {
          throw error;
        }
      }
    }

    return results;
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
   * Get circuit breaker status (for monitoring/debugging)
   */
  async getCircuitBreakerStatus() {
    return await this.circuitBreaker.getState();
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
