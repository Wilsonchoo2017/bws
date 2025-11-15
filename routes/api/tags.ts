import { FreshContext } from "$fresh/server.ts";
import { desc, eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { products, productTags } from "../../db/schema.ts";

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    // GET - List all tags
    if (req.method === "GET") {
      const tags = await db
        .select()
        .from(productTags)
        .orderBy(desc(productTags.createdAt));

      // Count products for each tag
      const tagsWithCounts = await Promise.all(
        tags.map(async (tag) => {
          const productsWithTag = await db
            .select({ count: sql<number>`count(*)` })
            .from(products)
            .where(
              sql`${products.tags} @> ${JSON.stringify([{ tagId: tag.id }])}`,
            );

          return {
            ...tag,
            productCount: Number(productsWithTag[0]?.count || 0),
            isExpired: tag.endDate ? new Date(tag.endDate) < new Date() : false,
          };
        }),
      );

      return new Response(JSON.stringify(tagsWithCounts), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // POST - Create new tag
    if (req.method === "POST") {
      const body = await req.json();

      if (!body.name || typeof body.name !== "string") {
        return new Response(
          JSON.stringify({ error: "Missing or invalid 'name' field" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      // Default endDate to end of today if not provided
      let endDate = body.endDate;
      if (!endDate) {
        const today = new Date();
        today.setHours(23, 59, 59, 999);
        endDate = today.toISOString();
      }

      const [newTag] = await db
        .insert(productTags)
        .values({
          name: body.name.trim(),
          description: body.description?.trim() || null,
          endDate: endDate ? new Date(endDate) : null,
        })
        .returning();

      return new Response(JSON.stringify(newTag), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    }

    // PUT - Update existing tag
    if (req.method === "PUT") {
      const body = await req.json();

      if (!body.id) {
        return new Response(
          JSON.stringify({ error: "Missing 'id' field" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      const updates: Record<string, unknown> = {
        updatedAt: new Date(),
      };

      if (body.name !== undefined) updates.name = body.name.trim();
      if (body.description !== undefined) {
        updates.description = body.description?.trim() || null;
      }
      if (body.endDate !== undefined) {
        updates.endDate = body.endDate ? new Date(body.endDate) : null;
      }

      const [updatedTag] = await db
        .update(productTags)
        .set(updates)
        .where(eq(productTags.id, body.id))
        .returning();

      if (!updatedTag) {
        return new Response(
          JSON.stringify({ error: "Tag not found" }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      return new Response(JSON.stringify(updatedTag), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // DELETE - Delete tag
    if (req.method === "DELETE") {
      const url = new URL(req.url);
      const id = url.searchParams.get("id");

      if (!id) {
        return new Response(
          JSON.stringify({ error: "Missing 'id' query parameter" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      // Remove tag from all products first
      const allProducts = await db
        .select()
        .from(products)
        .where(sql`${products.tags} @> ${JSON.stringify([{ tagId: id }])}`);

      for (const product of allProducts) {
        const currentTags =
          (product.tags as Array<{ tagId: string; addedAt: string }>) || [];
        const updatedTags = currentTags.filter((t) => t.tagId !== id);

        await db
          .update(products)
          .set({ tags: updatedTags.length > 0 ? updatedTags : null })
          .where(eq(products.productId, product.productId));
      }

      // Delete the tag
      const [deletedTag] = await db
        .delete(productTags)
        .where(eq(productTags.id, id))
        .returning();

      if (!deletedTag) {
        return new Response(
          JSON.stringify({ error: "Tag not found" }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      return new Response(
        JSON.stringify({ success: true, deletedTag }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    return new Response(
      JSON.stringify({ error: "Method not allowed" }),
      { status: 405, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    console.error("Error in tags API:", error);
    return new Response(
      JSON.stringify({
        error: "Internal server error",
        details: error instanceof Error ? error.message : String(error),
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
};
