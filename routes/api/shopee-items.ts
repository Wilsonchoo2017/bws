import { Handlers } from "$fresh/server.ts";
import { db } from "../../db/client.ts";
import { bricklinkItems, products } from "../../db/schema.ts";
import { and, asc, desc, eq, sql } from "drizzle-orm";
import {
  createErrorResponse,
  createJsonResponse,
  createPaginatedResponse,
} from "../../utils/api-helpers.ts";
import { PAGINATION } from "../../constants/app-config.ts";
import type { ProductSource } from "../../db/schema.ts";

interface ProductsQuery {
  search?: string;
  legoSetNumber?: string;
  watchStatus?: string;
  source?: ProductSource | "all"; // Filter by platform or show all
  sortBy?: "price" | "sold" | "createdAt" | "updatedAt";
  sortOrder?: "asc" | "desc";
  page?: number;
  limit?: number;
}

export const handler: Handlers = {
  async GET(req) {
    try {
      const url = new URL(req.url);
      const query: ProductsQuery = {
        search: url.searchParams.get("search") || undefined,
        legoSetNumber: url.searchParams.get("legoSetNumber") || undefined,
        watchStatus: url.searchParams.get("watchStatus") ||
          url.searchParams.get("watch_status") || undefined,
        source: (url.searchParams.get("source") as ProductSource | "all") ||
          "all",
        sortBy: (url.searchParams.get("sortBy") as ProductsQuery["sortBy"]) ||
          "updatedAt",
        sortOrder: (url.searchParams.get("sortOrder") as "asc" | "desc") ||
          "desc",
        page: parseInt(url.searchParams.get("page") || "1"),
        limit: parseInt(
          url.searchParams.get("limit") || PAGINATION.DEFAULT_LIMIT.toString(),
        ),
      };

      // Build where conditions
      const conditions = [];

      // Filter by source/platform
      if (query.source && query.source !== "all") {
        conditions.push(eq(products.source, query.source));
      }

      // Search by product name (full-text search with improved handling)
      if (query.search && query.search.trim()) {
        const searchTerm = query.search.trim().replace(/\s+/g, " "); // Normalize multiple spaces

        // Use websearch_to_tsquery for better phrase and partial matching
        // COALESCE handles NULL names
        conditions.push(
          sql`to_tsvector('english', COALESCE(${products.name}, '')) @@ websearch_to_tsquery('english', ${searchTerm})`,
        );
      }

      // Filter by LEGO set number (starts with match, case-insensitive)
      if (query.legoSetNumber && query.legoSetNumber.trim()) {
        const setNumberTerm = query.legoSetNumber.trim().replace(/\s+/g, ""); // Remove all spaces

        // Use ILIKE for case-insensitive "starts with" matching
        // COALESCE handles NULL set numbers
        conditions.push(
          sql`COALESCE(${products.legoSetNumber}, '') ILIKE ${
            setNumberTerm + "%"
          }`,
        );
      }

      // Filter by watch status
      if (query.watchStatus && query.watchStatus.trim()) {
        conditions.push(
          eq(
            products.watchStatus,
            query.watchStatus as "active" | "paused" | "stopped" | "archived",
          ),
        );
      }

      const whereClause = conditions.length > 0
        ? and(...conditions)
        : undefined;

      // Determine sort column and order
      let orderByClause;
      const sortOrderFn = query.sortOrder === "asc" ? asc : desc;

      switch (query.sortBy) {
        case "price":
          orderByClause = sortOrderFn(products.price);
          break;
        case "sold":
          orderByClause = sortOrderFn(products.unitsSold);
          break;
        case "createdAt":
          orderByClause = sortOrderFn(products.createdAt);
          break;
        case "updatedAt":
        default:
          orderByClause = sortOrderFn(products.updatedAt);
          break;
      }

      // Get total count for pagination
      const [countResult] = await db
        .select({ count: sql<number>`count(*)::int` })
        .from(products)
        .where(whereClause);

      const totalCount = countResult?.count || 0;

      // Get paginated results with Bricklink data indicator
      const offset = (query.page! - 1) * query.limit!;
      const items = await db
        .select({
          id: products.id,
          productId: products.productId,
          name: products.name,
          price: products.price,
          priceMin: products.priceMin,
          priceMax: products.priceMax,
          priceBeforeDiscount: products.priceBeforeDiscount,
          image: products.image,
          images: products.images,
          localImagePath: products.localImagePath,
          localImages: products.localImages,
          imageDownloadStatus: products.imageDownloadStatus,
          unitsSold: products.unitsSold,
          source: products.source,
          legoSetNumber: products.legoSetNumber,
          createdAt: products.createdAt,
          updatedAt: products.updatedAt,
          hasBricklinkData: sql<boolean>`${bricklinkItems.itemId} IS NOT NULL`,
        })
        .from(products)
        .leftJoin(bricklinkItems, eq(products.legoSetNumber, bricklinkItems.itemId))
        .where(whereClause)
        .orderBy(orderByClause)
        .limit(query.limit!)
        .offset(offset);

      // Return paginated response
      const response = createPaginatedResponse(
        items,
        query.page!,
        query.limit!,
        totalCount,
      );

      return createJsonResponse(response);
    } catch (error) {
      return createErrorResponse(error, "Failed to fetch products");
    }
  },
};
