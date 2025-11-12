import { Handlers } from "$fresh/server.ts";
import { eq, sql } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import { priceHistory, products } from "../../../db/schema.ts";
import { getMissingDataDetector } from "../../../services/missing-data/MissingDataDetectorService.ts";

export const handler: Handlers = {
  async POST(req) {
    try {
      const data = await req.json();

      // Validate required fields based on source
      if (!data.source || !data.legoSetNumber || !data.productId) {
        return new Response(
          JSON.stringify({
            success: false,
            error:
              "Missing required fields: source, productId, and legoSetNumber",
          }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      // Validate LEGO ID format (exactly 5 digits)
      const legoIdPattern = /^\d{5}$/;
      if (!legoIdPattern.test(data.legoSetNumber)) {
        return new Response(
          JSON.stringify({
            success: false,
            error: "LEGO ID must be exactly 5 digits",
          }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        );
      }

      // Check if product already exists to get previous data
      const existingProduct = await db.query.products.findFirst({
        where: eq(products.productId, data.productId),
      });

      // Get the most recent price history entry (before this update)
      let previousHistory = null;
      if (existingProduct) {
        const histories = await db.query.priceHistory.findMany({
          where: eq(priceHistory.productId, data.productId),
          orderBy: (history, { desc }) => [desc(history.recordedAt)],
          limit: 1,
        });
        previousHistory = histories[0] || null;
      }

      // Upsert product into database (insert or update if exists)
      const [insertedProduct] = await db.insert(products).values({
        ...data,
        updatedAt: new Date(),
      }).onConflictDoUpdate({
        target: products.productId,
        set: {
          legoSetNumber: sql`EXCLUDED.lego_set_number`,
          name: sql`EXCLUDED.name`,
          price: sql`EXCLUDED.price`,
          unitsSold: data.source === "shopee"
            ? sql`EXCLUDED.units_sold`
            : undefined,
          priceBeforeDiscount: data.source === "toysrus"
            ? sql`EXCLUDED.price_before_discount`
            : undefined,
          shopId: data.source === "shopee" ? sql`EXCLUDED.shop_id` : undefined,
          shopName: data.source === "shopee"
            ? sql`EXCLUDED.shop_name`
            : undefined,
          brand: data.source === "toysrus" ? sql`EXCLUDED.brand` : undefined,
          sku: data.source === "toysrus" ? sql`EXCLUDED.sku` : undefined,
          categoryNumber: data.source === "toysrus"
            ? sql`EXCLUDED.category_number`
            : undefined,
          categoryName: data.source === "toysrus"
            ? sql`EXCLUDED.category_name`
            : undefined,
          ageRange: data.source === "toysrus"
            ? sql`EXCLUDED.age_range`
            : undefined,
          image: sql`EXCLUDED.image`,
          rawData: sql`EXCLUDED.raw_data`,
          updatedAt: new Date(),
        },
      }).returning();

      // Record price history if price/units changed
      const shouldRecordHistory = !existingProduct || // New product, always record
        (previousHistory && (
          previousHistory.price !== data.price || // Price changed
          (data.source === "shopee" &&
            previousHistory.unitsSoldSnapshot !== data.unitsSold) || // Sold units changed (Shopee)
          (data.source === "toysrus" &&
            previousHistory.priceBeforeDiscount !== data.priceBeforeDiscount) // Discount changed (ToysRUs)
        )) ||
        !previousHistory; // No previous history exists

      if (shouldRecordHistory && data.price !== null) {
        await db.insert(priceHistory).values({
          productId: data.productId,
          price: data.price,
          unitsSoldSnapshot: data.source === "shopee" ? data.unitsSold : null,
          priceBeforeDiscount: data.source === "toysrus"
            ? data.priceBeforeDiscount
            : null,
        });
      }

      // Add metadata matching parser response format
      const productWithMeta = {
        ...insertedProduct,
        wasUpdated: !!existingProduct,
        previousSold: data.source === "shopee"
          ? (previousHistory?.unitsSoldSnapshot || null)
          : undefined,
        previousPrice: previousHistory?.price || null,
        soldDelta: existingProduct && data.source === "shopee" &&
            data.unitsSold !== null && previousHistory?.unitsSoldSnapshot
          ? data.unitsSold - (previousHistory.unitsSoldSnapshot || 0)
          : null,
        priceDelta: existingProduct && data.price !== null &&
            previousHistory?.price
          ? data.price - (previousHistory.price || 0)
          : null,
      };

      // Check for missing Bricklink data and enqueue scraping job if needed
      // This runs asynchronously without blocking the response
      if (data.legoSetNumber) {
        const detector = getMissingDataDetector();
        detector.checkProduct(data.productId).catch((error) => {
          console.error(
            `Failed to check missing Bricklink data for product ${data.productId}:`,
            error,
          );
        });
      }

      return new Response(
        JSON.stringify({
          success: true,
          product: productWithMeta,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    } catch (error) {
      console.error("Error saving product:", error);
      return new Response(
        JSON.stringify({
          success: false,
          error: error instanceof Error
            ? error.message
            : "Failed to save product",
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
  },
};
