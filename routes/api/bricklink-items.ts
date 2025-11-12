import { FreshContext } from "$fresh/server.ts";
import { eq } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { bricklinkItems } from "../../db/schema.ts";
import {
  createErrorResponse,
  createJsonResponse,
  createNotFoundResponse,
  createValidationErrorResponse,
} from "../../utils/api-helpers.ts";

export const handler = {
  // GET /api/bricklink-items - List all items
  // GET /api/bricklink-items?item_id=75192 - Get specific item
  // GET /api/bricklink-items?watch_status=active - Filter by watch status
  async GET(req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const url = new URL(req.url);
      const itemId = url.searchParams.get("item_id");
      const watchStatus = url.searchParams.get("watch_status");

      if (itemId) {
        // Get specific item
        const item = await db.query.bricklinkItems.findFirst({
          where: eq(bricklinkItems.itemId, itemId),
        });

        if (!item) {
          return createNotFoundResponse("Item");
        }

        return createJsonResponse(item);
      }

      // Get all items (optionally filtered by watch status)
      let items;
      if (watchStatus) {
        items = await db.query.bricklinkItems.findMany({
          where: eq(
            bricklinkItems.watchStatus,
            watchStatus as "active" | "paused" | "stopped" | "archived",
          ),
        });
      } else {
        items = await db.select().from(bricklinkItems);
      }

      return createJsonResponse(items);
    } catch (error) {
      return createErrorResponse(error, "Error fetching Bricklink items");
    }
  },

  // POST /api/bricklink-items - Create new item
  async POST(req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const body = await req.json();

      // Insert item
      const [newItem] = await db.insert(bricklinkItems).values({
        itemId: body.item_id,
        itemType: body.item_type,
        title: body.title || null,
        weight: body.weight || null,
        sixMonthNew: body.six_month_new || null,
        sixMonthUsed: body.six_month_used || null,
        currentNew: body.current_new || null,
        currentUsed: body.current_used || null,
      }).returning();

      return createJsonResponse(newItem, 201);
    } catch (error) {
      return createErrorResponse(error, "Error creating Bricklink item");
    }
  },

  // PUT /api/bricklink-items?item_id=75192 - Update item
  async PUT(req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const url = new URL(req.url);
      const itemId = url.searchParams.get("item_id");

      if (!itemId) {
        return new Response(
          JSON.stringify({ error: "Missing item_id parameter" }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      const body = await req.json();

      // Build update object dynamically to only update provided fields
      const updateData: Record<string, unknown> = {
        updatedAt: new Date(),
      };

      if (body.title !== undefined) updateData.title = body.title;
      if (body.weight !== undefined) updateData.weight = body.weight;
      if (body.six_month_new !== undefined) {
        updateData.sixMonthNew = body.six_month_new || null;
      }
      if (body.six_month_used !== undefined) {
        updateData.sixMonthUsed = body.six_month_used || null;
      }
      if (body.current_new !== undefined) {
        updateData.currentNew = body.current_new || null;
      }
      if (body.current_used !== undefined) {
        updateData.currentUsed = body.current_used || null;
      }
      if (body.watch_status !== undefined) {
        updateData.watchStatus = body.watch_status;
      }
      if (body.scrape_interval_days !== undefined) {
        updateData.scrapeIntervalDays = body.scrape_interval_days;

        // If interval changed, recalculate next_scrape_at
        if (body.scrape_interval_days > 0) {
          const now = new Date();
          const nextScrape = new Date(
            now.getTime() + body.scrape_interval_days * 24 * 60 * 60 * 1000,
          );
          updateData.nextScrapeAt = nextScrape;
        }
      }

      // Update item
      const [updatedItem] = await db.update(bricklinkItems)
        .set(updateData)
        .where(eq(bricklinkItems.itemId, itemId))
        .returning();

      if (!updatedItem) {
        return createNotFoundResponse("Item");
      }

      return createJsonResponse(updatedItem);
    } catch (error) {
      return createErrorResponse(error, "Error updating Bricklink item");
    }
  },

  // DELETE /api/bricklink-items?item_id=75192 - Delete item
  async DELETE(req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const url = new URL(req.url);
      const itemId = url.searchParams.get("item_id");

      if (!itemId) {
        return createValidationErrorResponse("Missing item_id parameter");
      }

      await db.delete(bricklinkItems).where(eq(bricklinkItems.itemId, itemId));

      return createJsonResponse({ success: true });
    } catch (error) {
      return createErrorResponse(error, "Error deleting Bricklink item");
    }
  },
};
