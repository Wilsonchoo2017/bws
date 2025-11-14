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
  parsePastSales,
  parsePriceGuide,
} from "./BricklinkParser.ts";
import { calculateBackoff, RETRY_CONFIG } from "../../config/scraper.config.ts";
import { imageDownloadService } from "../image/ImageDownloadService.ts";
import { imageStorageService } from "../image/ImageStorageService.ts";
import {
  IMAGE_CONFIG,
  ImageDownloadStatus,
} from "../../config/image.config.ts";
import { scraperLogger } from "../../utils/logger.ts";
import {
  createCircuitBreaker,
  type RedisCircuitBreaker,
} from "../../utils/RedisCircuitBreaker.ts";
import { db } from "../../db/client.ts";
import { rawDataService } from "../raw-data/index.ts";
import { scrapeSessions } from "../../db/schema.ts";

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
 * BricklinkScraperService - Orchestrates the entire scraping workflow
 */
export class BricklinkScraperService {
  private circuitBreaker: RedisCircuitBreaker;

  constructor(
    private httpClient: HttpClientService,
    private rateLimiter: RateLimiterService,
    private repository: BricklinkRepository,
  ) {
    // Initialize Redis-based circuit breaker for distributed state
    this.circuitBreaker = createCircuitBreaker("bricklink");
  }

  /**
   * Scrape a Bricklink item
   */
  async scrape(options: ScrapeOptions): Promise<ScrapeResult> {
    const { url, saveToDb = false, skipRateLimit = false } = options;

    // Check circuit breaker
    if (await this.circuitBreaker.isCircuitOpen()) {
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
        source: "bricklink",
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

        scraperLogger.info(
          `Scraping attempt ${attempt}/${RETRY_CONFIG.MAX_RETRIES}: ${url}`,
          {
            attempt,
            maxRetries: RETRY_CONFIG.MAX_RETRIES,
            url,
          },
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
        scraperLogger.info("Fetching item page", { itemId, itemType });
        const itemResponse = await this.httpClient.fetch({
          url,
          waitForSelector: "h1#item-name-title",
        });

        if (itemResponse.status !== 200) {
          throw new Error(
            `Failed to fetch item page: HTTP ${itemResponse.status}`,
          );
        }

        // Save raw HTML for item page if saveToDb is true
        if (saveToDb && scrapeSessionId) {
          await rawDataService.saveRawData({
            scrapeSessionId,
            source: "bricklink",
            sourceUrl: url,
            rawHtml: itemResponse.html,
            contentType: "text/html",
            httpStatus: itemResponse.status,
          });
        }

        // Parse item info
        const { title, weight, image_url } = parseItemInfo(itemResponse.html);

        // Build price guide URL
        const priceGuideUrl = buildPriceGuideUrl(itemType, itemId);

        // Rate limiting between requests
        if (!skipRateLimit) {
          await this.rateLimiter.waitForNextRequest({
            domain: "bricklink.com",
          });
        }

        // Fetch price guide page
        scraperLogger.info("Fetching price guide", { itemId, priceGuideUrl });
        const priceResponse = await this.httpClient.fetch({
          url: priceGuideUrl,
          waitForSelector: "#id-main-legacy-table",
        });

        if (priceResponse.status !== 200) {
          throw new Error(
            `Failed to fetch price guide: HTTP ${priceResponse.status}`,
          );
        }

        // Save raw HTML for price guide page if saveToDb is true
        if (saveToDb && scrapeSessionId) {
          await rawDataService.saveRawData({
            scrapeSessionId,
            source: "bricklink",
            sourceUrl: priceGuideUrl,
            rawHtml: priceResponse.html,
            contentType: "text/html",
            httpStatus: priceResponse.status,
          });
        }

        // Parse price guide
        const pricingData = parsePriceGuide(priceResponse.html);

        // Parse past sales transactions from the item page
        scraperLogger.info("Parsing past sales", { itemId });
        const pastSales = parsePastSales(itemResponse.html);
        scraperLogger.info(
          `Found ${pastSales.length} past sales transactions`,
          { itemId, count: pastSales.length },
        );

        // Build complete data object
        const data: BricklinkData = {
          item_id: itemId,
          item_type: itemType,
          title,
          weight,
          image_url,
          ...pricingData,
        };

        scraperLogger.info(`Successfully scraped: ${itemId} - ${title}`, {
          itemId,
          title,
          hasImage: !!image_url,
        });

        // Save to database if requested
        let saved = false;
        if (saveToDb) {
          await this.saveToDatabase(data, pastSales);
          saved = true;
        }

        // Reset circuit breaker on success
        await this.circuitBreaker.recordSuccess();

        return {
          success: true,
          data,
          retries,
          saved,
        };
      } catch (error) {
        lastError = error as Error;
        scraperLogger.error(
          `Scraping attempt ${attempt} failed: ${error.message}`,
          {
            attempt,
            error: error.message,
            stack: error.stack,
            url,
          },
        );

        // If not the last attempt, wait with exponential backoff
        if (attempt < RETRY_CONFIG.MAX_RETRIES) {
          const backoffDelay = calculateBackoff(attempt);
          scraperLogger.info(
            `⏳ Waiting ${backoffDelay / 1000}s before retry...`,
          );
          await this.delay(backoffDelay);
        }
      }
    }

    // All retries failed
    await this.circuitBreaker.recordFailure();

    return {
      success: false,
      error: lastError?.message || "Unknown error",
      retries: RETRY_CONFIG.MAX_RETRIES,
    };
  }

  /**
   * Save scraped data to database
   * Uses transaction to ensure atomicity of multi-step database operations
   *
   * @param data - The Bricklink item data
   * @param pastSales - Array of past sales transactions (optional)
   */
  private async saveToDatabase(
    data: BricklinkData,
    pastSales: import("./BricklinkParser.ts").PastSaleTransaction[] = [],
  ): Promise<void> {
    try {
      // Download and store image if available (outside transaction - file I/O)
      let localImagePath: string | null = null;
      let imageDownloadStatus = ImageDownloadStatus.SKIPPED;

      if (data.image_url && IMAGE_CONFIG.FEATURES.ENABLE_DEDUPLICATION) {
        try {
          scraperLogger.info(`Downloading image: ${data.image_url}`, {
            itemId: data.item_id,
            imageUrl: data.image_url,
          });
          imageDownloadStatus = ImageDownloadStatus.DOWNLOADING;

          const imageData = await imageDownloadService.download(
            data.image_url,
            {
              timeoutMs: IMAGE_CONFIG.DOWNLOAD.TIMEOUT_MS,
              maxRetries: IMAGE_CONFIG.DOWNLOAD.MAX_RETRIES,
              retryDelayMs: IMAGE_CONFIG.DOWNLOAD.RETRY_DELAY_MS,
              allowedFormats: IMAGE_CONFIG.VALIDATION.ALLOWED_FORMATS,
            },
          );

          const storageResult = await imageStorageService.store(
            imageData.data,
            data.image_url,
            imageData.extension,
            data.item_id,
          );

          localImagePath = storageResult.relativePath;
          imageDownloadStatus = ImageDownloadStatus.COMPLETED;
          scraperLogger.info(`Image stored: ${localImagePath}`, {
            itemId: data.item_id,
            localImagePath,
          });
        } catch (error) {
          scraperLogger.error(`Image download failed: ${error.message}`, {
            itemId: data.item_id,
            imageUrl: data.image_url,
            error: error.message,
          });
          imageDownloadStatus = ImageDownloadStatus.FAILED;
          // Continue with scraping even if image download fails
          if (!IMAGE_CONFIG.FEATURES.FALLBACK_TO_EXTERNAL) {
            throw error; // Re-throw if we don't want to continue without image
          }
        }
      }

      // Wrap all database operations in a transaction for atomicity
      await db.transaction(async (_tx) => {
        // Upsert the item
        const { item, isNew } = await this.repository.upsert(
          data.item_id,
          {
            itemType: data.item_type,
            title: data.title,
            weight: data.weight,
            imageUrl: data.image_url,
            localImagePath,
            imageDownloadStatus,
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
          scraperLogger.info(`Created new item: ${data.item_id}`, {
            itemId: data.item_id,
          });
          await this.repository.createPriceHistory({
            itemId: data.item_id,
            sixMonthNew: data.six_month_new,
            sixMonthUsed: data.six_month_used,
            currentNew: data.current_new,
            currentUsed: data.current_used,
          });
          // Also create normalized volume history
          await this.repository.createVolumeHistory({
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
              scraperLogger.info(`Price changed for: ${data.item_id}`, {
                itemId: data.item_id,
              });
              await this.repository.createPriceHistory({
                itemId: data.item_id,
                sixMonthNew: data.six_month_new,
                sixMonthUsed: data.six_month_used,
                currentNew: data.current_new,
                currentUsed: data.current_used,
              });
            } else {
              scraperLogger.info(`No price change for: ${data.item_id}`, {
                itemId: data.item_id,
              });
            }

            // Always record volume history on every scrape (regardless of price change)
            // This allows tracking volume trends over time
            await this.repository.createVolumeHistory({
              itemId: data.item_id,
              sixMonthNew: data.six_month_new,
              sixMonthUsed: data.six_month_used,
              currentNew: data.current_new,
              currentUsed: data.current_used,
            });
          }
        }

        // Save past sales transactions if any were found
        if (pastSales.length > 0) {
          const insertedCount = await this.repository.upsertPastSales(
            data.item_id,
            pastSales,
          );
          scraperLogger.info(
            `Saved ${insertedCount} past sales transactions for ${data.item_id}`,
            {
              itemId: data.item_id,
              totalParsed: pastSales.length,
              inserted: insertedCount,
              duplicatesSkipped: pastSales.length - insertedCount,
            },
          );
        }

        scraperLogger.info(`Saved to database: ${data.item_id}`, {
          itemId: data.item_id,
          isNew,
        });
      });
    } catch (error) {
      scraperLogger.error("Database save failed", {
        itemId: data.item_id,
        error: error.message,
        stack: error.stack,
      });
      throw new Error(`Database save failed: ${error.message}`);
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
