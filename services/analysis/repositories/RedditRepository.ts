/**
 * RedditRepository - Data access layer for Reddit data
 * Single Responsibility: Reddit database operations only
 * Follows Repository Pattern for clean architecture
 */

import { eq, inArray } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import {
  type RedditSearchResult,
  redditSearchResults,
} from "../../../db/schema.ts";
import type { IRedditRepository } from "./IRepository.ts";

export class RedditRepository implements IRedditRepository {
  /**
   * Find Reddit search results by LEGO set number
   */
  async findByLegoSetNumber(
    setNumber: string,
  ): Promise<RedditSearchResult | null> {
    try {
      const result = await db
        .select()
        .from(redditSearchResults)
        .where(eq(redditSearchResults.legoSetNumber, setNumber))
        .limit(1);

      return result.length > 0 ? result[0] : null;
    } catch (error) {
      // Gracefully handle missing table or other DB errors
      console.warn(
        `[RedditRepository] Failed to fetch results for set ${setNumber}:`,
        error instanceof Error ? error.message : error,
      );
      return null; // Return null instead of throwing
    }
  }

  /**
   * Find multiple Reddit search results by LEGO set numbers (batch operation)
   * Returns a map of setNumber -> RedditSearchResult for O(1) lookup
   * Solves N+1 query problem
   */
  async findByLegoSetNumbers(
    setNumbers: string[],
  ): Promise<Map<string, RedditSearchResult>> {
    if (setNumbers.length === 0) return new Map();

    try {
      const results = await db
        .select()
        .from(redditSearchResults)
        .where(inArray(redditSearchResults.legoSetNumber, setNumbers));

      // Build map: setNumber -> RedditSearchResult
      const resultMap = new Map<string, RedditSearchResult>();
      for (const result of results) {
        if (result.legoSetNumber) {
          resultMap.set(result.legoSetNumber, result);
        }
      }

      return resultMap;
    } catch (error) {
      console.warn(
        `[RedditRepository] Failed to batch fetch results (count: ${setNumbers.length}):`,
        error instanceof Error ? error.message : error,
      );
      return new Map(); // Return empty map on error
    }
  }
}
