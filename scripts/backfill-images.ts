/**
 * Backfill Script: Download Images for Existing Products
 *
 * This script downloads and stores images for products that have image URLs
 * but no local image paths. It processes products in batches with rate limiting
 * to avoid overwhelming servers.
 *
 * Usage:
 *   deno run --allow-net --allow-read --allow-write --allow-env scripts/backfill-images.ts
 *
 * Options:
 *   --dry-run: Preview what would be downloaded without actually downloading
 *   --limit=N: Limit to N products (useful for testing)
 *   --source=X: Only process products from specific source (shopee, bricklink, etc.)
 */

import { db } from "../db/client.ts";
import { bricklinkItems, products } from "../db/schema.ts";
import { and, eq, isNotNull, isNull } from "drizzle-orm";
import { imageDownloadService } from "../services/image/ImageDownloadService.ts";
import { imageStorageService } from "../services/image/ImageStorageService.ts";
import { IMAGE_CONFIG, ImageDownloadStatus } from "../config/image.config.ts";

interface BackfillStats {
  totalProcessed: number;
  successful: number;
  failed: number;
  skipped: number;
  errors: Array<{ id: string; error: string }>;
}

interface BackfillOptions {
  dryRun: boolean;
  limit?: number;
  source?: string;
}

/**
 * Parse command line arguments
 */
function parseArgs(): BackfillOptions {
  const args = Deno.args;
  const options: BackfillOptions = {
    dryRun: false,
  };

  for (const arg of args) {
    if (arg === "--dry-run") {
      options.dryRun = true;
    } else if (arg.startsWith("--limit=")) {
      options.limit = parseInt(arg.split("=")[1]);
    } else if (arg.startsWith("--source=")) {
      options.source = arg.split("=")[1];
    }
  }

  return options;
}

/**
 * Backfill images for Bricklink items
 */
async function backfillBricklinkImages(
  options: BackfillOptions,
): Promise<BackfillStats> {
  const stats: BackfillStats = {
    totalProcessed: 0,
    successful: 0,
    failed: 0,
    skipped: 0,
    errors: [],
  };

  console.log("📦 Fetching Bricklink items without local images...");

  // Query Bricklink items that have image URLs but no local paths
  const items = await db
    .select()
    .from(bricklinkItems)
    .where(
      and(
        isNotNull(bricklinkItems.imageUrl),
        isNull(bricklinkItems.localImagePath),
      ),
    )
    .limit(options.limit || 10000);

  console.log(`Found ${items.length} Bricklink items to process`);

  if (options.dryRun) {
    console.log("🔍 DRY RUN - No images will be downloaded");
    items.forEach((item, index) => {
      console.log(`  ${index + 1}. ${item.itemId}: ${item.imageUrl}`);
    });
    return stats;
  }

  // Process in batches
  const batchSize = IMAGE_CONFIG.BACKFILL.BATCH_SIZE;
  const delayBetweenBatches = IMAGE_CONFIG.BACKFILL.DELAY_BETWEEN_BATCHES_MS;

  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    console.log(
      `\n📥 Processing batch ${Math.floor(i / batchSize) + 1}/${
        Math.ceil(items.length / batchSize)
      } (${batch.length} items)`,
    );

    // Process batch items
    for (const item of batch) {
      stats.totalProcessed++;

      try {
        if (!item.imageUrl) {
          stats.skipped++;
          continue;
        }

        console.log(
          `  [${stats.totalProcessed}/${items.length}] ${item.itemId}: Downloading...`,
        );

        // Download image
        const imageData = await imageDownloadService.download(item.imageUrl, {
          timeoutMs: IMAGE_CONFIG.DOWNLOAD.TIMEOUT_MS,
          maxRetries: 2, // Fewer retries for backfill
          retryDelayMs: IMAGE_CONFIG.DOWNLOAD.RETRY_DELAY_MS,
          allowedFormats: IMAGE_CONFIG.VALIDATION.ALLOWED_FORMATS,
        });

        // Store image
        const storageResult = await imageStorageService.store(
          imageData.data,
          item.imageUrl,
          imageData.extension,
          item.itemId,
        );

        // Update database
        await db
          .update(bricklinkItems)
          .set({
            localImagePath: storageResult.relativePath,
            imageDownloadedAt: new Date(),
            imageDownloadStatus: ImageDownloadStatus.COMPLETED,
          })
          .where(eq(bricklinkItems.itemId, item.itemId));

        stats.successful++;
        console.log(
          `  ✅ ${item.itemId}: Saved to ${storageResult.relativePath}`,
        );
      } catch (error) {
        stats.failed++;
        const errorMessage = error instanceof Error
          ? error.message
          : String(error);
        stats.errors.push({ id: item.itemId, error: errorMessage });
        console.error(`  ❌ ${item.itemId}: ${errorMessage}`);

        // Mark as failed in database
        try {
          await db
            .update(bricklinkItems)
            .set({
              imageDownloadStatus: ImageDownloadStatus.FAILED,
            })
            .where(eq(bricklinkItems.itemId, item.itemId));
        } catch (_dbError) {
          console.error(`  ⚠️ Failed to update database for ${item.itemId}`);
        }
      }
    }

    // Delay between batches (except for the last batch)
    if (i + batchSize < items.length) {
      console.log(`⏳ Waiting ${delayBetweenBatches}ms before next batch...`);
      await new Promise((resolve) => setTimeout(resolve, delayBetweenBatches));
    }
  }

  return stats;
}

/**
 * Backfill images for unified products table
 */
async function backfillProductImages(
  options: BackfillOptions,
): Promise<BackfillStats> {
  const stats: BackfillStats = {
    totalProcessed: 0,
    successful: 0,
    failed: 0,
    skipped: 0,
    errors: [],
  };

  console.log("📦 Fetching products without local images...");

  // Build query conditions
  const conditions = [
    isNotNull(products.image),
    isNull(products.localImagePath),
  ];

  if (options.source) {
    conditions.push(
      eq(
        products.source,
        options.source as "shopee" | "toysrus" | "brickeconomy" | "self",
      ),
    );
  }

  // Query products that have image URLs but no local paths
  const items = await db
    .select()
    .from(products)
    .where(and(...conditions))
    .limit(options.limit || 10000);

  console.log(`Found ${items.length} products to process`);

  if (options.dryRun) {
    console.log("🔍 DRY RUN - No images will be downloaded");
    items.forEach((item, index) => {
      console.log(
        `  ${index + 1}. ${item.productId} (${item.source}): ${item.image}`,
      );
    });
    return stats;
  }

  // Process in batches
  const batchSize = IMAGE_CONFIG.BACKFILL.BATCH_SIZE;
  const delayBetweenBatches = IMAGE_CONFIG.BACKFILL.DELAY_BETWEEN_BATCHES_MS;

  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    console.log(
      `\n📥 Processing batch ${Math.floor(i / batchSize) + 1}/${
        Math.ceil(items.length / batchSize)
      } (${batch.length} items)`,
    );

    // Process batch items
    for (const item of batch) {
      stats.totalProcessed++;

      try {
        if (!item.image) {
          stats.skipped++;
          continue;
        }

        console.log(
          `  [${stats.totalProcessed}/${items.length}] ${item.productId}: Downloading...`,
        );

        // Download image
        const imageData = await imageDownloadService.download(item.image, {
          timeoutMs: IMAGE_CONFIG.DOWNLOAD.TIMEOUT_MS,
          maxRetries: 2,
          retryDelayMs: IMAGE_CONFIG.DOWNLOAD.RETRY_DELAY_MS,
          allowedFormats: IMAGE_CONFIG.VALIDATION.ALLOWED_FORMATS,
        });

        // Store image
        const storageResult = await imageStorageService.store(
          imageData.data,
          item.image,
          imageData.extension,
          item.productId,
        );

        // Handle multiple images if they exist
        const localImagesArray: string[] = [storageResult.relativePath];

        if (item.images && Array.isArray(item.images)) {
          console.log(
            `  📸 Downloading ${item.images.length} additional images...`,
          );

          const imageResults = await imageDownloadService.downloadMultiple(
            item.images as string[],
            {
              timeoutMs: IMAGE_CONFIG.DOWNLOAD.TIMEOUT_MS,
              maxRetries: 1,
              retryDelayMs: IMAGE_CONFIG.DOWNLOAD.RETRY_DELAY_MS,
              allowedFormats: IMAGE_CONFIG.VALIDATION.ALLOWED_FORMATS,
            },
            IMAGE_CONFIG.BACKFILL.CONCURRENCY,
          );

          // Store successfully downloaded images
          for (const result of imageResults) {
            if (result.data) {
              const storage = await imageStorageService.store(
                result.data.data,
                result.url,
                result.data.extension,
                item.productId,
              );
              localImagesArray.push(storage.relativePath);
            }
          }
        }

        // Update database
        await db
          .update(products)
          .set({
            localImagePath: storageResult.relativePath,
            localImages: localImagesArray,
            imageDownloadedAt: new Date(),
            imageDownloadStatus: ImageDownloadStatus.COMPLETED,
          })
          .where(eq(products.productId, item.productId));

        stats.successful++;
        console.log(
          `  ✅ ${item.productId}: Saved ${localImagesArray.length} image(s)`,
        );
      } catch (error) {
        stats.failed++;
        const errorMessage = error instanceof Error
          ? error.message
          : String(error);
        stats.errors.push({ id: item.productId, error: errorMessage });
        console.error(`  ❌ ${item.productId}: ${errorMessage}`);

        // Mark as failed in database
        try {
          await db
            .update(products)
            .set({
              imageDownloadStatus: ImageDownloadStatus.FAILED,
            })
            .where(eq(products.productId, item.productId));
        } catch (_dbError) {
          console.error(`  ⚠️ Failed to update database for ${item.productId}`);
        }
      }
    }

    // Delay between batches
    if (i + batchSize < items.length) {
      console.log(`⏳ Waiting ${delayBetweenBatches}ms before next batch...`);
      await new Promise((resolve) => setTimeout(resolve, delayBetweenBatches));
    }
  }

  return stats;
}

/**
 * Print summary statistics
 */
function printStats(tableName: string, stats: BackfillStats): void {
  console.log(`\n${"=".repeat(60)}`);
  console.log(`📊 ${tableName} Backfill Summary`);
  console.log("=".repeat(60));
  console.log(`Total Processed: ${stats.totalProcessed}`);
  console.log(`✅ Successful: ${stats.successful}`);
  console.log(`❌ Failed: ${stats.failed}`);
  console.log(`⏭️  Skipped: ${stats.skipped}`);

  if (stats.errors.length > 0) {
    console.log(`\n⚠️  Errors (${stats.errors.length}):`);
    stats.errors.slice(0, 10).forEach(({ id, error }) => {
      console.log(`  - ${id}: ${error}`);
    });
    if (stats.errors.length > 10) {
      console.log(`  ... and ${stats.errors.length - 10} more errors`);
    }
  }
}

/**
 * Main execution
 */
async function main() {
  const options = parseArgs();

  console.log("🚀 Image Backfill Script");
  console.log("=".repeat(60));
  console.log(`Mode: ${options.dryRun ? "DRY RUN" : "LIVE"}`);
  if (options.limit) {
    console.log(`Limit: ${options.limit} items`);
  }
  if (options.source) {
    console.log(`Source filter: ${options.source}`);
  }
  console.log("=".repeat(60));

  try {
    // Backfill Bricklink items
    console.log("\n🔧 Processing Bricklink items...");
    const bricklinkStats = await backfillBricklinkImages(options);
    printStats("Bricklink Items", bricklinkStats);

    // Backfill unified products
    console.log("\n🔧 Processing unified products...");
    const productStats = await backfillProductImages(options);
    printStats("Products", productStats);

    // Overall summary
    const totalSuccessful = bricklinkStats.successful + productStats.successful;
    const totalFailed = bricklinkStats.failed + productStats.failed;
    const totalProcessed = bricklinkStats.totalProcessed +
      productStats.totalProcessed;

    console.log(`\n${"=".repeat(60)}`);
    console.log("🎉 Overall Summary");
    console.log("=".repeat(60));
    console.log(`Total items processed: ${totalProcessed}`);
    console.log(`✅ Total successful: ${totalSuccessful}`);
    console.log(`❌ Total failed: ${totalFailed}`);
    console.log(
      `Success rate: ${((totalSuccessful / totalProcessed) * 100).toFixed(2)}%`,
    );

    if (options.dryRun) {
      console.log("\n🔍 This was a DRY RUN - no changes were made");
    }

    console.log("\n✅ Backfill complete!");
  } catch (error) {
    console.error("\n❌ Fatal error during backfill:", error);
    Deno.exit(1);
  }
}

// Run the script
if (import.meta.main) {
  main();
}
