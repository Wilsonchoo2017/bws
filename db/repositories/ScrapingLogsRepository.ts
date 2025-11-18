/**
 * ScrapingLogsRepository - Database access layer for scraping session logs
 *
 * Responsibilities (Single Responsibility Principle):
 * - Query scrape_sessions table
 * - Join with product-related tables to get scraping history
 * - Format and aggregate scraping logs for display
 *
 * This service follows SOLID principles:
 * - SRP: Only handles database operations for scraping logs
 * - OCP: Can be extended without modifying core logic
 * - DIP: Depends on database abstraction (Drizzle ORM)
 * - ISP: Focused interface for scraping logs
 */

import { db } from "../client.ts";
import { scrapeSessions, shopeeScrapes } from "../schema.ts";
import { desc, eq } from "drizzle-orm";

/**
 * Scraping log entry with session metadata
 */
export interface ScrapingLogEntry {
  id: number;
  source: string;
  sourceUrl: string | null;
  productsFound: number;
  productsStored: number;
  status: string;
  errorMessage: string | null;
  sessionLabel: string | null;
  shopName: string | null;
  scrapedAt: Date;
}

/**
 * ScrapingLogsRepository - Handles all database operations for scraping logs
 */
export class ScrapingLogsRepository {
  /**
   * Get scraping logs for a specific product
   * Returns sessions that scraped this product, ordered by most recent first
   */
  async getScrapingLogsByProductId(
    productId: string,
    limit = 20,
  ): Promise<ScrapingLogEntry[]> {
    // Query shopee_scrapes to find session IDs that scraped this product
    const shopeeScrapeRecords = await db.query.shopeeScrapes.findMany({
      where: eq(shopeeScrapes.productId, productId),
      columns: {
        scrapeSessionId: true,
      },
    });

    // Extract unique session IDs
    const sessionIds = [
      ...new Set(
        shopeeScrapeRecords
          .map((r) => r.scrapeSessionId)
          .filter((id): id is number => id !== null),
      ),
    ];

    // If no sessions found, return empty array
    if (sessionIds.length === 0) {
      return [];
    }

    // Get session details for these session IDs
    const sessions = await db.query.scrapeSessions.findMany({
      where: (scrapeSessions, { inArray }) =>
        inArray(scrapeSessions.id, sessionIds),
      orderBy: [desc(scrapeSessions.scrapedAt)],
      limit,
    });

    // Map to ScrapingLogEntry format
    return sessions.map((session) => ({
      id: session.id,
      source: session.source,
      sourceUrl: session.sourceUrl,
      productsFound: session.productsFound,
      productsStored: session.productsStored,
      status: session.status,
      errorMessage: session.errorMessage,
      sessionLabel: session.sessionLabel,
      shopName: session.shopName,
      scrapedAt: session.scrapedAt,
    }));
  }

  /**
   * Get recent scraping sessions across all sources
   */
  async getRecentScrapingSessions(limit = 50): Promise<ScrapingLogEntry[]> {
    const sessions = await db.query.scrapeSessions.findMany({
      orderBy: [desc(scrapeSessions.scrapedAt)],
      limit,
    });

    return sessions.map((session) => ({
      id: session.id,
      source: session.source,
      sourceUrl: session.sourceUrl,
      productsFound: session.productsFound,
      productsStored: session.productsStored,
      status: session.status,
      errorMessage: session.errorMessage,
      sessionLabel: session.sessionLabel,
      shopName: session.shopName,
      scrapedAt: session.scrapedAt,
    }));
  }

  /**
   * Get scraping sessions by source
   */
  async getScrapingSessionsBySource(
    source: string,
    limit = 50,
  ): Promise<ScrapingLogEntry[]> {
    const sessions = await db.query.scrapeSessions.findMany({
      where: eq(scrapeSessions.source, source),
      orderBy: [desc(scrapeSessions.scrapedAt)],
      limit,
    });

    return sessions.map((session) => ({
      id: session.id,
      source: session.source,
      sourceUrl: session.sourceUrl,
      productsFound: session.productsFound,
      productsStored: session.productsStored,
      status: session.status,
      errorMessage: session.errorMessage,
      sessionLabel: session.sessionLabel,
      shopName: session.shopName,
      scrapedAt: session.scrapedAt,
    }));
  }

  /**
   * Get a single scraping session by ID
   */
  async getScrapingSessionById(
    id: number,
  ): Promise<ScrapingLogEntry | undefined> {
    const session = await db.query.scrapeSessions.findFirst({
      where: eq(scrapeSessions.id, id),
    });

    if (!session) {
      return undefined;
    }

    return {
      id: session.id,
      source: session.source,
      sourceUrl: session.sourceUrl,
      productsFound: session.productsFound,
      productsStored: session.productsStored,
      status: session.status,
      errorMessage: session.errorMessage,
      sessionLabel: session.sessionLabel,
      shopName: session.shopName,
      scrapedAt: session.scrapedAt,
    };
  }
}
