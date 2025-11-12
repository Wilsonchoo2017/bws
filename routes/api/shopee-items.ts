import { Handlers } from "$fresh/server.ts";
import { db } from "../../db/client.ts";
import { shopeeItems } from "../../db/schema.ts";
import { desc, asc, sql, like, eq, and } from "drizzle-orm";

interface ShopeeItemsQuery {
  search?: string;
  legoSetNumber?: string;
  watchStatus?: string;
  sortBy?: "price" | "sold" | "createdAt" | "updatedAt";
  sortOrder?: "asc" | "desc";
  page?: number;
  limit?: number;
}

export const handler: Handlers = {
  async GET(req) {
    try {
      const url = new URL(req.url);
      const query: ShopeeItemsQuery = {
        search: url.searchParams.get("search") || undefined,
        legoSetNumber: url.searchParams.get("legoSetNumber") || undefined,
        watchStatus: url.searchParams.get("watchStatus") || url.searchParams.get("watch_status") || undefined,
        sortBy: (url.searchParams.get("sortBy") as ShopeeItemsQuery["sortBy"]) || "updatedAt",
        sortOrder: (url.searchParams.get("sortOrder") as "asc" | "desc") || "desc",
        page: parseInt(url.searchParams.get("page") || "1"),
        limit: parseInt(url.searchParams.get("limit") || "50"),
      };

      // Build where conditions
      const conditions = [];

      // Search by product name (full-text search with improved handling)
      if (query.search && query.search.trim()) {
        const searchTerm = query.search.trim().replace(/\s+/g, ' '); // Normalize multiple spaces

        // Use websearch_to_tsquery for better phrase and partial matching
        // COALESCE handles NULL names
        conditions.push(
          sql`to_tsvector('english', COALESCE(${shopeeItems.name}, '')) @@ websearch_to_tsquery('english', ${searchTerm})`
        );
      }

      // Filter by LEGO set number (starts with match, case-insensitive)
      if (query.legoSetNumber && query.legoSetNumber.trim()) {
        const setNumberTerm = query.legoSetNumber.trim().replace(/\s+/g, ''); // Remove all spaces

        // Use ILIKE for case-insensitive "starts with" matching
        // COALESCE handles NULL set numbers
        conditions.push(
          sql`COALESCE(${shopeeItems.legoSetNumber}, '') ILIKE ${setNumberTerm + '%'}`
        );
      }

      // Filter by watch status
      if (query.watchStatus && query.watchStatus.trim()) {
        conditions.push(
          eq(shopeeItems.watchStatus, query.watchStatus as any)
        );
      }

      const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

      // Determine sort column and order
      let orderByClause;
      const sortOrderFn = query.sortOrder === "asc" ? asc : desc;

      switch (query.sortBy) {
        case "price":
          orderByClause = sortOrderFn(shopeeItems.price);
          break;
        case "sold":
          orderByClause = sortOrderFn(shopeeItems.sold);
          break;
        case "createdAt":
          orderByClause = sortOrderFn(shopeeItems.createdAt);
          break;
        case "updatedAt":
        default:
          orderByClause = sortOrderFn(shopeeItems.updatedAt);
          break;
      }

      // Get total count for pagination
      const [countResult] = await db
        .select({ count: sql<number>`count(*)::int` })
        .from(shopeeItems)
        .where(whereClause);

      const totalCount = countResult?.count || 0;

      // Get paginated results
      const offset = (query.page! - 1) * query.limit!;
      const items = await db
        .select()
        .from(shopeeItems)
        .where(whereClause)
        .orderBy(orderByClause)
        .limit(query.limit!)
        .offset(offset);

      // Calculate pagination metadata
      const totalPages = Math.ceil(totalCount / query.limit!);
      const hasNextPage = query.page! < totalPages;
      const hasPrevPage = query.page! > 1;

      return new Response(
        JSON.stringify({
          items,
          pagination: {
            page: query.page,
            limit: query.limit,
            totalCount,
            totalPages,
            hasNextPage,
            hasPrevPage,
          },
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        }
      );
    } catch (error) {
      console.error("Error fetching Shopee items:", error);
      return new Response(
        JSON.stringify({
          error: "Failed to fetch products",
          message: error instanceof Error ? error.message : String(error),
        }),
        {
          status: 500,
          headers: {
            "Content-Type": "application/json",
          },
        }
      );
    }
  },
};
