import { FreshContext } from "$fresh/server.ts";
import { desc, eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { products, scrapeSessions, shopeeScrapes } from "../../db/schema.ts";
import { extractShopUsername, findExistingProduct } from "../../db/utils.ts";
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
    const parsedProducts = parseShopeeHtml(htmlContent, shopUsername);

    // Check database for existing products and populate LEGO IDs
    const productsWithLegoIdResolution = await Promise.all(
      parsedProducts.map(async (product) => {
        // Check if product exists in database
        const existingProduct = await findExistingProduct(
          db,
          product.product_id,
          product.product_name,
        );

        // If product exists with LEGO ID, use it
        if (existingProduct?.legoSetNumber) {
          return {
            ...product,
            lego_set_number: existingProduct.legoSetNumber,
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
      p.lego_set_number
    );
    const productsWithoutLegoId = productsWithLegoIdResolution.filter((p) =>
      !p.lego_set_number
    );

    // Two-phase save: Save products with LEGO IDs first
    const finalProducts = productsWithLegoId;

    // Create scrape session
    const [session] = await db.insert(scrapeSessions).values({
      source: "shopee",
      sourceUrl: sourceUrl || null,
      productsFound: finalProducts.length,
      productsStored: 0,
      status: "success",
    }).returning();

    sessionId = session.id;

    // Insert/update products in database
    let productsStored = 0;
    const insertedProducts = [];

    for (const product of finalProducts) {
      try {
        // Check if product already exists to get previous data
        const existingProduct = await db.query.products.findFirst({
          where: eq(products.productId, product.product_id),
        });

        // Get the most recent scrape entry (before this update)
        let previousScrape = null;
        if (existingProduct) {
          const scrapes = await db.query.shopeeScrapes.findMany({
            where: eq(shopeeScrapes.productId, product.product_id),
            orderBy: [desc(shopeeScrapes.scrapedAt)],
            limit: 1,
          });
          previousScrape = scrapes[0] || null;
        }

        // Upsert product into products table
        const [insertedProduct] = await db.insert(products).values({
          source: "shopee",
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
          target: products.productId,
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

        // Always insert a new scrape record - this is a complete snapshot at this point in time
        await db.insert(shopeeScrapes).values({
          productId: product.product_id,
          scrapeSessionId: sessionId,
          price: product.price,
          currency: "MYR",
          unitsSold: product.units_sold,
          shopId: product.shop_id,
          shopName: product.shop_name,
          productUrl: product.product_url,
          rawData: {
            product_url: product.product_url,
            price_string: product.price_string,
            units_sold_string: product.units_sold_string,
          },
        });

        // Calculate deltas and price change percentage
        const previousPrice = previousScrape?.price || null;
        const previousSold = previousScrape?.unitsSold || null;
        const priceDelta =
          existingProduct && product.price !== null && previousPrice
            ? product.price - previousPrice
            : null;
        const soldDelta =
          existingProduct && product.units_sold !== null && previousSold
            ? product.units_sold - previousSold
            : null;
        const priceChangePercent = previousPrice && priceDelta
          ? Math.round((priceDelta / previousPrice) * 10000) / 100 // 2 decimal places
          : null;

        // Add metadata about whether this was an update
        const productWithMeta = {
          ...insertedProduct,
          wasUpdated: !!existingProduct,
          previousSold,
          previousPrice,
          soldDelta,
          priceDelta,
          priceChangePercent,
          isNew: !existingProduct,
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
    await db.update(scrapeSessions).set({
      productsStored,
      status: productsStored === finalProducts.length ? "success" : "partial",
    }).where(eq(scrapeSessions.id, sessionId));

    sessionStatus = productsStored === finalProducts.length
      ? "success"
      : "partial";

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
            productName: p.product_name,
            price: p.price,
            priceString: p.price_string,
            unitsSold: p.units_sold,
            unitsSoldString: p.units_sold_string,
            image: p.image,
            productUrl: p.product_url,
            shopName: p.shop_name,
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
