/**
 * API endpoint for retrieving raw HTML/API response data
 * GET /api/raw-data/:id - Get raw HTML by ID
 */

import { FreshContext } from "$fresh/server.ts";
import { rawDataService } from "../../../services/raw-data/index.ts";

export const handler = async (
  _req: Request,
  ctx: FreshContext,
): Promise<Response> => {
  try {
    const id = parseInt(ctx.params.id);

    if (isNaN(id)) {
      return new Response(
        JSON.stringify({ error: "Invalid ID parameter" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    const rawData = await rawDataService.getRawDataById(id);

    if (!rawData) {
      return new Response(
        JSON.stringify({ error: `Raw data with ID ${id} not found` }),
        {
          status: 404,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Return the raw HTML with metadata
    return new Response(
      JSON.stringify(
        {
          id: rawData.id,
          scrapeSessionId: rawData.scrapeSessionId,
          source: rawData.source,
          sourceUrl: rawData.sourceUrl,
          contentType: rawData.contentType,
          httpStatus: rawData.httpStatus,
          scrapedAt: rawData.scrapedAt,
          rawHtmlSize: rawData.rawHtmlSize,
          compressedSize: rawData.compressedSize,
          compressionRatio: (rawData.compressedSize / rawData.rawHtmlSize).toFixed(3),
          rawHtml: rawData.rawHtml,
        },
        null,
        2,
      ),
      {
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Unknown error",
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
};
