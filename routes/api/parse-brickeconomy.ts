import { FreshContext } from "$fresh/server.ts";
import { eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { priceHistory, products, scrapeSessions } from "../../db/schema.ts";
import {
  findProductsByBaseSetNumber,
  normalizeLegoSetNumber,
} from "../../db/utils.ts";
import { parseBrickEconomyHtml } from "../../utils/brickeconomy-extractors.ts";
import { calculateSimilarity } from "../../utils/string-similarity.ts";

// Re-export type from brickeconomy-extractors for backwards compatibility
import type { ParsedBrickEconomyProduct } from "../../utils/brickeconomy-extractors.ts";
type BrickEconomyProduct = ParsedBrickEconomyProduct;


export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  // Create a scrape session record
  let sessionId: number | null = null;
  let _sessionStatus: "success" | "partial" | "failed" = "failed";
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

    // Parse HTML to extract product
    const parsedProduct = parseBrickEconomyHtml(htmlContent);

    if (!parsedProduct) {
      return new Response(
        JSON.stringify({
          error:
            "Failed to parse BrickEconomy HTML. Make sure you're using a product detail page HTML.",
        }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }


    // Create scrape session
    const [session] = await db.insert(scrapeSessions).values({
      source: "brickeconomy",
      sourceUrl: sourceUrl || null,
      productsFound: 1,
      productsStored: 0,
      status: "success",
    }).returning();

    sessionId = session.id;

    // Check if BrickEconomy product already exists
    const existingProduct = await db.query.products.findFirst({
      where: eq(products.productId, parsedProduct.product_id),
    });

    // Get the most recent price history entry (before this update)
    let previousHistory = null;
    if (existingProduct) {
      const histories = await db.query.priceHistory.findMany({
        where: eq(priceHistory.productId, parsedProduct.product_id),
        orderBy: (history, { desc }) => [desc(history.recordedAt)],
        limit: 1,
      });
      previousHistory = histories[0] || null;
    }

    // Map BrickEconomy data to product schema
    // Use market value (new/sealed) as primary price
    const productPrice = parsedProduct.market_value;
    const priceBeforeDiscount = parsedProduct.retail_price;

    // Upsert product into products table
    const [insertedProduct] = await db.insert(products).values({
      source: "brickeconomy",
      productId: parsedProduct.product_id,
      name: parsedProduct.product_name,
      brand: parsedProduct.brand,
      currency: "USD", // BrickEconomy uses USD
      price: productPrice,
      priceBeforeDiscount: priceBeforeDiscount,
      legoSetNumber: parsedProduct.lego_set_number,
      image: parsedProduct.image,
      rawData: parsedProduct.raw_data,
      updatedAt: new Date(),
    }).onConflictDoUpdate({
      target: products.productId,
      set: {
        name: sql`EXCLUDED.name`,
        brand: sql`EXCLUDED.brand`,
        price: sql`EXCLUDED.price`,
        priceBeforeDiscount: sql`EXCLUDED.price_before_discount`,
        legoSetNumber: sql`EXCLUDED.lego_set_number`,
        image: sql`EXCLUDED.image`,
        rawData: sql`EXCLUDED.raw_data`,
        updatedAt: new Date(),
      },
    }).returning();

    // Record price history - only if values have changed or it's a new product
    const shouldRecordHistory = !existingProduct || // New product, always record
      (previousHistory && (
        previousHistory.price !== productPrice || // Price changed
        previousHistory.priceBeforeDiscount !== priceBeforeDiscount // MSRP changed
      )) ||
      !previousHistory; // No previous history exists

    if (shouldRecordHistory && productPrice !== null) {
      await db.insert(priceHistory).values({
        productId: parsedProduct.product_id,
        price: productPrice,
        priceBeforeDiscount: priceBeforeDiscount,
      });
    }

    // Update session with success status
    await db.update(scrapeSessions)
      .set({
        productsStored: 1,
        status: "success",
      })
      .where(eq(scrapeSessions.id, sessionId));

    // Add metadata about whether this was an update
    const productWithMeta = {
      ...insertedProduct,
      wasUpdated: !!existingProduct,
      previousPrice: previousHistory?.price || null,
      previousMSRP: previousHistory?.priceBeforeDiscount || null,
      priceDelta: existingProduct && productPrice !== null &&
          previousHistory?.price
        ? productPrice - previousHistory.price
        : null,
      // Add BrickEconomy-specific metadata
      brickeconomy: {
        growth: parsedProduct.growth_percent,
        annualGrowth: parsedProduct.annual_growth_percent,
        growth90day: parsedProduct.growth_90day_percent,
        forecast1year: parsedProduct.forecast_1year,
        forecast5year: parsedProduct.forecast_5year,
        pieces: parsedProduct.pieces,
        minifigs: parsedProduct.minifigs,
        ppp: parsedProduct.ppp,
        availability: parsedProduct.availability,
      },
    };

    _sessionStatus = "success";

    return new Response(
      JSON.stringify({
        success: true,
        sessionId: sessionId,
        product: productWithMeta,
        message: "Product saved successfully.",
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    console.error("Error parsing BrickEconomy HTML:", error);

    sessionError = error instanceof Error ? error.message : "Unknown error";
    _sessionStatus = "failed";

    // Update session with failed status if session was created
    if (sessionId) {
      await db.update(scrapeSessions)
        .set({
          status: "failed",
          errorMessage: sessionError,
        })
        .where(eq(scrapeSessions.id, sessionId));
    }

    return new Response(
      JSON.stringify({
        error: "Failed to parse and store product data",
        details: error instanceof Error ? error.message : String(error),
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
};
