/**
 * API endpoint for compression analytics
 * GET /api/raw-data/stats - Get compression statistics
 * GET /api/raw-data/stats?source=shopee - Get statistics for specific source
 */

import { FreshContext } from "$fresh/server.ts";
import { rawDataService } from "../../../services/raw-data/index.ts";

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    const url = new URL(req.url);
    const source = url.searchParams.get("source") as
      | "shopee"
      | "toysrus"
      | "brickeconomy"
      | "bricklink"
      | "worldbricks"
      | "brickranker"
      | null;

    const stats = await rawDataService.getCompressionAnalytics(source || undefined);

    // Format bytes to human-readable format
    const formatBytes = (bytes: number): string => {
      if (bytes === 0) return "0 Bytes";
      const k = 1024;
      const sizes = ["Bytes", "KB", "MB", "GB"];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
    };

    return new Response(
      JSON.stringify(
        {
          source: source || "all",
          totalRecords: stats.totalRecords,
          storage: {
            originalSize: formatBytes(stats.totalOriginalSize),
            compressedSize: formatBytes(stats.totalCompressedSize),
            savedSpace: formatBytes(stats.totalSavedBytes),
          },
          compression: {
            ratio: stats.averageCompressionRatio,
            percent: `${stats.averageCompressionPercent}%`,
          },
          raw: {
            totalOriginalBytes: stats.totalOriginalSize,
            totalCompressedBytes: stats.totalCompressedSize,
            totalSavedBytes: stats.totalSavedBytes,
          },
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
