/**
 * RedditSearchService - High-level orchestrator for Reddit searches
 *
 * Responsibilities (Single Responsibility Principle):
 * - Orchestrate Reddit search workflow
 * - Coordinate between HTTP client and repository
 * - Handle errors and retries with circuit breaker
 * - Manage rate limiting
 *
 * This service follows SOLID principles:
 * - SRP: Only handles orchestration logic
 * - OCP: Can be extended without modifying core logic
 * - LSP: Can be substituted with mock for testing
 * - ISP: Focused interface for search operations
 * - DIP: Depends on abstractions (injected dependencies)
 */

import type { HttpClientService } from "../http/HttpClientService.ts";
import type { RateLimiterService } from "../rate-limiter/RateLimiterService.ts";
import type { RedditRepository } from "./RedditRepository.ts";
import { REDDIT_INTERVALS } from "../../config/scraper.config.ts";
import { scraperLogger } from "../../utils/logger.ts";
import { BaseScraperService } from "../base/BaseScraperService.ts";

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
 * Extends BaseScraperService for consistent retry logic and circuit breaker
 */
export class RedditSearchService extends BaseScraperService {
  constructor(
    private httpClient: HttpClientService,
    rateLimiter: RateLimiterService,
    private repository: RedditRepository,
  ) {
    super(rateLimiter, "reddit");
  }

  /**
   * Search Reddit for a LEGO set
   */
  async search(options: SearchOptions): Promise<SearchResult> {
    const { setNumber, subreddit = "lego", saveToDb = false } = options;

    // Create scrape session if saveToDb is true
    if (saveToDb) {
      await this.createScrapeSession({
        source: "reddit" as const,
        sourceUrl:
          `https://www.reddit.com/r/${subreddit}/search?q=${setNumber}`,
      });
    }

    try {
      const result = await this.withRetryLogic(
        async (_attempt) => {
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
            saved,
          };
        },
        {
          url: `https://www.reddit.com/r/${subreddit}/search?q=${setNumber}`,
          skipRateLimit: false,
          domain: "reddit.com",
          source: "reddit",
          context: { setNumber, subreddit },
        },
      );

      return result;
    } catch (error) {
      scraperLogger.error("Reddit search failed after all retries", {
        setNumber,
        subreddit,
        error: (error as Error).message,
        source: "reddit",
      });

      return {
        success: false,
        error: (error as Error).message || "Unknown error",
      };
    }
  }

  /**
   * Search Reddit API using HttpClientService for consistent anti-bot protection
   */
  private async searchRedditAPI(
    setNumber: string,
    subreddit: string,
  ): Promise<RedditPost[]> {
    const searchUrl = `https://www.reddit.com/r/${subreddit}/search.json?q=${
      encodeURIComponent(setNumber)
    }&restrict_sr=on&limit=100&sort=relevance`;

    scraperLogger.info("Fetching Reddit search results", {
      setNumber,
      subreddit,
      url: searchUrl,
      source: "reddit",
    });

    const response = await this.httpClient.simpleFetch({
      url: searchUrl,
      timeout: 30000,
    });

    if (response.status !== 200) {
      throw new Error(`Reddit API error: HTTP ${response.status}`);
    }

    // Parse JSON response
    const data: RedditSearchResponse = JSON.parse(response.html);

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
}

/**
 * Factory function to create RedditSearchService with dependencies
 */
export function createRedditSearchService(
  httpClient: HttpClientService,
  rateLimiter: RateLimiterService,
  repository: RedditRepository,
): RedditSearchService {
  return new RedditSearchService(httpClient, rateLimiter, repository);
}
