import { FreshContext } from "$fresh/server.ts";
import { eq, sql } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import { products, productTags as productTagsTable } from "../../../db/schema.ts";

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    if (req.method !== "POST") {
      return new Response(
        JSON.stringify({ error: "Method not allowed. Use POST." }),
        {
          status: 405,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    const body = await req.json();

    if (!Array.isArray(body.productIds) || body.productIds.length === 0) {
      return new Response(
        JSON.stringify({ error: "productIds array is required and must not be empty" }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    if (!body.action || !["add", "remove", "replace"].includes(body.action)) {
      return new Response(
        JSON.stringify({ error: "action must be 'add', 'remove', or 'replace'" }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    if (!Array.isArray(body.tagIds)) {
      return new Response(
        JSON.stringify({ error: "tagIds array is required" }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    // Validate that all tagIds exist
    if (body.tagIds.length > 0) {
      const existingTags = await db
        .select()
        .from(productTagsTable)
        .where(sql`${productTagsTable.id} = ANY(${body.tagIds})`);

      if (existingTags.length !== body.tagIds.length) {
        return new Response(
          JSON.stringify({ error: "One or more tag IDs are invalid" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }
    }

    // Fetch all products
    const productsToUpdate = await db
      .select()
      .from(products)
      .where(sql`${products.productId} = ANY(${body.productIds})`);

    if (productsToUpdate.length === 0) {
      return new Response(
        JSON.stringify({ error: "No products found" }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      );
    }

    const updatedCount = { value: 0 };
    const now = new Date().toISOString();

    // Update each product based on action
    for (const product of productsToUpdate) {
      let newTags: Array<{ tagId: string; addedAt: string }> = [];

      const currentTags = (product.tags as Array<{ tagId: string; addedAt: string }>) || [];

      if (body.action === "replace") {
        // Replace all tags
        newTags = body.tagIds.map((tagId: string) => ({
          tagId,
          addedAt: now,
        }));
      } else if (body.action === "add") {
        // Add tags (avoid duplicates)
        const existingTagIds = new Set(currentTags.map((t) => t.tagId));
        const tagsToAdd = body.tagIds
          .filter((tagId: string) => !existingTagIds.has(tagId))
          .map((tagId: string) => ({
            tagId,
            addedAt: now,
          }));
        newTags = [...currentTags, ...tagsToAdd];
      } else if (body.action === "remove") {
        // Remove specified tags
        const tagIdsToRemove = new Set(body.tagIds);
        newTags = currentTags.filter((t) => !tagIdsToRemove.has(t.tagId));
      }

      await db
        .update(products)
        .set({
          tags: newTags.length > 0 ? newTags : null,
          updatedAt: new Date(),
        })
        .where(eq(products.productId, product.productId));

      updatedCount.value++;
    }

    return new Response(
      JSON.stringify({
        success: true,
        updatedCount: updatedCount.value,
        action: body.action,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    console.error("Error in bulk tag API:", error);
    return new Response(
      JSON.stringify({
        error: "Internal server error",
        details: error instanceof Error ? error.message : String(error),
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
};
