import { FreshContext } from "$fresh/server.ts";
import { sql } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import { productTags, products } from "../../../db/schema.ts";

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

    // Find expired tags
    const expiredTags = await db
      .select()
      .from(productTags)
      .where(sql`${productTags.endDate} < NOW()`);

    if (expiredTags.length === 0) {
      return new Response(
        JSON.stringify({ message: "No expired tags found", removedCount: 0 }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    const expiredTagIds = expiredTags.map((tag) => tag.id);
    let totalRemoved = 0;

    // Remove expired tags from all products
    const allProducts = await db.select().from(products);

    for (const product of allProducts) {
      if (!product.tags) continue;

      const currentTags = (product.tags as Array<{ tagId: string; addedAt: string }>) || [];
      const filteredTags = currentTags.filter(
        (t) => !expiredTagIds.includes(t.tagId),
      );

      if (filteredTags.length !== currentTags.length) {
        await db
          .update(products)
          .set({
            tags: filteredTags.length > 0 ? filteredTags : null,
          })
          .where(sql`${products.productId} = ${product.productId}`);

        totalRemoved += currentTags.length - filteredTags.length;
      }
    }

    return new Response(
      JSON.stringify({
        message: `Successfully removed expired tags from products`,
        expiredTags: expiredTags.map((t) => ({ id: t.id, name: t.name })),
        removedCount: totalRemoved,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    console.error("Error cleaning up expired tags:", error);
    return new Response(
      JSON.stringify({
        error: "Internal server error",
        details: error instanceof Error ? error.message : String(error),
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
};
