import { FreshContext } from "$fresh/server.ts";
import { DOMParser } from "https://deno.land/x/deno_dom@v0.1.45/deno-dom-wasm.ts";
import { db } from "../../db/client.ts";
import { bricklinkItems, bricklinkPriceHistory } from "../../db/schema.ts";
import { eq, desc } from "drizzle-orm";

interface PriceData {
  currency: string;
  amount: number;
}

interface PricingBox {
  times_sold?: number;
  total_lots?: number;
  total_qty?: number;
  min_price?: PriceData;
  avg_price?: PriceData;
  qty_avg_price?: PriceData;
  max_price?: PriceData;
}

interface BricklinkData {
  item_id: string;
  item_type: string;
  title: string | null;
  weight: string | null;
  six_month_new: PricingBox | null;
  six_month_used: PricingBox | null;
  current_new: PricingBox | null;
  current_used: PricingBox | null;
}

const RE_TIMES_SOLD = /Times Sold:\s*(\d+)/i;
const RE_TOTAL_LOTS = /Total Lots:\s*(\d+)/i;
const RE_TOTAL_QTY = /Total Qty:\s*(\d+)/i;
const RE_MIN_PRICE = /Min Price:\s*([A-Z]+)\s+([\d,\.]+)/i;
const RE_AVG_PRICE = /Avg Price:\s*([A-Z]+)\s+([\d,\.]+)/i;
const RE_QTY_AVG_PRICE = /Qty Avg Price:\s*([A-Z]+)\s+([\d,\.]+)/i;
const RE_MAX_PRICE = /Max Price:\s*([A-Z]+)\s+([\d,\.]+)/i;

function extractPriceBox(boxElement: Element): PricingBox | null {
  const text = boxElement.textContent || "";

  // Check if box has "(unavailable)" message
  if (text.toLowerCase().includes("(unavailable)")) {
    return null;
  }

  const data: PricingBox = {};

  // Extract counts
  const timesSold = text.match(RE_TIMES_SOLD);
  if (timesSold) data.times_sold = parseInt(timesSold[1]);

  const totalLots = text.match(RE_TOTAL_LOTS);
  if (totalLots) data.total_lots = parseInt(totalLots[1]);

  const totalQty = text.match(RE_TOTAL_QTY);
  if (totalQty) data.total_qty = parseInt(totalQty[1]);

  // Extract prices
  const minPrice = text.match(RE_MIN_PRICE);
  if (minPrice) {
    data.min_price = {
      currency: minPrice[1].toUpperCase(),
      amount: parseFloat(minPrice[2].replace(/,/g, "")),
    };
  }

  const avgPrice = text.match(RE_AVG_PRICE);
  if (avgPrice) {
    data.avg_price = {
      currency: avgPrice[1].toUpperCase(),
      amount: parseFloat(avgPrice[2].replace(/,/g, "")),
    };
  }

  const qtyAvgPrice = text.match(RE_QTY_AVG_PRICE);
  if (qtyAvgPrice) {
    data.qty_avg_price = {
      currency: qtyAvgPrice[1].toUpperCase(),
      amount: parseFloat(qtyAvgPrice[2].replace(/,/g, "")),
    };
  }

  const maxPrice = text.match(RE_MAX_PRICE);
  if (maxPrice) {
    data.max_price = {
      currency: maxPrice[1].toUpperCase(),
      amount: parseFloat(maxPrice[2].replace(/,/g, "")),
    };
  }

  return Object.keys(data).length > 0 ? data : null;
}

function hasDataChanged(
  oldData: PricingBox | null,
  newData: PricingBox | null,
): boolean {
  // If one is null and the other isn't, it's a change
  if ((oldData === null) !== (newData === null)) return true;
  if (oldData === null && newData === null) return false;

  // Deep comparison of pricing data
  return JSON.stringify(oldData) !== JSON.stringify(newData);
}

async function scrapeBricklinkItem(url: string): Promise<BricklinkData> {
  // Parse URL to extract item type and ID
  const urlObj = new URL(url);
  const params = new URLSearchParams(urlObj.search);

  let itemType: string | null = null;
  let itemId: string | null = null;

  // Detect item type (P, S, M, G, C, I, O, B)
  for (const key of ["P", "S", "M", "G", "C", "I", "O", "B"]) {
    if (params.has(key)) {
      itemType = key;
      itemId = params.get(key);
      break;
    }
  }

  if (!itemType || !itemId) {
    throw new Error(`Could not extract item type and ID from URL: ${url}`);
  }

  const headers = {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
  };

  // Fetch main item page for basic info
  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`Failed to fetch item page: ${response.statusText}`);
  }

  const html = await response.text();
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  if (!doc) {
    throw new Error("Failed to parse HTML");
  }

  // Extract basic info
  const titleElem = doc.querySelector("h1#item-name-title");
  const title = titleElem?.textContent?.trim() || null;

  const weightElem = doc.querySelector("span#item-weight-info");
  const weight = weightElem?.textContent?.trim() || null;

  // Fetch price guide page
  const priceGuideUrl =
    `https://www.bricklink.com/catalogPG.asp?${itemType}=${itemId}`;
  const priceResponse = await fetch(priceGuideUrl, { headers });
  if (!priceResponse.ok) {
    throw new Error(
      `Failed to fetch price guide: ${priceResponse.statusText}`,
    );
  }

  const priceHtml = await priceResponse.text();
  const priceDoc = parser.parseFromString(priceHtml, "text/html");

  if (!priceDoc) {
    throw new Error("Failed to parse price guide HTML");
  }

  // Extract pricing boxes (4 boxes: 6mo new, 6mo used, current new, current used)
  const priceBoxes = priceDoc.querySelectorAll(
    "#id-main-legacy-table > tr table > tr:nth-of-type(3) > td > table > tr > td",
  );

  const pricingData: {
    six_month_new: PricingBox | null;
    six_month_used: PricingBox | null;
    current_new: PricingBox | null;
    current_used: PricingBox | null;
  } = {
    six_month_new: null,
    six_month_used: null,
    current_new: null,
    current_used: null,
  };

  if (priceBoxes.length >= 4) {
    pricingData.six_month_new = extractPriceBox(priceBoxes[0]);
    pricingData.six_month_used = extractPriceBox(priceBoxes[1]);
    pricingData.current_new = extractPriceBox(priceBoxes[2]);
    pricingData.current_used = extractPriceBox(priceBoxes[3]);
  }

  return {
    item_id: itemId,
    item_type: itemType,
    title,
    weight,
    ...pricingData,
  };
}

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    const url = new URL(req.url);
    const bricklinkUrl = url.searchParams.get("url");
    const saveToDb = url.searchParams.get("save") === "true";

    if (!bricklinkUrl) {
      return new Response(
        JSON.stringify({ error: "Missing 'url' query parameter" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    const result = await scrapeBricklinkItem(bricklinkUrl);

    // Optionally save to database
    if (saveToDb) {
      try {
        // Check if item already exists
        const existingItem = await db.query.bricklinkItems.findFirst({
          where: eq(bricklinkItems.itemId, result.item_id),
        });

        if (existingItem) {
          // Update existing item
          await db.update(bricklinkItems)
            .set({
              title: result.title,
              weight: result.weight,
              sixMonthNew: result.six_month_new,
              sixMonthUsed: result.six_month_used,
              currentNew: result.current_new,
              currentUsed: result.current_used,
              updatedAt: new Date(),
            })
            .where(eq(bricklinkItems.itemId, result.item_id));

          // Record price history if watch status is active and data has changed
          if (existingItem.watchStatus === "active") {
            const hasChanged = hasDataChanged(
              existingItem.sixMonthNew as PricingBox | null,
              result.six_month_new,
            ) ||
              hasDataChanged(
                existingItem.sixMonthUsed as PricingBox | null,
                result.six_month_used,
              ) ||
              hasDataChanged(
                existingItem.currentNew as PricingBox | null,
                result.current_new,
              ) ||
              hasDataChanged(
                existingItem.currentUsed as PricingBox | null,
                result.current_used,
              );

            if (hasChanged) {
              await db.insert(bricklinkPriceHistory).values({
                itemId: result.item_id,
                sixMonthNew: result.six_month_new,
                sixMonthUsed: result.six_month_used,
                currentNew: result.current_new,
                currentUsed: result.current_used,
              });
            }
          }
        } else {
          // Insert new item (defaults to 'active' watch status)
          await db.insert(bricklinkItems).values({
            itemId: result.item_id,
            itemType: result.item_type,
            title: result.title,
            weight: result.weight,
            sixMonthNew: result.six_month_new,
            sixMonthUsed: result.six_month_used,
            currentNew: result.current_new,
            currentUsed: result.current_used,
          });

          // Record initial price history for new items
          await db.insert(bricklinkPriceHistory).values({
            itemId: result.item_id,
            sixMonthNew: result.six_month_new,
            sixMonthUsed: result.six_month_used,
            currentNew: result.current_new,
            currentUsed: result.current_used,
          });
        }

        return new Response(
          JSON.stringify({ ...result, saved: true }, null, 2),
          {
            headers: { "Content-Type": "application/json" },
          },
        );
      } catch (dbError) {
        console.error("Database error:", dbError);
        // Return scraped data even if DB save fails
        return new Response(
          JSON.stringify(
            {
              ...result,
              saved: false,
              db_error: dbError instanceof Error
                ? dbError.message
                : "Unknown database error",
            },
            null,
            2,
          ),
          {
            headers: { "Content-Type": "application/json" },
          },
        );
      }
    }

    return new Response(JSON.stringify(result, null, 2), {
      headers: { "Content-Type": "application/json" },
    });
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
