/**
 * RawDataService - High-level service for managing raw scrape data
 *
 * Responsibilities (Single Responsibility Principle):
 * - Orchestrate raw data saving workflow
 * - Handle compression and storage
 * - Provide simple interface for scrapers
 * - Log operations and errors
 *
 * This service follows SOLID principles:
 * - SRP: Only handles raw data operations
 * - OCP: Can be extended without modifying core logic
 * - LSP: Can be substituted with mock for testing
 * - ISP: Focused interface for raw data operations
 * - DIP: Depends on abstractions (ScrapeRawDataRepository)
 */

import type { ScrapeRawDataRepository } from "../../db/repositories/ScrapeRawDataRepository.ts";
import { scraperLogger } from "../../utils/logger.ts";

/**
 * Options for saving raw data
 */
export interface SaveRawDataOptions {
  scrapeSessionId: number;
  source:
    | "shopee"
    | "toysrus"
    | "brickeconomy"
    | "bricklink"
    | "worldbricks"
    | "brickranker"
    | "reddit"
    | "self";
  sourceUrl: string;
  rawHtml: string;
  contentType?: string;
  httpStatus?: number;
}

/**
 * RawDataService - Handles saving and retrieving raw scrape data
 */
export class RawDataService {
  constructor(
    private repository: ScrapeRawDataRepository,
  ) {}

  /**
   * Save raw HTML/API response data
   * Handles compression, storage, and error logging
   */
  async saveRawData(options: SaveRawDataOptions): Promise<void> {
    try {
      await this.repository.saveRawData({
        scrapeSessionId: options.scrapeSessionId,
        source: options.source,
        sourceUrl: options.sourceUrl,
        rawHtml: options.rawHtml,
        contentType: options.contentType || "text/html",
        httpStatus: options.httpStatus,
      });

      scraperLogger.info(`Saved raw HTML for ${options.source}`, {
        sessionId: options.scrapeSessionId,
        source: options.source,
        url: options.sourceUrl,
        size: options.rawHtml.length,
      });
    } catch (error) {
      // Log error but don't throw - raw data saving shouldn't break scraping
      scraperLogger.error(`Failed to save raw HTML for ${options.source}`, {
        sessionId: options.scrapeSessionId,
        source: options.source,
        error: (error as Error).message,
        stack: (error as Error).stack,
      });
    }
  }

  /**
   * Get raw data by ID with decompression
   */
  async getRawDataById(id: number) {
    return await this.repository.getRawDataById(id);
  }

  /**
   * Get all raw data for a session
   */
  async getRawDataBySession(sessionId: number) {
    return await this.repository.getRawDataBySession(sessionId);
  }

  /**
   * Get compression analytics
   */
  async getCompressionAnalytics(source?: SaveRawDataOptions["source"]) {
    return await this.repository.getCompressionAnalytics(source);
  }
}
