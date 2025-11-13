/**
 * RedditRepository - Database access layer for Reddit search results
 *
 * Responsibilities (Single Responsibility Principle):
 * - CRUD operations for reddit_search_results table
 * - Query building and execution
 * - Transaction management
 *
 * This service follows SOLID principles:
 * - SRP: Only handles database operations
 * - OCP: Can be extended without modifying core logic
 * - DIP: Depends on database abstraction (Drizzle ORM)
 * - ISP: Focused interface for Reddit data
 */

import { db } from "../../db/client.ts";
import {
  type NewRedditSearchResult,
  type RedditSearchResult,
  redditSearchResults,
} from "../../db/schema.ts";
import { and, desc, eq, lte, or, sql } from "drizzle-orm";

export interface RedditPost {
  id: string;
  title: string;
  author: string;
  score: number;
  num_comments: number;
  url: string;
  permalink: string;
  created_utc: number;
  selftext?: string;
}

/**
 * RedditRepository - Handles all database operations for Reddit search results
 */
export class RedditRepository {
  /**
   * Find search results by LEGO set number
   */
  async findBySetNumber(
    setNumber: string,
    options: { limit?: number; offset?: number } = {},
  ): Promise<RedditSearchResult[]> {
    const limit = options.limit || 50;
    const offset = options.offset || 0;

    return await db.select()
      .from(redditSearchResults)
      .where(eq(redditSearchResults.legoSetNumber, setNumber))
      .orderBy(desc(redditSearchResults.searchedAt))
      .limit(limit)
      .offset(offset);
  }

  /**
   * Find the most recent search result for a set number
   */
  async findLatestBySetNumber(
    setNumber: string,
  ): Promise<RedditSearchResult | undefined> {
    return await db.query.redditSearchResults.findFirst({
      where: eq(redditSearchResults.legoSetNumber, setNumber),
      orderBy: desc(redditSearchResults.searchedAt),
    });
  }

  /**
   * Find search result by ID
   */
  async findById(id: number): Promise<RedditSearchResult | undefined> {
    return await db.query.redditSearchResults.findFirst({
      where: eq(redditSearchResults.id, id),
    });
  }

  /**
   * Create a new search result
   */
  async create(data: NewRedditSearchResult): Promise<RedditSearchResult> {
    const [result] = await db.insert(redditSearchResults)
      .values(data)
      .returning();

    return result;
  }

  /**
   * Create or update search result (atomic upsert using ON CONFLICT)
   * This prevents race conditions in concurrent environments
   *
   * Once the unique constraint on (legoSetNumber, subreddit) is added,
   * this will use that for conflict resolution. Until then, it will
   * insert duplicates (which we'll clean up with the migration).
   */
  async upsert(data: {
    legoSetNumber: string;
    subreddit: string;
    totalPosts: number;
    posts: unknown; // JSONB array of post objects
    scrapeIntervalDays?: number;
  }): Promise<{ result: RedditSearchResult; isNew: boolean }> {
    const now = new Date();
    const intervalDays = data.scrapeIntervalDays || 30;
    const nextScrape = new Date(
      now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
    );

    const insertData: NewRedditSearchResult = {
      legoSetNumber: data.legoSetNumber,
      subreddit: data.subreddit,
      totalPosts: data.totalPosts,
      posts: data.posts,
      searchedAt: now,
      scrapeIntervalDays: intervalDays,
      lastScrapedAt: now,
      nextScrapeAt: nextScrape,
    };

    // Note: This will work properly once we add the unique constraint on (legoSetNumber, subreddit)
    // Until then, this may create duplicates, but the migration will clean them up
    const [result] = await db
      .insert(redditSearchResults)
      .values(insertData)
      .onConflictDoUpdate({
        // TODO: This will be updated to use composite key once migration is applied
        // For now, this won't trigger because there's no unique constraint yet
        target: [
          redditSearchResults.legoSetNumber,
          redditSearchResults.subreddit,
        ],
        set: {
          totalPosts: data.totalPosts,
          posts: data.posts,
          searchedAt: now,
          lastScrapedAt: now,
          nextScrapeAt: nextScrape,
          updatedAt: now,
        },
      })
      .returning();

    // Determine if this was a new insert by checking timestamps
    const isNew = result.createdAt.getTime() === result.updatedAt.getTime();

    return { result, isNew };
  }

  /**
   * Delete a search result by ID
   */
  async delete(id: number): Promise<boolean> {
    await db.delete(redditSearchResults)
      .where(eq(redditSearchResults.id, id));

    return true;
  }

  /**
   * Delete all search results for a set number
   */
  async deleteBySetNumber(setNumber: string): Promise<boolean> {
    await db.delete(redditSearchResults)
      .where(eq(redditSearchResults.legoSetNumber, setNumber));

    return true;
  }

  /**
   * Get all unique LEGO set numbers that have been searched
   */
  async getAllSearchedSetNumbers(): Promise<string[]> {
    const results = await db.selectDistinct({
      setNumber: redditSearchResults.legoSetNumber,
    })
      .from(redditSearchResults);

    return results.map((r) => r.setNumber);
  }

  /**
   * Count total searches
   */
  async count(): Promise<number> {
    const result = await db.select()
      .from(redditSearchResults);

    return result.length;
  }

  /**
   * Count searches by set number
   */
  async countBySetNumber(setNumber: string): Promise<number> {
    const result = await db.select()
      .from(redditSearchResults)
      .where(eq(redditSearchResults.legoSetNumber, setNumber));

    return result.length;
  }

  /**
   * Get all search results with pagination
   */
  async findAll(
    options: {
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<RedditSearchResult[]> {
    const limit = options.limit || 50;
    const offset = options.offset || 0;

    return await db.select()
      .from(redditSearchResults)
      .orderBy(desc(redditSearchResults.searchedAt))
      .limit(limit)
      .offset(offset);
  }

  /**
   * Find all searches by subreddit
   */
  async findBySubreddit(
    subreddit: string,
    options: { limit?: number; offset?: number } = {},
  ): Promise<RedditSearchResult[]> {
    const limit = options.limit || 50;
    const offset = options.offset || 0;

    return await db.select()
      .from(redditSearchResults)
      .where(eq(redditSearchResults.subreddit, subreddit))
      .orderBy(desc(redditSearchResults.searchedAt))
      .limit(limit)
      .offset(offset);
  }

  /**
   * Find searches that need scraping based on schedule
   * Returns searches where:
   * - watch_status = 'active'
   * - next_scrape_at IS NULL OR next_scrape_at <= now
   */
  async findSearchesNeedingScraping(): Promise<RedditSearchResult[]> {
    const now = new Date();

    return await db.select()
      .from(redditSearchResults)
      .where(
        and(
          eq(redditSearchResults.watchStatus, "active"),
          or(
            sql`${redditSearchResults.nextScrapeAt} IS NULL`,
            lte(redditSearchResults.nextScrapeAt, now),
          ),
        ),
      );
  }

  /**
   * Update scheduling timestamps after a successful scrape
   */
  async updateNextScrapeTime(
    id: number,
    intervalDays: number,
  ): Promise<RedditSearchResult> {
    const now = new Date();
    const nextScrape = new Date(
      now.getTime() + intervalDays * 24 * 60 * 60 * 1000,
    );

    const [updated] = await db.update(redditSearchResults)
      .set({
        lastScrapedAt: now,
        nextScrapeAt: nextScrape,
        searchedAt: now,
        updatedAt: now,
      })
      .where(eq(redditSearchResults.id, id))
      .returning();

    return updated;
  }

  /**
   * Update watch status for a search result
   */
  async updateWatchStatus(
    id: number,
    watchStatus: "active" | "paused" | "stopped" | "archived",
  ): Promise<RedditSearchResult> {
    const [updated] = await db.update(redditSearchResults)
      .set({
        watchStatus,
        updatedAt: new Date(),
      })
      .where(eq(redditSearchResults.id, id))
      .returning();

    return updated;
  }

  /**
   * Update scrape interval for a search result
   */
  async updateScrapeInterval(
    id: number,
    intervalDays: number,
  ): Promise<RedditSearchResult> {
    const [updated] = await db.update(redditSearchResults)
      .set({
        scrapeIntervalDays: intervalDays,
        updatedAt: new Date(),
      })
      .where(eq(redditSearchResults.id, id))
      .returning();

    return updated;
  }
}

/**
 * Singleton instance for reuse across the application
 */
let repositoryInstance: RedditRepository | null = null;

/**
 * Get the singleton RedditRepository instance
 */
export function getRedditRepository(): RedditRepository {
  if (!repositoryInstance) {
    repositoryInstance = new RedditRepository();
  }
  return repositoryInstance;
}
