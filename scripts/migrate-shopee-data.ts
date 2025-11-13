/**
 * Data Migration Script: Migrate existing Shopee data to shopee_scrapes table
 *
 * This script migrates existing Shopee product data from the products table
 * and price_history table into the new shopee_scrapes table for proper
 * time-series tracking.
 *
 * Usage:
 *   deno run --allow-net --allow-read --allow-env scripts/migrate-shopee-data.ts
 *
 * Options:
 *   --dry-run: Preview what would be migrated without actually migrating
 */

import { db } from "../db/client.ts";
import { priceHistory, products, shopeeScrapes } from "../db/schema.ts";
import { eq } from "drizzle-orm";

interface MigrationStats {
  productsProcessed: number;
  scrapeRecordsCreated: number;
  historyRecordsMigrated: number;
  errors: Array<{ id: string; error: string }>;
}

interface MigrationOptions {
  dryRun: boolean;
}

/**
 * Parse command line arguments
 */
function parseArgs(): MigrationOptions {
  const args = Deno.args;
  const options: MigrationOptions = {
    dryRun: false,
  };

  for (const arg of args) {
    if (arg === "--dry-run") {
      options.dryRun = true;
    }
  }

  return options;
}

/**
 * Migrate existing Shopee product data to shopee_scrapes
 */
async function migrateShopeeData(
  options: MigrationOptions,
): Promise<MigrationStats> {
  const stats: MigrationStats = {
    productsProcessed: 0,
    scrapeRecordsCreated: 0,
    historyRecordsMigrated: 0,
    errors: [],
  };

  console.log("📦 Fetching Shopee products...");

  // Get all Shopee products
  const shopeeProducts = await db
    .select()
    .from(products)
    .where(eq(products.source, "shopee"));

  console.log(`Found ${shopeeProducts.length} Shopee products to migrate`);

  if (options.dryRun) {
    console.log("🔍 DRY RUN - No data will be migrated");
    return stats;
  }

  // Process each product
  for (const product of shopeeProducts) {
    stats.productsProcessed++;

    try {
      console.log(
        `[${stats.productsProcessed}/${shopeeProducts.length}] Processing ${product.productId}...`,
      );

      // Get price history for this product
      const history = await db
        .select()
        .from(priceHistory)
        .where(eq(priceHistory.productId, product.productId))
        .orderBy(priceHistory.recordedAt);

      if (history.length > 0) {
        // Migrate each price history record as a scrape
        for (const historyRecord of history) {
          await db.insert(shopeeScrapes).values({
            productId: product.productId!,
            scrapeSessionId: null, // No session info for historical data
            price: historyRecord.price,
            currency: product.currency,
            unitsSold: historyRecord.unitsSoldSnapshot,
            shopId: product.shopId,
            shopName: product.shopName,
            productUrl: null, // No URL history available
            rawData: null,
            scrapedAt: historyRecord.recordedAt,
          });

          stats.historyRecordsMigrated++;
        }

        console.log(
          `  ✅ Migrated ${history.length} price history records for ${product.productId}`,
        );
      } else {
        // No price history - create a single scrape record from current product data
        await db.insert(shopeeScrapes).values({
          productId: product.productId!,
          scrapeSessionId: null,
          price: product.price,
          currency: product.currency,
          unitsSold: product.unitsSold,
          shopId: product.shopId,
          shopName: product.shopName,
          productUrl: null,
          rawData: product.rawData,
          scrapedAt: product.createdAt,
        });

        stats.scrapeRecordsCreated++;
        console.log(
          `  ✅ Created initial scrape record for ${product.productId}`,
        );
      }
    } catch (error) {
      const errorMessage = error instanceof Error
        ? error.message
        : String(error);
      stats.errors.push({ id: product.productId!, error: errorMessage });
      console.error(`  ❌ ${product.productId}: ${errorMessage}`);
    }
  }

  return stats;
}

/**
 * Print summary statistics
 */
function printStats(stats: MigrationStats): void {
  console.log(`\n${"=".repeat(60)}`);
  console.log("📊 Migration Summary");
  console.log("=".repeat(60));
  console.log(`Products Processed: ${stats.productsProcessed}`);
  console.log(`History Records Migrated: ${stats.historyRecordsMigrated}`);
  console.log(`New Scrape Records: ${stats.scrapeRecordsCreated}`);
  console.log(
    `Total Records Created: ${
      stats.historyRecordsMigrated + stats.scrapeRecordsCreated
    }`,
  );

  if (stats.errors.length > 0) {
    console.log(`\n⚠️  Errors (${stats.errors.length}):`);
    stats.errors.forEach(({ id, error }) => {
      console.log(`  - ${id}: ${error}`);
    });
  }
}

/**
 * Main execution
 */
async function main() {
  const options = parseArgs();

  console.log("🚀 Shopee Data Migration Script");
  console.log("=".repeat(60));
  console.log(`Mode: ${options.dryRun ? "DRY RUN" : "LIVE"}`);
  console.log("=".repeat(60));

  try {
    const stats = await migrateShopeeData(options);
    printStats(stats);

    if (options.dryRun) {
      console.log("\n🔍 This was a DRY RUN - no changes were made");
    }

    console.log("\n✅ Migration complete!");
  } catch (error) {
    console.error("\n❌ Fatal error during migration:", error);
    Deno.exit(1);
  }
}

// Run the script
if (import.meta.main) {
  main();
}
