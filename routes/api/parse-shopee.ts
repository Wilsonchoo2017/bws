import { FreshContext } from "$fresh/server.ts";
import { DOMParser } from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";

interface ShopeeProduct {
  product_name: string;
  price: string;
  units_sold: string;
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
      // Extract product name - look for LEGO and 5-digit code
      let productName: string | null = null;

      // Search for text containing LEGO pattern
      const allText = item.textContent || "";
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

      // Extract price
      let price: string | null = null;
      const priceSpan = item.querySelector(
        '[class*="text-base"][class*="font-medium"]',
      );
      if (priceSpan) {
        price = priceSpan.textContent?.trim().replace(/,/g, "") || null;
      }

      // Fallback: regex search for RM price
      if (!price) {
        const priceMatch = allText.match(/RM\s*([0-9,.]+)/);
        if (priceMatch) {
          price = priceMatch[1].replace(/,/g, "");
        }
      }

      // Extract sold units
      let soldUnits: string | null = null;
      const soldDiv = item.querySelector(
        '[class*="text-shopee-black87"][class*="text-xs"]',
      );
      if (soldDiv) {
        const soldMatch = soldDiv.textContent?.match(/([0-9kK.+,]+)\s*sold/);
        if (soldMatch) {
          soldUnits = soldMatch[1].trim();
        }
      }

      // Fallback: regex search in all text
      if (!soldUnits) {
        const soldMatch = allText.match(/([0-9kK.+,]+)\s*sold/);
        if (soldMatch) {
          soldUnits = soldMatch[1].trim();
        }
      }

      if (productName) {
        products.push({
          product_name: productName,
          price: price || "N/A",
          units_sold: soldUnits || "N/A",
        });
      }
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
    } else if (contentType.includes("text/html")) {
      htmlContent = await req.text();
    } else {
      return new Response(
        JSON.stringify({
          error:
            "Invalid content type. Use 'application/json' with {html: '...'} or 'text/html'",
        }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    const products = parseShopeeHtml(htmlContent);

    return new Response(
      JSON.stringify({
        count: products.length,
        products,
      }, null, 2),
      {
        headers: { "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Unknown error",
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
};
