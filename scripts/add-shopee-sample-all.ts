/**
 * Script to add ALL Shopee LEGO sets from the sample HTML file
 * This saves all products that have LEGO set numbers detected
 *
 * Usage: deno run --allow-read --allow-write --allow-net --allow-env scripts/add-shopee-sample-all.ts
 */

import { db } from "../db/client.ts";
import { products, scrapeSessions, shopeeScrapes } from "../db/schema.ts";
import { parseShopeeHtml } from "../utils/shopee-extractors.ts";
import { rawDataService } from "../services/raw-data/index.ts";
import { sql } from "drizzle-orm";

const SAMPLE_FILE_PATH = "./sample/shopee-element example.txt";
const SHOP_NAME = "legoshopmy";

async function main() {
  // Read the sample HTML file
  console.log(`📖 Reading sample file: ${SAMPLE_FILE_PATH}`);
  const htmlContent = await Deno.readTextFile(SAMPLE_FILE_PATH);

  if (!htmlContent) {
    console.error("❌ Sample file is empty");
    Deno.exit(1);
  }

  console.log(`✓ Loaded ${htmlContent.length} characters from sample file`);

  // Parse the Shopee HTML
  console.log(`\n📦 Parsing Shopee HTML from shop: ${SHOP_NAME}...`);
  const parsedProducts = parseShopeeHtml(htmlContent, SHOP_NAME);

  console.log(`✓ Found ${parsedProducts.length} product(s)`);

  if (parsedProducts.length === 0) {
    console.error("❌ No products found in sample HTML");
    Deno.exit(1);
  }

  // Filter products with LEGO set numbers
  const productsWithLegoSet = parsedProducts.filter((p) => p.lego_set_number);
  const productsWithoutLegoSet = parsedProducts.filter((p) =>
    !p.lego_set_number
  );

  console.log(`\n📊 Product breakdown:`);
  console.log(`   ✓ With LEGO set #: ${productsWithLegoSet.length}`);
  console.log(`   ⚠️  Without LEGO set #: ${productsWithoutLegoSet.length}`);

  if (productsWithLegoSet.length === 0) {
    console.error("❌ No products with LEGO set numbers found");
    Deno.exit(1);
  }

  // Display products to be saved
  console.log(`\n📋 Products to be saved:`);
  for (const [index, product] of productsWithLegoSet.entries()) {
    console.log(
      `[${index + 1}] ${product.lego_set_number}: ${product.product_name}`,
    );
  }

  // Confirm
  console.log(`\n⚠️  About to save ${productsWithLegoSet.length} products.`);
  console.log("Press Ctrl+C to cancel, or Enter to continue...");
  await new Promise((resolve) => {
    const buf = new Uint8Array(1);
    Deno.stdin.read(buf).then(resolve);
  });

  // Create scrape session
  console.log("\n💾 Creating scrape session...");
  const [session] = await db.insert(scrapeSessions).values({
    source: "shopee",
    sourceUrl: `https://shopee.com.my/${SHOP_NAME}`,
    productsFound: productsWithLegoSet.length,
    productsStored: 0,
    status: "success",
    sessionLabel: "Manual import from sample (all products)",
  }).returning();

  console.log(`✓ Created session ID: ${session.id}`);

  // Save raw HTML
  await rawDataService.saveRawData({
    scrapeSessionId: session.id,
    source: "shopee",
    sourceUrl: `https://shopee.com.my/${SHOP_NAME}`,
    rawHtml: htmlContent,
    contentType: "text/html",
  });

  console.log("✓ Saved raw HTML data");

  // Insert products
  let productsStored = 0;
  const savedProducts = [];

  for (const product of productsWithLegoSet) {
    try {
      console.log(
        `\n💾 [${productsStored + 1}/${productsWithLegoSet.length}] Saving: ${product.lego_set_number} - ${product.product_name}...`,
      );

      // Upsert product into products table
      const [insertedProduct] = await db.insert(products).values({
        source: "shopee",
        productId: product.product_id,
        name: product.product_name,
        currency: "MYR",
        price: product.price,
        priceBeforeDiscount: product.price_before_discount,
        unitsSold: product.units_sold,
        legoSetNumber: product.lego_set_number,
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

      savedProducts.push({
        legoSetNumber: product.lego_set_number,
        name: product.product_name,
        price: product.price,
        unitsSold: product.units_sold,
      });

      console.log(`   ✓ Saved (Product ID: ${insertedProduct.productId})`);

      productsStored++;
    } catch (error) {
      console.error(
        `   ❌ Error saving product: ${(error as Error).message}`,
      );
    }
  }

  // Update session
  await db.update(scrapeSessions).set({
    productsStored,
  }).where(sql`${scrapeSessions.id} = ${session.id}`);

  console.log(
    `\n✅ Done! Saved ${productsStored}/${productsWithLegoSet.length} products`,
  );
  console.log(`   Session ID: ${session.id}`);

  // Summary table
  console.log(`\n📊 Summary of saved products:`);
  for (const p of savedProducts) {
    console.log(
      `   ${p.legoSetNumber}: ${p.name} - ${p.price / 100} MYR (${p.unitsSold} sold)`,
    );
  }

  if (productsWithoutLegoSet.length > 0) {
    console.log(`\n⚠️  ${productsWithoutLegoSet.length} products were skipped (no LEGO set number detected):`);
    for (const p of productsWithoutLegoSet) {
      console.log(`   - ${p.product_name}`);
    }
  }
}

// Run the script
if (import.meta.main) {
  main().catch((error) => {
    console.error("❌ Error:", error);
    Deno.exit(1);
  });
}
