/**
 * RedditSearchService - High-level orchestrator for Reddit searches
 *
 * Responsibilities (Single Responsibility Principle):
 * - Orchestrate Reddit search workflow
 * - Coordinate between HTTP client and repository
 * - Handle errors and retries
 * - Manage rate limiting
 *
 * This service follows SOLID principles:
 * - SRP: Only handles orchestration logic
 * - OCP: Can be extended without modifying core logic
 * - LSP: Can be substituted with mock for testing
 * - ISP: Focused interface for search operations
 * - DIP: Depends on abstractions (injected dependencies)
 */

import type { RateLimiterService } from "../rate-limiter/RateLimiterService.ts";
import type { RedditRepository } from "./RedditRepository.ts";
import {
  calculateBackoff,
  REDDIT_INTERVALS,
  RETRY_CONFIG,
} from "../../config/scraper.config.ts";
import { scraperLogger } from "../../utils/logger.ts";

/**
 * Reddit post interface
 */
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
 * Reddit API response interface
 */
interface RedditSearchResponse {
  kind: string;
  data: {
    children: Array<{
      kind: string;
      data: RedditPost;
    }>;
    after: string | null;
  };
}

/**
 * Result of a search operation
 */
export interface SearchResult {
  success: boolean;
  setNumber?: string;
  subreddit?: string;
  totalPosts?: number;
  posts?: RedditPost[];
  error?: string;
  retries?: number;
  saved?: boolean;
}

/**
 * Options for searching
 */
export interface SearchOptions {
  setNumber: string;
  subreddit?: string;
  saveToDb?: boolean;
}

/**
 * RedditSearchService - Orchestrates the entire search workflow
 */
export class RedditSearchService {
  constructor(
    private rateLimiter: RateLimiterService,
    private repository: RedditRepository,
  ) {}

  /**
   * Search Reddit for a LEGO set
   */
  async search(options: SearchOptions): Promise<SearchResult> {
    const { setNumber, subreddit = "lego", saveToDb = false } = options;

    let lastError: Error | null = null;
    let retries = 0;

    // Retry loop with exponential backoff
    for (let attempt = 1; attempt <= RETRY_CONFIG.MAX_RETRIES; attempt++) {
      try {
        retries = attempt - 1;

        scraperLogger.info("Starting Reddit search attempt", {
          setNumber,
          subreddit,
          attempt,
          maxRetries: RETRY_CONFIG.MAX_RETRIES,
          source: "reddit",
        });

        // Rate limiting
        await this.rateLimiter.waitForNextRequest({
          domain: "reddit.com",
        });

        // Search Reddit
        const posts = await this.searchRedditAPI(setNumber, subreddit);

        scraperLogger.info("Reddit search completed successfully", {
          setNumber,
          subreddit,
          postsFound: posts.length,
          source: "reddit",
        });

        // Save to database if requested
        let saved = false;
        if (saveToDb) {
          await this.saveToDatabase(setNumber, subreddit, posts);
          saved = true;
        }

        return {
          success: true,
          setNumber,
          subreddit,
          totalPosts: posts.length,
          posts,
          retries,
          saved,
        };
      } catch (error) {
        lastError = error as Error;
        scraperLogger.error("Reddit search attempt failed", {
          setNumber,
          subreddit,
          attempt,
          maxRetries: RETRY_CONFIG.MAX_RETRIES,
          error: error.message,
          stack: error.stack,
          source: "reddit",
        });

        // If not the last attempt, wait with exponential backoff
        if (attempt < RETRY_CONFIG.MAX_RETRIES) {
          const backoffDelay = calculateBackoff(attempt);
          scraperLogger.info("Waiting before retry with exponential backoff", {
            setNumber,
            subreddit,
            backoffMs: backoffDelay,
            backoffSeconds: backoffDelay / 1000,
            nextAttempt: attempt + 1,
            source: "reddit",
          });
          await this.delay(backoffDelay);
        }
      }
    }

    // All retries failed
    scraperLogger.error("All Reddit search attempts failed", {
      setNumber,
      subreddit,
      totalAttempts: RETRY_CONFIG.MAX_RETRIES,
      finalError: lastError?.message || "Unknown error",
      source: "reddit",
    });

    return {
      success: false,
      error: lastError?.message || "Unknown error",
      retries: RETRY_CONFIG.MAX_RETRIES,
    };
  }

  /**
   * Search Reddit API
   */
  private async searchRedditAPI(
    setNumber: string,
    subreddit: string,
  ): Promise<RedditPost[]> {
    const searchUrl = `https://www.reddit.com/r/${subreddit}/search.json?q=${
      encodeURIComponent(setNumber)
    }&restrict_sr=on&limit=100&sort=relevance`;

    const headers = {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    };

    const response = await fetch(searchUrl, { headers });

    if (!response.ok) {
      throw new Error(`Reddit API error: ${response.statusText}`);
    }

    const data: RedditSearchResponse = await response.json();

    return data.data.children.map((child) => ({
      id: child.data.id,
      title: child.data.title,
      author: child.data.author,
      score: child.data.score,
      num_comments: child.data.num_comments,
      url: child.data.url,
      permalink: `https://reddit.com${child.data.permalink}`,
      created_utc: child.data.created_utc,
      selftext: child.data.selftext || undefined,
    }));
  }

  /**
   * Save search results to database with scheduling timestamps
   */
  private async saveToDatabase(
    setNumber: string,
    subreddit: string,
    posts: RedditPost[],
  ): Promise<void> {
    try {
      const now = new Date();
      const nextScrape = new Date(
        now.getTime() +
          REDDIT_INTERVALS.DEFAULT_INTERVAL_DAYS * 24 * 60 * 60 * 1000,
      );

      scraperLogger.info("Saving Reddit search results to database", {
        setNumber,
        subreddit,
        postsCount: posts.length,
        nextScrapeAt: nextScrape.toISOString(),
        source: "reddit",
      });

      await this.repository.create({
        legoSetNumber: setNumber,
        subreddit,
        totalPosts: posts.length,
        posts: posts as unknown as Record<string, unknown>,
        watchStatus: "active",
        scrapeIntervalDays: REDDIT_INTERVALS.DEFAULT_INTERVAL_DAYS,
        lastScrapedAt: now,
        nextScrapeAt: nextScrape,
        searchedAt: now,
        createdAt: now,
        updatedAt: now,
      });

      scraperLogger.info("Successfully saved Reddit search results", {
        setNumber,
        subreddit,
        postsCount: posts.length,
        nextScrapeAt: nextScrape.toISOString(),
        source: "reddit",
      });
    } catch (error) {
      scraperLogger.error("Failed to save Reddit search results to database", {
        setNumber,
        subreddit,
        error: (error as Error).message,
        stack: (error as Error).stack,
        source: "reddit",
      });
      throw new Error(`Database save failed: ${error.message}`);
    }
  }

  /**
   * Delay helper
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

/**
 * Factory function to create RedditSearchService with dependencies
 */
export function createRedditSearchService(
  rateLimiter: RateLimiterService,
  repository: RedditRepository,
): RedditSearchService {
  return new RedditSearchService(rateLimiter, repository);
}
