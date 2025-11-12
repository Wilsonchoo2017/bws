import { FreshContext } from "$fresh/server.ts";
import { eq } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { bricklinkItems } from "../../db/schema.ts";

export const handler = {
  // GET /api/bricklink-items - List all items
  // GET /api/bricklink-items?item_id=75192 - Get specific item
  async GET(req: Request, _ctx: FreshContext): Promise<Response> {
    try {
      const url = new URL(req.url);
      const itemId = url.searchParams.get("item_id");

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

      // Get all items
      const items = await db.select().from(bricklinkItems);

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

      // Update item
      const [updatedItem] = await db.update(bricklinkItems)
        .set({
          title: body.title,
          weight: body.weight,
          sixMonthNew: body.six_month_new || null,
          sixMonthUsed: body.six_month_used || null,
          currentNew: body.current_new || null,
          currentUsed: body.current_used || null,
          updatedAt: new Date(),
        })
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
