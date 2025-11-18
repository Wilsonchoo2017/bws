/**
 * API endpoint to fetch scraping logs for a specific product
 * GET /api/scraping-logs/product/:productId
 */

import type { Handlers } from "$fresh/server.ts";
import { ScrapingLogsRepository } from "../../../../db/repositories/ScrapingLogsRepository.ts";

export const handler: Handlers = {
  async GET(_req, ctx) {
    const { productId } = ctx.params;

    if (!productId) {
      return new Response(
        JSON.stringify({ error: "Product ID is required" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    try {
      const repository = new ScrapingLogsRepository();
      const logs = await repository.getScrapingLogsByProductId(productId, 20);

      return new Response(JSON.stringify({ logs }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      console.error("Error fetching scraping logs:", error);
      return new Response(
        JSON.stringify({
          error: "Failed to fetch scraping logs",
          message: error instanceof Error ? error.message : "Unknown error",
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
  },
};
