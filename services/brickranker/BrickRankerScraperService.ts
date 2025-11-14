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
import { BRICKRANKER_CONFIG } from "../../config/scraper.config.ts";
import { scraperLogger } from "../../utils/logger.ts";
import { BaseScraperService } from "../base/BaseScraperService.ts";

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
export class BrickRankerScraperService extends BaseScraperService {
  constructor(
    private httpClient: HttpClientService,
    rateLimiter: RateLimiterService,
    private repository: BrickRankerRepository,
  ) {
    super(rateLimiter, "brickranker");
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

    let scrapeSessionId: number | null = null;

    // Create scrape session if saveToDb is true
    if (saveToDb) {
      scrapeSessionId = await this.createScrapeSession({
        source: "brickranker",
        sourceUrl: url,
      });
    }

    try {
      const result = await this.withRetryLogic(
        async (_attempt) => {
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
            await this.saveRawHtml({
              scrapeSessionId,
              source: "brickranker",
              sourceUrl: url,
              rawHtml: response.html,
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
          let stats = undefined;
          if (saveToDb) {
            stats = await this.saveToDatabase(data.items);
          }

          return { data, stats, saved: saveToDb };
        },
        {
          url,
          skipRateLimit,
          domain: "brickranker.com",
          source: "brickranker",
        },
      );

      return {
        success: true,
        data: result.data,
        saved: result.saved,
        stats: result.stats,
        retries: 0,
      };
    } catch (error) {
      return {
        success: false,
        error: error.message || "Unknown error",
      };
    }
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
