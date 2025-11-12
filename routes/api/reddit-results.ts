/**
 * Reddit results API endpoint
 * Fetches Reddit search results from database
 */

import { FreshContext } from "$fresh/server.ts";
import { getRedditRepository } from "../../services/reddit/RedditRepository.ts";
import {
  createErrorResponse,
  createJsonResponse,
  createNotFoundResponse,
  createValidationErrorResponse,
} from "../../utils/api-helpers.ts";

export const handler = {
  // GET /api/reddit-results?set=75192 - Get results for a specific set
  // GET /api/reddit-results - Get all results (paginated)
  async GET(req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const url = new URL(req.url);
      const setNumber = url.searchParams.get("set");
      const subreddit = url.searchParams.get("subreddit");
      const limit = parseInt(url.searchParams.get("limit") || "50");
      const offset = parseInt(url.searchParams.get("offset") || "0");

      const repository = getRedditRepository();

      if (setNumber) {
        // Get results for specific set
        const results = await repository.findBySetNumber(setNumber, {
          limit,
          offset,
        });

        if (results.length === 0) {
          return createNotFoundResponse(
            `No Reddit search results found for set ${setNumber}`,
          );
        }

        // Return the most recent result
        return createJsonResponse(results[0]);
      }

      if (subreddit) {
        // Get results by subreddit
        const results = await repository.findBySubreddit(subreddit, {
          limit,
          offset,
        });

        return createJsonResponse({
          subreddit,
          total: results.length,
          results,
        });
      }

      // Get all results
      const results = await repository.findAll({ limit, offset });
      const total = await repository.count();

      return createJsonResponse({
        total,
        limit,
        offset,
        results,
      });
    } catch (error) {
      return createErrorResponse(error, "Error fetching Reddit results");
    }
  },

  // DELETE /api/reddit-results?set=75192 - Delete results for a specific set
  // DELETE /api/reddit-results?id=123 - Delete a specific result by ID
  async DELETE(req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const url = new URL(req.url);
      const setNumber = url.searchParams.get("set");
      const id = url.searchParams.get("id");

      const repository = getRedditRepository();

      if (id) {
        // Delete specific result by ID
        const numericId = parseInt(id);
        if (isNaN(numericId)) {
          return createValidationErrorResponse("Invalid ID parameter");
        }

        await repository.delete(numericId);
        return createJsonResponse({ success: true, message: "Result deleted" });
      }

      if (setNumber) {
        // Delete all results for a set
        await repository.deleteBySetNumber(setNumber);
        return createJsonResponse({
          success: true,
          message: `All results for set ${setNumber} deleted`,
        });
      }

      return createValidationErrorResponse(
        "Missing 'set' or 'id' query parameter",
      );
    } catch (error) {
      return createErrorResponse(error, "Error deleting Reddit results");
    }
  },
};
