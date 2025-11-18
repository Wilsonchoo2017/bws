import { FreshContext } from "$fresh/server.ts";
import { and, asc, desc, eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import {
  bricklinkItems,
  brickrankerRetirementItems,
  products,
  productTags as productTagsTable,
  worldbricksSets,
} from "../../db/schema.ts";
import { BricklinkDataValidator } from "../../services/bricklink/BricklinkDataValidator.ts";

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

    // Parse query parameters (matching shopee-items API format)
    const searchQuery = url.searchParams.get("search") || "";
    const legoSetNumber = url.searchParams.get("legoSetNumber") || "";
    const source = url.searchParams.get("source") || "";
    const watchStatus = url.searchParams.get("watchStatus") ||
      url.searchParams.get("watch_status") || "";
    const tagIds = url.searchParams.get("tagIds")?.split(",").filter(Boolean) ||
      [];
    const bricklinkStatus = url.searchParams.get("bricklinkStatus") || "all";
    const worldbricksStatus = url.searchParams.get("worldbricksStatus") ||
      "all";
    const lastScrapedBefore = url.searchParams.get("lastScrapedBefore") || "";
    const lastScrapedAfter = url.searchParams.get("lastScrapedAfter") || "";
    const showIncompleteOnly = url.searchParams.get("showIncompleteOnly") ===
      "true";
    const showMissingCriticalData = url.searchParams.get(
      "showMissingCriticalData",
    ) === "true";
    const sortBy = url.searchParams.get("sortBy") || "updatedAt";
    const sortOrder = (url.searchParams.get("sortOrder") || "desc") as
      | "asc"
      | "desc";
    const page = parseInt(url.searchParams.get("page") || "1");
    const limit = parseInt(url.searchParams.get("limit") || "100");
    const offset = (page - 1) * limit;

    // Build filter conditions
    const conditions = [];

    // Search by product name (full-text search)
    if (searchQuery && searchQuery.trim()) {
      const searchTerm = searchQuery.trim().replace(/\s+/g, " ");
      conditions.push(
        sql`to_tsvector('english', COALESCE(${products.name}, '')) @@ websearch_to_tsquery('english', ${searchTerm})`,
      );
    }

    // Filter by LEGO set number (starts with match)
    if (legoSetNumber && legoSetNumber.trim()) {
      const setNumberTerm = legoSetNumber.trim().replace(/\s+/g, "");
      conditions.push(
        sql`COALESCE(${products.legoSetNumber}, '') ILIKE ${
          setNumberTerm + "%"
        }`,
      );
    }

    if (source && source !== "all") {
      conditions.push(
        eq(
          products.source,
          source as
            | "shopee"
            | "toysrus"
            | "brickeconomy"
            | "bricklink"
            | "worldbricks"
            | "brickranker"
            | "self",
        ),
      );
    }

    if (watchStatus) {
      conditions.push(
        eq(
          products.watchStatus,
          watchStatus as "active" | "paused" | "stopped" | "archived",
        ),
      );
    }

    // Filter by tags if specified (using JSONB contains)
    if (tagIds.length > 0) {
      for (const tagId of tagIds) {
        conditions.push(
          sql`${products.tags} @> ${JSON.stringify([{ tagId }])}`,
        );
      }
    }

    // Add date range filters for last scraped
    if (lastScrapedBefore) {
      conditions.push(
        sql`${products.updatedAt} < ${new Date(lastScrapedBefore)}`,
      );
    }
    if (lastScrapedAfter) {
      conditions.push(
        sql`${products.updatedAt} > ${new Date(lastScrapedAfter)}`,
      );
    }

    // Build query with LEFT JOINs to fetch related LEGO data
    const baseQuery = db
      .select({
        // All product fields
        product: products,
        // WorldBricks data (for release year, retired year, retail price)
        worldbricks: worldbricksSets,
        // Brickranker data (for retiring soon status)
        brickranker: brickrankerRetirementItems,
        // Bricklink data (for price data availability)
        bricklink: bricklinkItems,
        // Brick Economy data check (via self-join on products with source='brickeconomy')
        brickEconomy: {
          id: sql<number>`be.id`,
          productId: sql<string>`be.product_id`,
          name: sql<string>`be.name`,
          price: sql<number>`be.price`,
          priceBeforeDiscount: sql<number>`be.price_before_discount`,
          rawData: sql<Record<string, unknown>>`be.raw_data`,
        },
      })
      .from(products)
      .leftJoin(
        worldbricksSets,
        eq(products.legoSetNumber, worldbricksSets.setNumber),
      )
      .leftJoin(
        brickrankerRetirementItems,
        eq(products.legoSetNumber, brickrankerRetirementItems.setNumber),
      )
      .leftJoin(
        bricklinkItems,
        eq(products.legoSetNumber, bricklinkItems.itemId),
      )
      .leftJoin(
        sql`products AS be`,
        sql`${products.legoSetNumber} = be.lego_set_number AND be.source = 'brickeconomy'`,
      );

    // Add JOIN-based filters for data completeness
    const joinConditions = [...conditions];

    // Filter by Bricklink data status
    if (bricklinkStatus !== "all") {
      if (bricklinkStatus === "missing") {
        joinConditions.push(
          sql`${products.legoSetNumber} IS NOT NULL AND ${bricklinkItems.itemId} IS NULL`,
        );
      } else if (bricklinkStatus === "complete" || bricklinkStatus === "partial") {
        joinConditions.push(
          sql`${bricklinkItems.itemId} IS NOT NULL`,
        );
        // Note: We'll filter complete vs partial in memory after validation
      }
    }

    // Filter by WorldBricks data status
    if (worldbricksStatus === "missing_data") {
      joinConditions.push(
        sql`${products.legoSetNumber} IS NOT NULL AND ${worldbricksSets.setNumber} IS NULL`,
      );
    } else if (worldbricksStatus === "has_data") {
      joinConditions.push(
        sql`${worldbricksSets.setNumber} IS NOT NULL`,
      );
    }

    // Show incomplete only (missing any LEGO data)
    if (showIncompleteOnly) {
      joinConditions.push(
        sql`(
          ${products.legoSetNumber} IS NOT NULL AND (
            ${worldbricksSets.setNumber} IS NULL OR
            ${bricklinkItems.itemId} IS NULL
          )
        )`,
      );
    }

    // Show missing critical data (missing retail price OR Bricklink data)
    if (showMissingCriticalData) {
      joinConditions.push(
        sql`(
          ${products.legoSetNumber} IS NOT NULL AND (
            ${bricklinkItems.itemId} IS NULL OR
            (${worldbricksSets.setNumber} IS NULL AND ${products.priceBeforeDiscount} IS NULL)
          )
        )`,
      );
    }

    // Determine sort column
    const sortColumn = sortBy === "price"
      ? products.price
      : sortBy === "sold"
      ? products.unitsSold
      : sortBy === "createdAt"
      ? products.createdAt
      : products.updatedAt;

    const orderFunc = sortOrder === "asc" ? asc : desc;

    // Execute query with all conditions
    const productList = joinConditions.length > 0
      ? await baseQuery
        .where(and(...joinConditions))
        .orderBy(orderFunc(sortColumn))
        .limit(limit)
        .offset(offset)
      : await baseQuery
        .orderBy(orderFunc(sortColumn))
        .limit(limit)
        .offset(offset);

    // Get total count with same filters
    const countQuery = db
      .select({ count: sql<number>`count(*)` })
      .from(products)
      .leftJoin(
        worldbricksSets,
        eq(products.legoSetNumber, worldbricksSets.setNumber),
      )
      .leftJoin(
        bricklinkItems,
        eq(products.legoSetNumber, bricklinkItems.itemId),
      );

    const countResult = joinConditions.length > 0
      ? await countQuery.where(and(...joinConditions))
      : await countQuery;

    const totalCount = Number(countResult[0]?.count || 0);

    // Fetch tags and enrich products with LEGO data
    let productsWithEnrichedData = await Promise.all(
      productList.map(async (row) => {
        const { product, worldbricks, brickranker, bricklink, brickEconomy } =
          row;

        const productTagsList =
          (product.tags as Array<{ tagId: string; addedAt: string }>) || [];

        let tagsData: Array<{
          id: string;
          name: string;
          description: string | null;
          endDate: Date | null;
          createdAt: Date;
          updatedAt: Date;
          addedAt?: string;
          isExpired: boolean;
        }> = [];

        if (productTagsList.length > 0) {
          const tagIdsList = productTagsList.map((t) => t.tagId);
          const tags = await db
            .select()
            .from(productTagsTable)
            .where(sql`${productTagsTable.id} = ANY(${tagIdsList})`);

          // Add addedAt timestamp to each tag
          tagsData = tags.map((tag) => {
            const productTag = productTagsList.find((pt) =>
              pt.tagId === tag.id
            );
            return {
              ...tag,
              addedAt: productTag?.addedAt,
              isExpired: tag.endDate
                ? new Date(tag.endDate) < new Date()
                : false,
            };
          });
        }

        // Compute retail price: WorldBricks first, fallback to marketplace priceBeforeDiscount
        const retailPrice = worldbricks?.yearReleased
          ? (brickEconomy?.priceBeforeDiscount ?? product.priceBeforeDiscount)
          : product.priceBeforeDiscount;

        // Validate Bricklink data completeness (including monthly sales data)
        const bricklinkValidation = await BricklinkDataValidator
          .validateCompletenessWithMonthlyData(
            bricklink,
          );
        const bricklinkDataStatus = !bricklink
          ? "missing"
          : bricklinkValidation.isComplete
          ? "complete"
          : "partial";

        // Return enriched product with availability flags
        return {
          ...product,
          tagsData,
          // LEGO data fields
          releaseYear: worldbricks?.yearReleased ?? null,
          retiredYear: worldbricks?.yearRetired ?? null,
          retiringSoon: brickranker?.retiringSoon ?? false,
          expectedRetirementDate: brickranker?.expectedRetirementDate ?? null,
          retailPrice,
          // Data availability flags (for checkmark/X display)
          hasReleaseYear: worldbricks?.yearReleased != null,
          hasRetiredYear: worldbricks?.yearRetired != null,
          hasRetiringSoon: brickranker?.retiringSoon != null,
          hasBricklinkData: bricklink != null,
          hasBrickEconomyData: brickEconomy?.id != null,
          // Enhanced Bricklink data status
          bricklinkDataStatus,
          bricklinkMissingBoxes: bricklinkValidation.missingBoxes,
          bricklinkHasMonthlyData: bricklinkValidation.hasMonthlyData ?? false,
        };
      }),
    );

    // Apply in-memory filter for complete vs partial Bricklink data
    if (bricklinkStatus === "complete") {
      productsWithEnrichedData = productsWithEnrichedData.filter(
        (p) => p.bricklinkDataStatus === "complete",
      );
    } else if (bricklinkStatus === "partial") {
      productsWithEnrichedData = productsWithEnrichedData.filter(
        (p) => p.bricklinkDataStatus === "partial",
      );
    }

    // Calculate pagination metadata
    const totalPages = Math.ceil(totalCount / limit);
    const hasNextPage = page < totalPages;
    const hasPrevPage = page > 1;

    return new Response(
      JSON.stringify({
        items: productsWithEnrichedData,
        pagination: {
          page,
          limit,
          totalCount,
          totalPages,
          hasNextPage,
          hasPrevPage,
        },
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
