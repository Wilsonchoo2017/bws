/**
 * API endpoint for manually adding LEGO products via Bricklink scraping
 * POST /api/products/manual
 *
 * Request body:
 * {
 *   "legoSetNumber": "75192" // 5-digit LEGO set number
 * }
 *
 * Response:
 * {
 *   "success": true,
 *   "job": { id: "...", status: "waiting" },
 *   "bricklinkItem": { itemId: "75192", ... },
 *   "message": "Scraping job enqueued. Data will appear once scraping completes.",
 *   "checkStatusUrl": "/api/scrape-queue-status"
 * }
 */

import { FreshContext } from "$fresh/server.ts";
import { db } from "../../../db/client.ts";
import { bricklinkItems } from "../../../db/schema.ts";
import { eq } from "drizzle-orm";
import { getQueueService, isQueueReady } from "../../../services/queue/init.ts";

interface ManualProductRequest {
  legoSetNumber: string;
}

interface ApiResponse {
  success: boolean;
  job?: { id: string; status: string };
  bricklinkItem?: unknown;
  message?: string;
  error?: string;
  checkStatusUrl?: string;
}

/**
 * Build Bricklink URL for a LEGO set
 */
function buildBricklinkUrl(itemType: string, itemId: string): string {
  return `https://www.bricklink.com/v2/catalog/catalogitem.page?${itemType}=${itemId}`;
}

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  // Only allow POST requests
  if (req.method !== "POST") {
    return new Response(
      JSON.stringify(
        {
          success: false,
          error: "Method not allowed. Use POST.",
        } satisfies ApiResponse,
      ),
      {
        status: 405,
        headers: { "Content-Type": "application/json" },
      },
    );
  }

  try {
    // Parse request body
    const body: ManualProductRequest = await req.json();
    const { legoSetNumber } = body;

    // Validate input
    if (!legoSetNumber) {
      return new Response(
        JSON.stringify(
          {
            success: false,
            error: "legoSetNumber is required",
          } satisfies ApiResponse,
        ),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Validate format (5 digits)
    if (!/^\d{5}$/.test(legoSetNumber)) {
      return new Response(
        JSON.stringify(
          {
            success: false,
            error:
              "Invalid LEGO set number format. Expected 5 digits (e.g., 75192)",
          } satisfies ApiResponse,
        ),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Check if Bricklink item already exists
    const existingItems = await db
      .select()
      .from(bricklinkItems)
      .where(eq(bricklinkItems.itemId, legoSetNumber));

    if (existingItems.length > 0) {
      return new Response(
        JSON.stringify(
          {
            success: false,
            error:
              `Bricklink item ${legoSetNumber} already exists and is being tracked`,
            bricklinkItem: existingItems[0],
          } satisfies ApiResponse,
        ),
        {
          status: 409,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Check if queue is ready
    if (!isQueueReady()) {
      return new Response(
        JSON.stringify(
          {
            success: false,
            error:
              "Scraping queue is not available. Please try again later or contact administrator.",
          } satisfies ApiResponse,
        ),
        {
          status: 503,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Build Bricklink URL for LEGO set
    const itemType = "S"; // "S" = Sets
    const bricklinkUrl = buildBricklinkUrl(itemType, legoSetNumber);

    console.log(
      `📥 Creating Bricklink item entry for set ${legoSetNumber}...`,
    );

    // Create initial Bricklink item entry
    const [bricklinkItem] = await db
      .insert(bricklinkItems)
      .values({
        itemId: legoSetNumber,
        itemType: itemType,
        watchStatus: "active", // Track this item for price updates
        scrapeIntervalDays: 30, // Default scraping interval
        createdAt: new Date(),
        updatedAt: new Date(),
      })
      .returning();

    console.log(
      `✅ Created Bricklink item entry for ${legoSetNumber}`,
    );

    // Enqueue scraping job
    const queueService = getQueueService();
    const job = await queueService.addScrapeJob({
      url: bricklinkUrl,
      itemId: legoSetNumber,
      saveToDb: true,
    });

    const jobId = job.id || "unknown";

    console.log(
      `🔄 Enqueued Bricklink scraping job ${jobId} for set ${legoSetNumber}`,
    );

    return new Response(
      JSON.stringify(
        {
          success: true,
          job: {
            id: jobId,
            status: "waiting",
          },
          bricklinkItem,
          message:
            `Scraping job enqueued for LEGO set ${legoSetNumber}. Data will appear once scraping completes (usually 10-30 seconds).`,
          checkStatusUrl: "/api/scrape-queue-status",
        } satisfies ApiResponse,
      ),
      {
        status: 201,
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    console.error("❌ Error adding manual product:", error);

    return new Response(
      JSON.stringify(
        {
          success: false,
          error: error instanceof Error
            ? error.message
            : "Unknown error occurred",
        } satisfies ApiResponse,
      ),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
};
