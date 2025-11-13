import { FreshContext } from "$fresh/server.ts";
import { eq, sql } from "drizzle-orm";
import { db } from "../../../../db/client.ts";
import { products, productTags as productTagsTable } from "../../../../db/schema.ts";

export const handler = async (
  req: Request,
  ctx: FreshContext,
): Promise<Response> => {
  try {
    const productId = ctx.params.id;

    if (!productId) {
      return new Response(
        JSON.stringify({ error: "Product ID is required" }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    // GET - Get tags for a product
    if (req.method === "GET") {
      const product = await db
        .select()
        .from(products)
        .where(eq(products.productId, productId))
        .limit(1);

      if (product.length === 0) {
        return new Response(
          JSON.stringify({ error: "Product not found" }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      const productTags = (product[0].tags as Array<{ tagId: string; addedAt: string }>) || [];

      // Fetch full tag details
      if (productTags.length === 0) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      const tagIds = productTags.map((t) => t.tagId);
      const tagsData = await db
        .select()
        .from(productTagsTable)
        .where(sql`${productTagsTable.id} = ANY(${tagIds})`);

      const tagsWithAddedAt = tagsData.map((tag) => {
        const productTag = productTags.find((pt) => pt.tagId === tag.id);
        return {
          ...tag,
          addedAt: productTag?.addedAt,
        };
      });

      return new Response(JSON.stringify(tagsWithAddedAt), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // PUT - Update tags for a product
    if (req.method === "PUT") {
      const body = await req.json();

      if (!Array.isArray(body.tagIds)) {
        return new Response(
          JSON.stringify({ error: "tagIds must be an array" }),
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

      // Create tags array with timestamps
      const newTags = body.tagIds.map((tagId: string) => ({
        tagId,
        addedAt: new Date().toISOString(),
      }));

      const [updatedProduct] = await db
        .update(products)
        .set({
          tags: newTags.length > 0 ? newTags : null,
          updatedAt: new Date(),
        })
        .where(eq(products.productId, productId))
        .returning();

      if (!updatedProduct) {
        return new Response(
          JSON.stringify({ error: "Product not found" }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      return new Response(JSON.stringify(updatedProduct), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(
      JSON.stringify({ error: "Method not allowed" }),
      { status: 405, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    console.error("Error in product tags API:", error);
    return new Response(
      JSON.stringify({
        error: "Internal server error",
        details: error instanceof Error ? error.message : String(error),
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
};
