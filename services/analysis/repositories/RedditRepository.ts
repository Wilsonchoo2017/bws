/**
 * RedditRepository - Data access layer for Reddit data
 * Single Responsibility: Reddit database operations only
 * Follows Repository Pattern for clean architecture
 */

import { eq } from "drizzle-orm";
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
}
