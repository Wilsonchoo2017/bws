/**
 * Script to manually add Shopee LEGO set from the sample HTML file
 * This version directly inserts into the database without needing the API server
 *
 * Usage: deno run --allow-read --allow-net --allow-env scripts/add-shopee-sample-direct.ts [--lego-set 77243]
 */

import { parseArgs } from "jsr:@std/cli/parse-args";
import { db } from "../db/client.ts";
import { products, scrapeSessions, shopeeScrapes } from "../db/schema.ts";
import { parseShopeeHtml } from "../utils/shopee-extractors.ts";
import { rawDataService } from "../services/raw-data/index.ts";
import { sql } from "drizzle-orm";

const SAMPLE_FILE_PATH = "./sample/shopee-element example.txt";

async function main() {
  const args = parseArgs(Deno.args, {
    string: ["lego-set", "shop-name"],
    alias: {
      l: "lego-set",
      s: "shop-name",
    },
  });

  // Read the sample HTML file
  console.log(`Reading sample file: ${SAMPLE_FILE_PATH}`);
  const htmlContent = await Deno.readTextFile(SAMPLE_FILE_PATH);

  if (!htmlContent) {
    console.error("❌ Sample file is empty");
    Deno.exit(1);
  }

  console.log(`✓ Loaded ${htmlContent.length} characters from sample file`);

  // Shop name for parsing (default to a generic shop)
  const shopName = args["shop-name"] || "legoshopmy";
  console.log(`Using shop name: ${shopName}`);

  // Parse the Shopee HTML
  console.log("\n📦 Parsing Shopee HTML...");
  const parsedProducts = parseShopeeHtml(htmlContent, shopName);

  console.log(`✓ Found ${parsedProducts.length} product(s)`);

  if (parsedProducts.length === 0) {
    console.error("❌ No products found in sample HTML");
    Deno.exit(1);
  }

  // Display parsed products
  console.log("\n📋 Parsed Products:");
  for (const [index, product] of parsedProducts.entries()) {
    console.log(`\n[${index + 1}] ${product.product_name}`);
    console.log(`    Price: ${product.price_string} (${product.price} cents)`);
    console.log(`    Units Sold: ${product.units_sold_string} (${product.units_sold})`);
    console.log(`    Product URL: ${product.product_url}`);
    console.log(`    Shop: ${product.shop_name} (ID: ${product.shop_id})`);
    console.log(`    Image: ${product.image}`);
    console.log(`    LEGO Set #: ${product.lego_set_number || "NOT DETECTED"}`);
  }

  // Ask for LEGO set number if not provided
  const legoSetNumber = args["lego-set"];

  if (!legoSetNumber) {
    console.log("\n⚠️  No LEGO set number provided.");
    console.log("💡 Run again with --lego-set to assign:");
    console.log(
      "   deno run --allow-read --allow-net --allow-env scripts/add-shopee-sample-direct.ts --lego-set 77243",
    );
    console.log("\nExiting without saving to database.");
    Deno.exit(0);
  }

  // Create scrape session
  console.log("\n💾 Creating scrape session...");
  const [session] = await db.insert(scrapeSessions).values({
    source: "shopee",
    sourceUrl: `https://shopee.com.my/${shopName}`,
    productsFound: parsedProducts.length,
    productsStored: 0,
    status: "success",
    sessionLabel: "Manual import from sample",
  }).returning();

  console.log(`✓ Created session ID: ${session.id}`);

  // Save raw HTML
  await rawDataService.saveRawData({
    scrapeSessionId: session.id,
    source: "shopee",
    sourceUrl: `https://shopee.com.my/${shopName}`,
    rawHtml: htmlContent,
    contentType: "text/html",
  });

  console.log("✓ Saved raw HTML data");

  // Insert products
  let productsStored = 0;

  for (const product of parsedProducts) {
    try {
      console.log(`\n💾 Saving: ${product.product_name}...`);

      // Upsert product into products table
      const [insertedProduct] = await db.insert(products).values({
        source: "shopee",
        productId: product.product_id,
        name: product.product_name,
        currency: "MYR",
        price: product.price,
        priceBeforeDiscount: product.price_before_discount,
        unitsSold: product.units_sold,
        legoSetNumber: legoSetNumber, // Use manually provided LEGO set number
        shopId: product.shop_id,
        shopName: product.shop_name,
        image: product.image,
        rawData: {
          product_url: product.product_url,
          price_string: product.price_string,
          units_sold_string: product.units_sold_string,
          discount_percentage: product.discount_percentage,
          promotional_badges: product.promotional_badges,
        },
        updatedAt: new Date(),
      }).onConflictDoUpdate({
        target: products.productId,
        set: {
          name: sql`EXCLUDED.name`,
          price: sql`EXCLUDED.price`,
          priceBeforeDiscount: sql`EXCLUDED.price_before_discount`,
          unitsSold: sql`EXCLUDED.units_sold`,
          legoSetNumber: sql`EXCLUDED.lego_set_number`,
          shopId: sql`EXCLUDED.shop_id`,
          shopName: sql`EXCLUDED.shop_name`,
          image: sql`EXCLUDED.image`,
          rawData: sql`EXCLUDED.raw_data`,
          updatedAt: new Date(),
        },
      }).returning();

      console.log(`   ✓ Product saved (ID: ${insertedProduct.productId})`);

      // Insert scrape record
      await db.insert(shopeeScrapes).values({
        productId: product.product_id,
        scrapeSessionId: session.id,
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
          discount_percentage: product.discount_percentage,
          promotional_badges: product.promotional_badges,
          price_before_discount: product.price_before_discount,
        },
      });

      console.log(`   ✓ Scrape record saved`);

      productsStored++;
    } catch (error) {
      console.error(`   ❌ Error saving product: ${error}`);
    }
  }

  // Update session
  await db.update(scrapeSessions).set({
    productsStored,
  }).where(sql`${scrapeSessions.id} = ${session.id}`);

  console.log(
    `\n✅ Done! Saved ${productsStored}/${parsedProducts.length} products`,
  );
  console.log(`   Session ID: ${session.id}`);
  console.log(`   LEGO Set #: ${legoSetNumber}`);
}

// Run the script
if (import.meta.main) {
  main().catch((error) => {
    console.error("❌ Error:", error);
    Deno.exit(1);
  });
}
