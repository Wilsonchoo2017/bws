import { FreshContext } from "$fresh/server.ts";
import { eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import {
  shopeeItems,
  shopeePriceHistory,
  shopeeScrapeSessions,
} from "../../db/schema.ts";
import { extractShopUsername } from "../../db/utils.ts";
import { parseShopeeHtml } from "../../utils/shopee-extractors.ts";

// Re-export type from shopee-extractors for backwards compatibility
import type { ParsedShopeeProduct } from "../../utils/shopee-extractors.ts";
type ShopeeProduct = ParsedShopeeProduct;

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  // Create a scrape session record
  let sessionId: number | null = null;
  let sessionStatus: "success" | "partial" | "failed" = "failed";
  let sessionError: string | null = null;

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

    const contentType = req.headers.get("content-type") || "";

    let htmlContent: string;
    let sourceUrl: string | undefined;

    if (contentType.includes("application/json")) {
      const body = await req.json();
      if (!body.html) {
        return new Response(
          JSON.stringify({ error: "Missing 'html' field in JSON body" }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      htmlContent = body.html;
      sourceUrl = body.source_url;
    } else if (contentType.includes("text/html")) {
      htmlContent = await req.text();
    } else {
      return new Response(
        JSON.stringify({
          error:
            "Invalid content type. Use 'application/json' with {html: '...', source_url: '...'} or 'text/html'",
        }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Extract shop username from source URL if provided
    const shopUsername = sourceUrl ? extractShopUsername(sourceUrl) : null;

    // Validate that shop username is available
    if (!shopUsername) {
      return new Response(
        JSON.stringify({
          error:
            "Shop name cannot be determined. Please provide a valid Shopee shop URL in the 'source_url' field (e.g., https://shopee.com.my/legoshopmy?shopCollection=...)",
        }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // Parse HTML to extract products
    const products = parseShopeeHtml(htmlContent, shopUsername);

    // Create scrape session
    const [session] = await db.insert(shopeeScrapeSessions).values({
      sourceUrl: sourceUrl || null,
      productsFound: products.length,
      productsStored: 0,
      status: "success",
    }).returning();

    sessionId = session.id;

    // Insert/update products in database
    let productsStored = 0;
    const insertedProducts = [];

    for (const product of products) {
      try {
        // Check if product already exists to get previous data
        const existingProduct = await db.query.shopeeItems.findFirst({
          where: eq(shopeeItems.productId, product.product_id),
        });

        // Get the most recent price history entry (before this update)
        let previousHistory = null;
        if (existingProduct) {
          const histories = await db.query.shopeePriceHistory.findMany({
            where: eq(shopeePriceHistory.productId, product.product_id),
            orderBy: (history, { desc }) => [desc(history.recordedAt)],
            limit: 1,
          });
          previousHistory = histories[0] || null;
        }

        // Upsert product into shopeeItems table
        const [insertedProduct] = await db.insert(shopeeItems).values({
          productId: product.product_id,
          name: product.product_name,
          currency: "MYR",
          price: product.price,
          unitsSold: product.units_sold,
          legoSetNumber: product.lego_set_number,
          shopId: product.shop_id,
          shopName: product.shop_name,
          image: product.image,
          rawData: {
            product_url: product.product_url,
            price_string: product.price_string,
            units_sold_string: product.units_sold_string,
          },
          updatedAt: new Date(),
        }).onConflictDoUpdate({
          target: shopeeItems.productId,
          set: {
            name: sql`EXCLUDED.name`,
            price: sql`EXCLUDED.price`,
            unitsSold: sql`EXCLUDED.units_sold`,
            legoSetNumber: sql`EXCLUDED.lego_set_number`,
            shopId: sql`EXCLUDED.shop_id`,
            shopName: sql`EXCLUDED.shop_name`,
            image: sql`EXCLUDED.image`,
            rawData: sql`EXCLUDED.raw_data`,
            updatedAt: new Date(),
          },
        }).returning();

        // Record price history - only if values have changed or it's a new product
        // This prevents duplicate entries and optimizes storage
        const shouldRecordHistory = !existingProduct || // New product, always record
          (previousHistory && (
            previousHistory.price !== product.price || // Price changed
            previousHistory.unitsSoldSnapshot !== product.units_sold // Sold units changed
          )) ||
          !previousHistory; // No previous history exists

        if (shouldRecordHistory && product.price !== null) {
          await db.insert(shopeePriceHistory).values({
            productId: product.product_id,
            price: product.price,
            unitsSoldSnapshot: product.units_sold,
          });
        }

        // Add metadata about whether this was an update
        const productWithMeta = {
          ...insertedProduct,
          wasUpdated: !!existingProduct,
          previousSold: previousHistory?.unitsSoldSnapshot || null,
          previousPrice: previousHistory?.price || null,
          soldDelta: existingProduct && product.units_sold !== null &&
              previousHistory?.unitsSoldSnapshot
            ? product.units_sold - (previousHistory.unitsSoldSnapshot || 0)
            : null,
          priceDelta:
            existingProduct && product.price !== null && previousHistory?.price
              ? product.price - (previousHistory.price || 0)
              : null,
        };

        insertedProducts.push(productWithMeta);
        productsStored++;
      } catch (productError) {
        console.error(
          `Failed to insert product ${product.product_id}:`,
          productError,
        );
        // Continue with other products
      }
    }

    // Update session with actual stored count
    await db.update(shopeeScrapeSessions).set({
      productsStored,
      status: productsStored === products.length ? "success" : "partial",
    }).where(eq(shopeeScrapeSessions.id, sessionId));

    sessionStatus = productsStored === products.length ? "success" : "partial";

    return new Response(
      JSON.stringify(
        {
          success: true,
          session_id: sessionId,
          status: sessionStatus,
          products_found: products.length,
          products_stored: productsStored,
          products: insertedProducts,
        },
        null,
        2,
      ),
      {
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    sessionError = error instanceof Error ? error.message : "Unknown error";

    // Update session with error if we have a session ID
    if (sessionId) {
      try {
        await db.update(shopeeScrapeSessions).set({
          status: "failed",
          errorMessage: sessionError,
        }).where(eq(shopeeScrapeSessions.id, sessionId));
      } catch (_updateError) {
        // Ignore errors updating session
      }
    }

    return new Response(
      JSON.stringify({
        success: false,
        session_id: sessionId,
        error: sessionError,
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
};
