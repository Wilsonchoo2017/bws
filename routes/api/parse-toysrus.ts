import { FreshContext } from "$fresh/server.ts";
import { eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { priceHistory, products, scrapeSessions } from "../../db/schema.ts";
import { findExistingProduct } from "../../db/utils.ts";
import { parseToysRUsHtml } from "../../utils/toysrus-extractors.ts";
import { scraperLogger } from "../../utils/logger.ts";
import { imageDownloadService } from "../../services/image/ImageDownloadService.ts";
import { imageStorageService } from "../../services/image/ImageStorageService.ts";
import { rawDataService } from "../../services/raw-data/index.ts";

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

    // Parse HTML to extract products
    scraperLogger.info('Parsing Toys"R"Us HTML', {
      sourceUrl: sourceUrl || "unknown",
      source: "toysrus",
    });

    const parsedProducts = parseToysRUsHtml(htmlContent);

    scraperLogger.info('Successfully parsed Toys"R"Us products', {
      productsFound: parsedProducts.length,
      sourceUrl: sourceUrl || "unknown",
      source: "toysrus",
    });

    // Check database for existing products and populate LEGO IDs
    const productsWithLegoIdResolution = await Promise.all(
      parsedProducts.map(async (product) => {
        // Check if product exists in database
        const existingProduct = await findExistingProduct(
          db,
          product.productId,
          product.name,
        );

        // If product exists with LEGO ID, use it
        if (existingProduct?.legoSetNumber) {
          return {
            ...product,
            legoSetNumber: existingProduct.legoSetNumber,
            _existingLegoId: existingProduct.legoSetNumber,
            _hasExistingProduct: true,
          };
        }

        // Product is new or has no LEGO ID
        return {
          ...product,
          _existingLegoId: null,
          _hasExistingProduct: !!existingProduct,
        };
      }),
    );

    // Split products into those with and without LEGO IDs
    const productsWithLegoId = productsWithLegoIdResolution.filter((p) =>
      p.legoSetNumber
    );
    const productsWithoutLegoId = productsWithLegoIdResolution.filter((p) =>
      !p.legoSetNumber
    );

    // Two-phase save: Save products with LEGO IDs first
    const finalProducts = productsWithLegoId;

    // Create scrape session
    const [session] = await db.insert(scrapeSessions).values({
      source: "toysrus",
      sourceUrl: sourceUrl || null,
      productsFound: finalProducts.length,
      productsStored: 0,
      status: "success",
    }).returning();

    sessionId = session.id;

    // Save raw HTML for debugging and testing
    await rawDataService.saveRawData({
      scrapeSessionId: sessionId,
      source: "toysrus",
      sourceUrl: sourceUrl || "unknown",
      rawHtml: htmlContent,
      contentType: "text/html",
    });

    scraperLogger.info('Created Toys"R"Us scrape session', {
      sessionId,
      productsWithLegoId: productsWithLegoId.length,
      productsWithoutLegoId: productsWithoutLegoId.length,
      source: "toysrus",
    });

    // Insert/update products in database
    let productsStored = 0;
    const insertedProducts = [];

    for (const product of finalProducts) {
      try {
        // Check if product already exists to get previous data
        const existingProduct = await db.query.products.findFirst({
          where: eq(products.productId, product.productId),
        });

        // Get the most recent price history entry (before this update)
        let previousHistory = null;
        if (existingProduct) {
          const histories = await db.query.priceHistory.findMany({
            where: eq(priceHistory.productId, product.productId),
            orderBy: (history, { desc }) => [desc(history.recordedAt)],
            limit: 1,
          });
          previousHistory = histories[0] || null;
        }

        // Upsert product into products table
        const [insertedProduct] = await db.insert(products).values({
          source: "toysrus",
          productId: product.productId,
          name: product.name,
          brand: product.brand,
          currency: "MYR",
          price: product.price,
          priceBeforeDiscount: product.priceBeforeDiscount,
          image: product.image,
          legoSetNumber: product.legoSetNumber,
          sku: product.sku,
          categoryNumber: product.categoryNumber,
          categoryName: product.categoryName,
          ageRange: product.ageRange,
          rawData: {
            product_url: product.productUrl,
            discount_percentage: product.discountPercentage,
            promotional_badges: product.promotionalBadges,
            ...product.rawData,
          },
          updatedAt: new Date(),
        }).onConflictDoUpdate({
          target: products.productId,
          set: {
            name: sql`EXCLUDED.name`,
            brand: sql`EXCLUDED.brand`,
            price: sql`EXCLUDED.price`,
            priceBeforeDiscount: sql`EXCLUDED.price_before_discount`,
            image: sql`EXCLUDED.image`,
            legoSetNumber: sql`EXCLUDED.lego_set_number`,
            sku: sql`EXCLUDED.sku`,
            categoryNumber: sql`EXCLUDED.category_number`,
            categoryName: sql`EXCLUDED.category_name`,
            ageRange: sql`EXCLUDED.age_range`,
            rawData: sql`EXCLUDED.raw_data`,
            updatedAt: new Date(),
          },
        }).returning();

        // Record price history - only if values have changed or it's a new product
        const shouldRecordHistory = !existingProduct || // New product, always record
          (previousHistory && (
            previousHistory.price !== product.price || // Price changed
            previousHistory.priceBeforeDiscount !== product.priceBeforeDiscount // Discount changed
          )) ||
          !previousHistory; // No previous history exists

        if (shouldRecordHistory && product.price !== null) {
          await db.insert(priceHistory).values({
            productId: product.productId,
            price: product.price,
            priceBeforeDiscount: product.priceBeforeDiscount,
            unitsSoldSnapshot: null, // Toys"R"Us doesn't have units sold
          });
        }

        // Download and store image locally if available
        if (product.image) {
          try {
            scraperLogger.info('Downloading image for Toys"R"Us product', {
              productId: product.productId,
              imageUrl: product.image,
              source: "toysrus",
            });

            // Download the image
            const imageData = await imageDownloadService.download(
              product.image,
            );

            // Store the image locally
            const storageResult = await imageStorageService.store(
              imageData.data,
              imageData.url,
              imageData.extension,
              product.productId,
            );

            // Update the product with local image path
            await db.update(products).set({
              localImagePath: storageResult.relativePath,
              imageDownloadedAt: new Date(),
              imageDownloadStatus: "completed",
            }).where(eq(products.productId, product.productId));

            scraperLogger.info("Successfully downloaded and stored image", {
              productId: product.productId,
              localPath: storageResult.relativePath,
              source: "toysrus",
            });
          } catch (imageError) {
            // Log error but don't fail the entire product save
            scraperLogger.error("Error downloading/storing image", {
              productId: product.productId,
              error: (imageError as Error).message,
              source: "toysrus",
            });

            // Mark as failed in database
            try {
              await db.update(products).set({
                imageDownloadStatus: "failed",
              }).where(eq(products.productId, product.productId));
            } catch (_updateError) {
              // Ignore errors updating status
            }
          }
        }

        // Add metadata about whether this was an update
        const productWithMeta = {
          ...insertedProduct,
          wasUpdated: !!existingProduct,
          previousPrice: previousHistory?.price || null,
          previousPriceBeforeDiscount: previousHistory?.priceBeforeDiscount ||
            null,
          priceDelta:
            existingProduct && product.price !== null && previousHistory?.price
              ? product.price - (previousHistory.price || 0)
              : null,
        };

        insertedProducts.push(productWithMeta);
        productsStored++;

        scraperLogger.info('Saved Toys"R"Us product to database', {
          productId: product.productId,
          productName: product.name,
          price: product.price,
          priceBeforeDiscount: product.priceBeforeDiscount,
          wasUpdated: !!existingProduct,
          sessionId,
          source: "toysrus",
        });
      } catch (productError) {
        scraperLogger.error('Failed to insert Toys"R"Us product', {
          productId: product.productId,
          error: (productError as Error).message,
          sessionId,
          source: "toysrus",
        });
        // Continue with other products
      }
    }

    // Update session with actual stored count
    await db.update(scrapeSessions).set({
      productsStored,
      status: productsStored === finalProducts.length ? "success" : "partial",
    }).where(eq(scrapeSessions.id, sessionId));

    sessionStatus = productsStored === finalProducts.length
      ? "success"
      : "partial";

    scraperLogger.info('Completed Toys"R"Us scrape session', {
      sessionId,
      productsStored,
      totalProducts: finalProducts.length,
      status: sessionStatus,
      productsWithoutLegoId: productsWithoutLegoId.length,
      source: "toysrus",
    });

    // If there are products without LEGO IDs, return them for manual validation
    // along with the session info and already-saved products
    if (productsWithoutLegoId.length > 0) {
      return new Response(
        JSON.stringify({
          success: false,
          requiresValidation: true,
          session_id: sessionId,
          alreadySaved: insertedProducts,
          productsNeedingValidation: productsWithoutLegoId.map((p) => ({
            productName: p.name,
            price: p.price,
            priceBeforeDiscount: p.priceBeforeDiscount,
            image: p.image,
            productUrl: p.productUrl,
            brand: p.brand,
            sku: p.sku,
            // Include original product data for saving later
            _originalData: p,
          })),
          message:
            `${productsStored} product(s) saved. ${productsWithoutLegoId.length} product(s) need LEGO ID validation.`,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // All products saved successfully
    return new Response(
      JSON.stringify(
        {
          success: true,
          session_id: sessionId,
          status: sessionStatus,
          products_found: finalProducts.length,
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

    scraperLogger.error('Error parsing Toys"R"Us HTML', {
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
      sessionId,
      source: "toysrus",
    });

    // Update session with error if we have a session ID
    if (sessionId) {
      try {
        await db.update(scrapeSessions).set({
          status: "failed",
          errorMessage: sessionError,
        }).where(eq(scrapeSessions.id, sessionId));
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
