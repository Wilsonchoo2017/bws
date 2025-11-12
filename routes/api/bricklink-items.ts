import { FreshContext } from "$fresh/server.ts";
import { eq } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { bricklinkItems } from "../../db/schema.ts";

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
          return new Response(
            JSON.stringify({ error: "Item not found" }),
            {
              status: 404,
              headers: { "Content-Type": "application/json" },
            },
          );
        }

        return new Response(JSON.stringify(item), {
          headers: { "Content-Type": "application/json" },
        });
      }

      // Get all items (optionally filtered by watch status)
      let items;
      if (watchStatus) {
        items = await db.query.bricklinkItems.findMany({
          where: eq(bricklinkItems.watchStatus, watchStatus as any),
        });
      } else {
        items = await db.select().from(bricklinkItems);
      }

      return new Response(JSON.stringify(items), {
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      console.error("Error fetching items:", error);
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

      return new Response(JSON.stringify(newItem), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      console.error("Error creating item:", error);
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
      const updateData: any = {
        updatedAt: new Date(),
      };

      if (body.title !== undefined) updateData.title = body.title;
      if (body.weight !== undefined) updateData.weight = body.weight;
      if (body.six_month_new !== undefined) updateData.sixMonthNew = body.six_month_new || null;
      if (body.six_month_used !== undefined) updateData.sixMonthUsed = body.six_month_used || null;
      if (body.current_new !== undefined) updateData.currentNew = body.current_new || null;
      if (body.current_used !== undefined) updateData.currentUsed = body.current_used || null;
      if (body.watch_status !== undefined) updateData.watchStatus = body.watch_status;

      // Update item
      const [updatedItem] = await db.update(bricklinkItems)
        .set(updateData)
        .where(eq(bricklinkItems.itemId, itemId))
        .returning();

      if (!updatedItem) {
        return new Response(
          JSON.stringify({ error: "Item not found" }),
          {
            status: 404,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      return new Response(JSON.stringify(updatedItem), {
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      console.error("Error updating item:", error);
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
  },

  // DELETE /api/bricklink-items?item_id=75192 - Delete item
  async DELETE(req: Request, _ctx: FreshContext): Promise<Response> {
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

      await db.delete(bricklinkItems).where(eq(bricklinkItems.itemId, itemId));

      return new Response(JSON.stringify({ success: true }), {
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      console.error("Error deleting item:", error);
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
  },
};
