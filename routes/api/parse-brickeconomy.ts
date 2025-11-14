import { FreshContext } from "$fresh/server.ts";
import { eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { priceHistory, products, scrapeSessions } from "../../db/schema.ts";
import { parseBrickEconomyHtml } from "../../utils/brickeconomy-extractors.ts";
import { scraperLogger } from "../../utils/logger.ts";
import { imageDownloadService } from "../../services/image/ImageDownloadService.ts";
import { imageStorageService } from "../../services/image/ImageStorageService.ts";
import { rawDataService } from "../../services/raw-data/index.ts";

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
    scraperLogger.info("Parsing BrickEconomy HTML", {
      sourceUrl: sourceUrl || "unknown",
      source: "brickeconomy",
    });

    const parsedProduct = parseBrickEconomyHtml(htmlContent);

    if (!parsedProduct) {
      scraperLogger.warn("Failed to parse BrickEconomy HTML", {
        sourceUrl: sourceUrl || "unknown",
        source: "brickeconomy",
      });
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

    scraperLogger.info("Successfully parsed BrickEconomy product", {
      productId: parsedProduct.product_id,
      productName: parsedProduct.product_name,
      legoSetNumber: parsedProduct.lego_set_number,
      marketValue: parsedProduct.market_value,
      sourceUrl: sourceUrl || "unknown",
      source: "brickeconomy",
    });

    // Create scrape session
    const [session] = await db.insert(scrapeSessions).values({
      source: "brickeconomy",
      sourceUrl: sourceUrl || null,
      productsFound: 1,
      productsStored: 0,
      status: "success",
    }).returning();

    sessionId = session.id;

    // Save raw HTML for debugging and testing
    await rawDataService.saveRawData({
      scrapeSessionId: sessionId,
      source: "brickeconomy",
      sourceUrl: sourceUrl || "unknown",
      rawHtml: htmlContent,
      contentType: "text/html",
    });

    scraperLogger.info("Created BrickEconomy scrape session", {
      sessionId,
      productId: parsedProduct.product_id,
      source: "brickeconomy",
    });

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

      scraperLogger.info("Recorded BrickEconomy price history", {
        productId: parsedProduct.product_id,
        price: productPrice,
        priceBeforeDiscount: priceBeforeDiscount,
        previousPrice: previousHistory?.price || null,
        isNewProduct: !existingProduct,
        source: "brickeconomy",
      });
    }

    // Download and store image locally if available
    if (parsedProduct.image) {
      try {
        scraperLogger.info("Downloading image for BrickEconomy product", {
          productId: parsedProduct.product_id,
          imageUrl: parsedProduct.image,
          source: "brickeconomy",
        });

        // Download the image
        const imageData = await imageDownloadService.download(
          parsedProduct.image,
        );

        // Store the image locally
        const storageResult = await imageStorageService.store(
          imageData.data,
          imageData.url,
          imageData.extension,
          parsedProduct.product_id,
        );

        // Update the product with local image path
        await db.update(products).set({
          localImagePath: storageResult.relativePath,
          imageDownloadedAt: new Date(),
          imageDownloadStatus: "completed",
        }).where(eq(products.productId, parsedProduct.product_id));

        scraperLogger.info("Successfully downloaded and stored image", {
          productId: parsedProduct.product_id,
          localPath: storageResult.relativePath,
          source: "brickeconomy",
        });
      } catch (imageError) {
        // Log error but don't fail the entire product save
        scraperLogger.error("Error downloading/storing image", {
          productId: parsedProduct.product_id,
          error: (imageError as Error).message,
          source: "brickeconomy",
        });

        // Mark as failed in database
        try {
          await db.update(products).set({
            imageDownloadStatus: "failed",
          }).where(eq(products.productId, parsedProduct.product_id));
        } catch (_updateError) {
          // Ignore errors updating status
        }
      }
    }

    // Update session with success status
    await db.update(scrapeSessions)
      .set({
        productsStored: 1,
        status: "success",
      })
      .where(eq(scrapeSessions.id, sessionId));

    scraperLogger.info("Successfully saved BrickEconomy product to database", {
      productId: parsedProduct.product_id,
      sessionId,
      wasUpdated: !!existingProduct,
      priceRecorded: shouldRecordHistory,
      source: "brickeconomy",
    });

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
    sessionError = error instanceof Error ? error.message : "Unknown error";
    _sessionStatus = "failed";

    scraperLogger.error("Error parsing BrickEconomy HTML", {
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
      sessionId,
      source: "brickeconomy",
    });

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
