/**
 * API endpoint for retrieving raw HTML/API response data by session
 * GET /api/raw-data/session/:sessionId - Get all raw HTML for a scrape session
 */

import { FreshContext } from "$fresh/server.ts";
import { rawDataService } from "../../../../services/raw-data/index.ts";

export const handler = async (
  _req: Request,
  ctx: FreshContext,
): Promise<Response> => {
  try {
    const sessionId = parseInt(ctx.params.sessionId);

    if (isNaN(sessionId)) {
      return new Response(
        JSON.stringify({ error: "Invalid session ID parameter" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    const rawDataList = await rawDataService.getRawDataBySession(sessionId);

    if (rawDataList.length === 0) {
      return new Response(
        JSON.stringify({
          error: `No raw data found for session ${sessionId}`,
        }),
        {
          status: 404,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Return all raw HTML entries with metadata
    return new Response(
      JSON.stringify(
        {
          sessionId,
          count: rawDataList.length,
          data: rawDataList.map((item) => ({
            id: item.id,
            source: item.source,
            sourceUrl: item.sourceUrl,
            contentType: item.contentType,
            httpStatus: item.httpStatus,
            scrapedAt: item.scrapedAt,
            rawHtmlSize: item.rawHtmlSize,
            compressedSize: item.compressedSize,
            compressionRatio: (item.compressedSize / item.rawHtmlSize).toFixed(
              3,
            ),
            rawHtml: item.rawHtml,
          })),
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
