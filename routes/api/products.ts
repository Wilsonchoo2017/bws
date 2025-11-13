import { FreshContext } from "$fresh/server.ts";
import { and, desc, eq, ilike, or, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { products, productTags as productTagsTable } from "../../db/schema.ts";

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    if (req.method !== "GET") {
      return new Response(
        JSON.stringify({ error: "Method not allowed. Use GET." }),
        {
          status: 405,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    const url = new URL(req.url);

    // Parse query parameters
    const searchQuery = url.searchParams.get("search") || "";
    const source = url.searchParams.get("source") || "";
    const watchStatus = url.searchParams.get("watchStatus") || "";
    const tagIds = url.searchParams.get("tagIds")?.split(",").filter(Boolean) || [];
    const limit = parseInt(url.searchParams.get("limit") || "100");
    const offset = parseInt(url.searchParams.get("offset") || "0");

    // Build filter conditions
    const conditions = [];

    if (searchQuery) {
      conditions.push(
        or(
          ilike(products.name, `%${searchQuery}%`),
          ilike(products.legoSetNumber, `%${searchQuery}%`),
        ),
      );
    }

    if (source) {
      conditions.push(eq(products.source, source as "shopee" | "toysrus" | "brickeconomy" | "self"));
    }

    if (watchStatus) {
      conditions.push(eq(products.watchStatus, watchStatus as "active" | "paused" | "stopped" | "archived"));
    }

    // Filter by tags if specified (using JSONB contains)
    if (tagIds.length > 0) {
      for (const tagId of tagIds) {
        conditions.push(
          sql`${products.tags} @> ${JSON.stringify([{ tagId }])}`
        );
      }
    }

    // Get total count (before pagination)
    const countResult = await db
      .select({ count: sql<number>`count(*)` })
      .from(products)
      .where(conditions.length > 0 ? and(...conditions) : undefined);

    const totalCount = Number(countResult[0]?.count || 0);

    // Build query with all conditions and execute
    const productList = conditions.length > 0
      ? await db
        .select()
        .from(products)
        .where(and(...conditions))
        .orderBy(desc(products.createdAt))
        .limit(limit)
        .offset(offset)
      : await db
        .select()
        .from(products)
        .orderBy(desc(products.createdAt))
        .limit(limit)
        .offset(offset);

    // Fetch tags for each product
    const productsWithTags = await Promise.all(
      productList.map(async (product) => {
        const productTagsList = (product.tags as Array<{ tagId: string; addedAt: string }>) || [];

        if (productTagsList.length === 0) {
          return { ...product, tagsData: [] };
        }

        const tagIdsList = productTagsList.map((t) => t.tagId);
        const tagsData = await db
          .select()
          .from(productTagsTable)
          .where(sql`${productTagsTable.id} = ANY(${tagIdsList})`);

        // Add addedAt timestamp to each tag
        const tagsWithTimestamp = tagsData.map((tag) => {
          const productTag = productTagsList.find((pt) => pt.tagId === tag.id);
          return {
            ...tag,
            addedAt: productTag?.addedAt,
            isExpired: tag.endDate ? new Date(tag.endDate) < new Date() : false,
          };
        });

        return { ...product, tagsData: tagsWithTimestamp };
      }),
    );

    return new Response(
      JSON.stringify({
        products: productsWithTags,
        totalCount,
        limit,
        offset,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    console.error("Error in products API:", error);
    return new Response(
      JSON.stringify({
        error: "Internal server error",
        details: error instanceof Error ? error.message : String(error),
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
};
