/**
 * ScrapeRawDataRepository - Database access layer for raw scrape data
 *
 * Responsibilities (Single Responsibility Principle):
 * - CRUD operations for scrape_raw_data table
 * - Compression/decompression of HTML data
 * - Query building and execution
 * - Analytics on compression efficiency
 *
 * This service follows SOLID principles:
 * - SRP: Only handles database operations for raw scrape data
 * - OCP: Can be extended without modifying core logic
 * - DIP: Depends on database abstraction (Drizzle ORM)
 * - ISP: Focused interface for raw scrape data
 */

import { db } from "../client.ts";
import {
  type NewScrapeRawData,
  type ScrapeRawData,
  scrapeRawData,
} from "../schema.ts";
import { and, desc, eq } from "drizzle-orm";
import {
  compressHtml,
  decompressHtml,
  getCompressionStats,
} from "../../utils/compression.ts";

/**
 * Input data for saving raw HTML
 */
export interface SaveRawDataInput {
  scrapeSessionId: number;
  source:
    | "shopee"
    | "toysrus"
    | "brickeconomy"
    | "bricklink"
    | "worldbricks"
    | "brickranker"
    | "self";
  sourceUrl: string;
  rawHtml: string;
  contentType?: string;
  httpStatus?: number;
}

/**
 * Raw data with decompressed HTML
 */
export interface RawDataWithHtml
  extends Omit<ScrapeRawData, "rawHtmlCompressed"> {
  rawHtml: string;
}

/**
 * Compression statistics for analytics
 */
export interface CompressionAnalytics {
  totalRecords: number;
  totalOriginalSize: number;
  totalCompressedSize: number;
  totalSavedBytes: number;
  averageCompressionRatio: number;
  averageCompressionPercent: number;
}

/**
 * ScrapeRawDataRepository - Handles all database operations for raw scrape data
 */
export class ScrapeRawDataRepository {
  /**
   * Save raw HTML/data with automatic compression
   */
  async saveRawData(input: SaveRawDataInput): Promise<ScrapeRawData> {
    // Compress the HTML
    const compressed = compressHtml(input.rawHtml);

    // Prepare data for insertion
    const data: NewScrapeRawData = {
      scrapeSessionId: input.scrapeSessionId,
      source: input.source,
      sourceUrl: input.sourceUrl,
      rawHtmlCompressed: compressed.compressed,
      rawHtmlSize: compressed.originalSize,
      compressedSize: compressed.compressedSize,
      contentType: input.contentType || "text/html",
      httpStatus: input.httpStatus,
    };

    // Insert into database
    const [result] = await db.insert(scrapeRawData).values(data).returning();

    return result;
  }

  /**
   * Get raw data by ID with decompressed HTML
   */
  async getRawDataById(id: number): Promise<RawDataWithHtml | undefined> {
    const record = await db.query.scrapeRawData.findFirst({
      where: eq(scrapeRawData.id, id),
    });

    if (!record) {
      return undefined;
    }

    // Decompress HTML
    const rawHtml = decompressHtml(record.rawHtmlCompressed);

    // Return with decompressed HTML
    const { rawHtmlCompressed: _, ...rest } = record;
    return {
      ...rest,
      rawHtml,
    };
  }

  /**
   * Get all raw data for a scrape session with decompressed HTML
   */
  async getRawDataBySession(
    scrapeSessionId: number,
  ): Promise<RawDataWithHtml[]> {
    const records = await db.query.scrapeRawData.findMany({
      where: eq(scrapeRawData.scrapeSessionId, scrapeSessionId),
      orderBy: [desc(scrapeRawData.scrapedAt)],
    });

    // Decompress all records
    const decompressed = records.map((record) => {
      const rawHtml = decompressHtml(record.rawHtmlCompressed);
      const { rawHtmlCompressed: _, ...rest } = record;
      return {
        ...rest,
        rawHtml,
      };
    });

    return decompressed;
  }

  /**
   * Get all raw data for a source with decompressed HTML
   */
  async getRawDataBySource(
    source: SaveRawDataInput["source"],
    limit = 50,
  ): Promise<RawDataWithHtml[]> {
    const records = await db.query.scrapeRawData.findMany({
      where: eq(scrapeRawData.source, source),
      orderBy: [desc(scrapeRawData.scrapedAt)],
      limit,
    });

    // Decompress all records
    const decompressed = records.map((record) => {
      const rawHtml = decompressHtml(record.rawHtmlCompressed);
      const { rawHtmlCompressed: _, ...rest } = record;
      return {
        ...rest,
        rawHtml,
      };
    });

    return decompressed;
  }

  /**
   * Get raw data by session and source
   */
  async getRawDataBySessionAndSource(
    scrapeSessionId: number,
    source: SaveRawDataInput["source"],
  ): Promise<RawDataWithHtml[]> {
    const records = await db.query.scrapeRawData.findMany({
      where: and(
        eq(scrapeRawData.scrapeSessionId, scrapeSessionId),
        eq(scrapeRawData.source, source),
      ),
      orderBy: [desc(scrapeRawData.scrapedAt)],
    });

    // Decompress all records
    const decompressed = records.map((record) => {
      const rawHtml = decompressHtml(record.rawHtmlCompressed);
      const { rawHtmlCompressed: _, ...rest } = record;
      return {
        ...rest,
        rawHtml,
      };
    });

    return decompressed;
  }

  /**
   * Delete raw data by ID
   */
  async deleteRawData(id: number): Promise<boolean> {
    await db.delete(scrapeRawData).where(
      eq(scrapeRawData.id, id),
    );

    return true;
  }

  /**
   * Delete all raw data for a scrape session
   */
  async deleteRawDataBySession(scrapeSessionId: number): Promise<boolean> {
    await db.delete(scrapeRawData).where(
      eq(scrapeRawData.scrapeSessionId, scrapeSessionId),
    );

    return true;
  }

  /**
   * Get compression statistics for analytics
   */
  async getCompressionAnalytics(
    source?: SaveRawDataInput["source"],
  ): Promise<CompressionAnalytics> {
    const whereClause = source ? eq(scrapeRawData.source, source) : undefined;

    const records = await db.query.scrapeRawData.findMany({
      where: whereClause,
      columns: {
        rawHtmlSize: true,
        compressedSize: true,
      },
    });

    if (records.length === 0) {
      return {
        totalRecords: 0,
        totalOriginalSize: 0,
        totalCompressedSize: 0,
        totalSavedBytes: 0,
        averageCompressionRatio: 0,
        averageCompressionPercent: 0,
      };
    }

    const totalOriginalSize = records.reduce(
      (sum, r) => sum + r.rawHtmlSize,
      0,
    );
    const totalCompressedSize = records.reduce(
      (sum, r) => sum + r.compressedSize,
      0,
    );

    const stats = getCompressionStats(totalOriginalSize, totalCompressedSize);

    return {
      totalRecords: records.length,
      totalOriginalSize,
      totalCompressedSize,
      totalSavedBytes: stats.savedBytes,
      averageCompressionRatio: stats.compressionRatio,
      averageCompressionPercent: stats.compressionPercent,
    };
  }

  /**
   * Get metadata only (without decompressing HTML) - useful for listing
   */
  async getRawDataMetadata(
    scrapeSessionId?: number,
    limit = 100,
  ): Promise<Omit<ScrapeRawData, "rawHtmlCompressed">[]> {
    const whereClause = scrapeSessionId
      ? eq(scrapeRawData.scrapeSessionId, scrapeSessionId)
      : undefined;

    const records = await db.query.scrapeRawData.findMany({
      where: whereClause,
      orderBy: [desc(scrapeRawData.scrapedAt)],
      limit,
      columns: {
        rawHtmlCompressed: false, // Exclude compressed data
      },
    });

    return records as Omit<ScrapeRawData, "rawHtmlCompressed">[];
  }
}
