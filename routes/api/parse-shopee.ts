import { FreshContext } from "$fresh/server.ts";
import { DOMParser } from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";
import { eq, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import {
  shopeeItems,
  shopeePriceHistory,
  shopeeScrapeSessions,
} from "../../db/schema.ts";
import {
  extractLegoSetNumber,
  extractShopeeProductId,
  generateProductIdFromName,
  normalizeSoldUnits,
  parsePriceToCents,
} from "../../db/utils.ts";

interface ShopeeProduct {
  product_id: string;
  product_name: string;
  price: number | null; // Price in cents
  price_string: string; // Original price string for reference
  units_sold: number | null; // Normalized sold units
  units_sold_string: string; // Original sold string for reference
  lego_set_number: string | null;
  shop_name?: string;
  shop_id?: number;
  image?: string;
  product_url?: string;
}

function parseShopeeHtml(htmlContent: string): ShopeeProduct[] {
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlContent, "text/html");

  if (!doc) {
    throw new Error("Failed to parse HTML");
  }

  const products: ShopeeProduct[] = [];

  // Find all product items
  const items = doc.querySelectorAll(".shop-search-result-view__item");

  for (let idx = 0; idx < items.length; idx++) {
    const item = items[idx];
    try {
      const allText = item.textContent || "";

      // Extract product name
      let productName: string | null = null;

      // Search for text containing LEGO pattern
      const legoMatch = allText.match(/LEGO.*\d{5}/i);
      if (legoMatch) {
        productName = legoMatch[0].trim();
      }

      // Fallback: look for line-clamp-2 class
      if (!productName) {
        const nameDiv = item.querySelector('[class*="line-clamp-2"]');
        if (nameDiv) {
          productName = nameDiv.textContent?.trim() || null;
        }
      }

      if (!productName) continue; // Skip items without names

      // Extract product URL and ID
      let productUrl: string | null = null;
      let productId: string | null = null;

      const linkElement = item.querySelector("a[href]");
      if (linkElement) {
        const href = linkElement.getAttribute("href");
        if (href) {
          // Handle relative URLs
          productUrl = href.startsWith("http")
            ? href
            : `https://shopee.com.my${href}`;
          productId = extractShopeeProductId(productUrl);
        }
      }

      // Fallback: generate ID from product name if URL-based ID not found
      if (!productId) {
        productId = generateProductIdFromName(productName);
      }

      // Extract price
      let priceStr: string | null = null;
      const priceSpan = item.querySelector(
        '[class*="text-base"][class*="font-medium"]',
      );
      if (priceSpan) {
        priceStr = priceSpan.textContent?.trim() || null;
      }

      // Fallback: regex search for RM price
      if (!priceStr) {
        const priceMatch = allText.match(/RM\s*([0-9,.]+)/);
        if (priceMatch) {
          priceStr = `RM ${priceMatch[1]}`;
        }
      }

      const price = priceStr ? parsePriceToCents(priceStr) : null;

      // Extract sold units
      let soldStr: string | null = null;
      const soldDiv = item.querySelector(
        '[class*="text-shopee-black87"][class*="text-xs"]',
      );
      if (soldDiv) {
        const soldMatch = soldDiv.textContent?.match(/([0-9kK.+,]+)\s*sold/);
        if (soldMatch) {
          soldStr = soldMatch[1].trim();
        }
      }

      // Fallback: regex search in all text
      if (!soldStr) {
        const soldMatch = allText.match(/([0-9kK.+,]+)\s*sold/);
        if (soldMatch) {
          soldStr = soldMatch[1].trim();
        }
      }

      const unitsSold = soldStr ? normalizeSoldUnits(soldStr) : null;

      // Extract LEGO set number
      const legoSetNumber = extractLegoSetNumber(productName);

      // Extract image
      let image: string | null = null;
      const imgElement = item.querySelector("img");
      if (imgElement) {
        image = imgElement.getAttribute("src") ||
          imgElement.getAttribute("data-src") || null;
      }

      // Extract shop information (if available in the HTML)
      let shopName: string | null = null;
      let shopId: number | null = null;

      // Try to find shop name in various places
      const shopNameElement = item.querySelector('[class*="shop-name"]') ||
        item.querySelector('[class*="shopName"]');
      if (shopNameElement) {
        shopName = shopNameElement.textContent?.trim() || null;
      }

      // Try to extract shop ID from URL if available
      if (productUrl && productId) {
        const shopIdMatch = productId.match(/^(\d+)-/);
        if (shopIdMatch) {
          shopId = parseInt(shopIdMatch[1], 10);
        }
      }

      products.push({
        product_id: productId,
        product_name: productName,
        price,
        price_string: priceStr || "N/A",
        units_sold: unitsSold,
        units_sold_string: soldStr || "N/A",
        lego_set_number: legoSetNumber,
        shop_name: shopName || undefined,
        shop_id: shopId || undefined,
        image: image || undefined,
        product_url: productUrl || undefined,
      });
    } catch (error) {
      console.error(`Error parsing item ${idx + 1}:`, error);
    }
  }

  return products;
}

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
    const products = parseShopeeHtml(htmlContent);

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
          sold: product.units_sold,
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
            sold: sql`EXCLUDED.sold`,
            legoSetNumber: sql`EXCLUDED.lego_set_number`,
            shopId: sql`EXCLUDED.shop_id`,
            shopName: sql`EXCLUDED.shop_name`,
            image: sql`EXCLUDED.image`,
            rawData: sql`EXCLUDED.raw_data`,
            updatedAt: new Date(),
          },
        }).returning();

        // Record price history
        if (product.price !== null) {
          await db.insert(shopeePriceHistory).values({
            productId: product.product_id,
            price: product.price,
            soldAtTime: product.units_sold,
          });
        }

        // Add metadata about whether this was an update
        const productWithMeta = {
          ...insertedProduct,
          wasUpdated: !!existingProduct,
          previousSold: previousHistory?.soldAtTime || null,
          previousPrice: previousHistory?.price || null,
          soldDelta: existingProduct && product.units_sold !== null && previousHistory?.soldAtTime
            ? product.units_sold - (previousHistory.soldAtTime || 0)
            : null,
          priceDelta: existingProduct && product.price !== null && previousHistory?.price
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
