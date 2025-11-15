/**
 * MissingDataDetectorService - Detects products missing Bricklink data
 *
 * Responsibilities (Single Responsibility Principle):
 * - Find products with LEGO set numbers but no corresponding Bricklink items
 * - Enqueue scraping jobs for missing Bricklink data
 * - Track detection runs and results
 *
 * This service follows SOLID principles:
 * - SRP: Only handles missing data detection
 * - OCP: Can be extended without modifying core logic
 * - DIP: Depends on abstractions (QueueService, database)
 * - ISP: Focused interface for missing data detection
 */

import { db } from "../../db/client.ts";
import {
  type BricklinkItem,
  bricklinkItems,
  products,
  redditSearchResults,
} from "../../db/schema.ts";
import { and, eq, isNotNull, or, sql } from "drizzle-orm";
import { getQueueService, JobPriority } from "../queue/QueueService.ts";
import type { PricingBox } from "../bricklink/BricklinkParser.ts";
import {
  asBaseSetNumber,
  asBricklinkItemId,
  buildBricklinkCatalogUrl,
  toBricklinkItemId,
} from "../../types/lego-set.ts";

/**
 * Result of a missing data detection run
 */
export interface MissingDataResult {
  success: boolean;
  productsChecked: number;
  missingBricklinkData: number;
  missingVolumeData: number;
  jobsEnqueued: number;
  errors: string[];
  timestamp: Date;
  productsWithMissingData: Array<{
    productId: string;
    legoSetNumber: string;
    name: string | null;
  }>;
  itemsWithMissingVolume: Array<{
    itemId: string;
    title: string | null;
    missingBoxes: string[];
  }>;
}

/**
 * MissingDataDetectorService - Finds and queues missing Bricklink data
 */
export class MissingDataDetectorService {
  /**
   * Run the missing data detector - find products without Bricklink data and enqueue jobs
   */
  async run(): Promise<MissingDataResult> {
    const result: MissingDataResult = {
      success: true,
      productsChecked: 0,
      missingBricklinkData: 0,
      missingVolumeData: 0,
      jobsEnqueued: 0,
      errors: [],
      timestamp: new Date(),
      productsWithMissingData: [],
      itemsWithMissingVolume: [],
    };

    try {
      console.log("🔍 Running missing data detection...");

      const queueService = getQueueService();

      // Check if queue is ready
      if (!queueService.isReady()) {
        const error = "Queue service is not available";
        console.error(`❌ ${error}`);
        result.success = false;
        result.errors.push(error);
        return result;
      }

      // Find products with missing Bricklink data
      const productsWithMissingData = await this
        .findProductsMissingBricklinkData();
      result.productsChecked = productsWithMissingData.length;
      result.missingBricklinkData = productsWithMissingData.length;
      result.productsWithMissingData = productsWithMissingData.map((p) => ({
        productId: p.productId,
        legoSetNumber: p.legoSetNumber!,
        name: p.name,
      }));

      console.log(
        `📋 Found ${productsWithMissingData.length} products with LEGO set numbers missing Bricklink data`,
      );

      if (productsWithMissingData.length === 0) {
        console.log(
          "✅ All products with LEGO set numbers have Bricklink data",
        );
        return result;
      }

      // Prepare all jobs for bulk enqueueing (optimized) with HIGH priority
      const bricklinkJobsToEnqueue = productsWithMissingData.map((product) => {
        const legoSetNumber = product.legoSetNumber!;
        // BrickLink requires -1 suffix for LEGO sets
        const baseSetNumber = asBaseSetNumber(legoSetNumber);
        const bricklinkItemId = toBricklinkItemId(baseSetNumber);
        const url = buildBricklinkCatalogUrl(bricklinkItemId);

        return {
          url,
          itemId: bricklinkItemId,
          saveToDb: true,
          priority: JobPriority.HIGH,
        };
      });

      // Enqueue all jobs at once using bulk operation
      try {
        await queueService.addScrapeJobsBulk(bricklinkJobsToEnqueue);
        result.jobsEnqueued += bricklinkJobsToEnqueue.length;

        // Log individual jobs
        productsWithMissingData.forEach((product) => {
          console.log(
            `✅ Enqueued Bricklink scraping job for LEGO set ${product.legoSetNumber} (${product.name})`,
          );
        });
      } catch (error) {
        const errorMsg =
          `Failed to enqueue bulk jobs for missing Bricklink data: ${error.message}`;
        console.error(`❌ ${errorMsg}`);
        result.errors.push(errorMsg);
      }

      console.log(
        `✅ Missing Bricklink items: ${result.jobsEnqueued}/${result.missingBricklinkData} jobs enqueued`,
      );

      // Find items with missing volume data
      const itemsWithMissingVolume = await this.findItemsMissingVolumeData();
      result.missingVolumeData = itemsWithMissingVolume.length;
      result.itemsWithMissingVolume = itemsWithMissingVolume;

      console.log(
        `📊 Found ${itemsWithMissingVolume.length} active Bricklink items with missing volume data (checking all items)`,
      );

      if (itemsWithMissingVolume.length > 0) {
        // Prepare all volume re-scrape jobs for bulk enqueueing (optimized) with MEDIUM priority
        const volumeJobsToEnqueue = itemsWithMissingVolume.map((item) => {
          // item.itemId is already in Bricklink format (e.g., "60365-1")
          const bricklinkItemId = asBricklinkItemId(item.itemId);
          return {
            url: buildBricklinkCatalogUrl(bricklinkItemId),
            itemId: item.itemId,
            saveToDb: true,
            priority: JobPriority.MEDIUM,
          };
        });

        // Enqueue all jobs at once using bulk operation
        try {
          await queueService.addScrapeJobsBulk(volumeJobsToEnqueue);
          result.jobsEnqueued += volumeJobsToEnqueue.length;

          // Log individual jobs
          itemsWithMissingVolume.forEach((item) => {
            console.log(
              `✅ Enqueued re-scraping job for ${item.itemId} (${item.title}) - missing: ${
                item.missingBoxes.join(", ")
              }`,
            );
          });
        } catch (error) {
          const errorMsg =
            `Failed to enqueue bulk jobs for missing volume data: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }

        console.log(
          `✅ Missing volume data: ${itemsWithMissingVolume.length} items enqueued for re-scraping`,
        );
      } else {
        console.log(
          "✅ All active Bricklink items have complete volume data",
        );
      }

      console.log(
        `✅ Missing data detection complete: ${result.jobsEnqueued} total jobs enqueued`,
      );
    } catch (error) {
      console.error("❌ Missing data detection failed:", error);
      result.success = false;
      result.errors.push(error.message);
    }

    return result;
  }

  /**
   * Check a single product for missing Bricklink data and enqueue if needed
   * Used for immediate checks when products are added/updated
   */
  async checkProduct(productId: string): Promise<{
    hasMissingData: boolean;
    jobEnqueued: boolean;
    error?: string;
  }> {
    try {
      // Get the product
      const product = await db.query.products.findFirst({
        where: eq(products.productId, productId),
      });

      if (!product) {
        return {
          hasMissingData: false,
          jobEnqueued: false,
          error: "Product not found",
        };
      }

      // Check if product has LEGO set number
      if (!product.legoSetNumber) {
        return {
          hasMissingData: false,
          jobEnqueued: false,
          error: "Product has no LEGO set number",
        };
      }

      // Check if Bricklink data exists
      // BrickLink requires -1 suffix for LEGO sets
      const bricklinkItem = await db.query.bricklinkItems.findFirst({
        where: eq(bricklinkItems.itemId, `${product.legoSetNumber}-1`),
      });

      if (bricklinkItem) {
        return {
          hasMissingData: false,
          jobEnqueued: false,
        };
      }

      // Missing Bricklink data - enqueue job
      const queueService = getQueueService();

      if (!queueService.isReady()) {
        return {
          hasMissingData: true,
          jobEnqueued: false,
          error: "Queue service is not available",
        };
      }

      // BrickLink requires -1 suffix for LEGO sets
      const baseSetNumber = asBaseSetNumber(product.legoSetNumber);
      const bricklinkItemId = toBricklinkItemId(baseSetNumber);
      const url = buildBricklinkCatalogUrl(bricklinkItemId);

      await queueService.addScrapeJob({
        url,
        itemId: bricklinkItemId,
        saveToDb: true,
        priority: JobPriority.HIGH,
      });

      console.log(
        `✅ Enqueued Bricklink scraping job for LEGO set ${product.legoSetNumber} (triggered by product ${productId})`,
      );

      return {
        hasMissingData: true,
        jobEnqueued: true,
      };
    } catch (error) {
      console.error(
        `❌ Failed to check product ${productId} for missing data:`,
        error,
      );
      return {
        hasMissingData: false,
        jobEnqueued: false,
        error: error.message,
      };
    }
  }

  /**
   * Find products with LEGO set numbers that don't have corresponding Bricklink items
   * Optimized: Uses SQL LEFT JOIN instead of in-memory filtering
   */
  private async findProductsMissingBricklinkData(): Promise<
    Array<{
      productId: string;
      legoSetNumber: string | null;
      name: string | null;
    }>
  > {
    // Use LEFT JOIN to find products without matching Bricklink items in a single query
    const missingProducts = await db
      .select({
        productId: products.productId,
        legoSetNumber: products.legoSetNumber,
        name: products.name,
      })
      .from(products)
      .leftJoin(
        bricklinkItems,
        sql`${products.legoSetNumber} || '-1' = ${bricklinkItems.itemId}`,
      )
      .where(
        sql`${products.legoSetNumber} IS NOT NULL AND ${bricklinkItems.itemId} IS NULL`,
      );

    return missingProducts;
  }

  /**
   * Find products with LEGO set numbers that don't have corresponding Reddit search results
   * Similar to BrickLink missing data detection
   */
  async findProductsMissingRedditData(): Promise<
    Array<{
      productId: string;
      legoSetNumber: string | null;
      name: string | null;
    }>
  > {
    // Use LEFT JOIN to find products without matching Reddit search results in a single query
    const missingProducts = await db
      .select({
        productId: products.productId,
        legoSetNumber: products.legoSetNumber,
        name: products.name,
      })
      .from(products)
      .leftJoin(
        redditSearchResults,
        eq(products.legoSetNumber, redditSearchResults.legoSetNumber),
      )
      .where(
        sql`${products.legoSetNumber} IS NOT NULL AND ${redditSearchResults.id} IS NULL`,
      );

    return missingProducts;
  }

  /**
   * Get preview of products that would be checked (for UI display)
   */
  async preview(): Promise<{
    productsWithLegoSets: number;
    productsWithBricklinkData: number;
    productsMissingBricklinkData: number;
    sampleMissingProducts: Array<{
      productId: string;
      legoSetNumber: string;
      name: string | null;
    }>;
  }> {
    const productsWithMissingData = await this
      .findProductsMissingBricklinkData();

    // Get total count of products with LEGO set numbers
    const allProductsWithLegoSets = await db.select({
      productId: products.productId,
    })
      .from(products)
      .where(isNotNull(products.legoSetNumber));

    const totalWithLegoSets = allProductsWithLegoSets.length;
    const missingCount = productsWithMissingData.length;
    const withDataCount = totalWithLegoSets - missingCount;

    return {
      productsWithLegoSets: totalWithLegoSets,
      productsWithBricklinkData: withDataCount,
      productsMissingBricklinkData: missingCount,
      sampleMissingProducts: productsWithMissingData.slice(0, 10).map((p) => ({
        productId: p.productId,
        legoSetNumber: p.legoSetNumber!,
        name: p.name,
      })),
    };
  }

  /**
   * Helper function to check if a pricing box has missing volume data
   *
   * A null/undefined box means "no sales exist" (legitimate) - NOT missing data
   * A box with null/undefined total_qty means scraping failed - IS missing data
   */
  private hasBoxMissingVolume(box: unknown): boolean {
    // null/undefined box means "unavailable" (no sales exist) - this is NOT missing data
    if (!box) return false;

    const pricingBox = box as PricingBox;

    // If box exists but total_qty is missing, that's a scraping error - IS missing data
    return pricingBox.total_qty === null ||
      pricingBox.total_qty === undefined;
  }

  /**
   * Helper function to check if a Bricklink item has any missing volume data
   */
  private hasAnyMissingVolume(item: BricklinkItem): {
    hasMissing: boolean;
    missingBoxes: string[];
  } {
    const missingBoxes: string[] = [];

    if (this.hasBoxMissingVolume(item.sixMonthNew)) {
      missingBoxes.push("six_month_new");
    }
    if (this.hasBoxMissingVolume(item.sixMonthUsed)) {
      missingBoxes.push("six_month_used");
    }
    if (this.hasBoxMissingVolume(item.currentNew)) {
      missingBoxes.push("current_new");
    }
    if (this.hasBoxMissingVolume(item.currentUsed)) {
      missingBoxes.push("current_used");
    }

    return {
      hasMissing: missingBoxes.length > 0,
      missingBoxes,
    };
  }

  /**
   * Find Bricklink items with missing volume data
   * Only checks items with watch_status = 'active'
   * Respects scrape intervals: Only returns items where next_scrape_at IS NULL or next_scrape_at <= now
   * Optimized: Uses SQL to filter items with missing volume data instead of checking in application code
   */
  private async findItemsMissingVolumeData(): Promise<
    Array<{
      itemId: string;
      title: string | null;
      missingBoxes: string[];
    }>
  > {
    // Use SQL to find items where any pricing box has null total_qty
    // This is much more efficient than fetching all items and checking in JavaScript
    //
    // Important: We only flag as missing if the box EXISTS but total_qty is null.
    // If the box itself is null (no sales exist), that's legitimate, not missing data.
    //
    // Note: This checks ALL active items regardless of scrape schedule to provide
    // immediate visibility into data quality issues.
    const itemsWithMissingVolume = await db
      .select({
        itemId: bricklinkItems.itemId,
        title: bricklinkItems.title,
        sixMonthNew: bricklinkItems.sixMonthNew,
        sixMonthUsed: bricklinkItems.sixMonthUsed,
        currentNew: bricklinkItems.currentNew,
        currentUsed: bricklinkItems.currentUsed,
      })
      .from(bricklinkItems)
      .where(
        and(
          sql`${bricklinkItems.watchStatus} = 'active'`,
          or(
            sql`(${bricklinkItems.sixMonthNew} IS NOT NULL AND ${bricklinkItems.sixMonthNew}->>'total_qty' IS NULL)`,
            sql`(${bricklinkItems.sixMonthUsed} IS NOT NULL AND ${bricklinkItems.sixMonthUsed}->>'total_qty' IS NULL)`,
            sql`(${bricklinkItems.currentNew} IS NOT NULL AND ${bricklinkItems.currentNew}->>'total_qty' IS NULL)`,
            sql`(${bricklinkItems.currentUsed} IS NOT NULL AND ${bricklinkItems.currentUsed}->>'total_qty' IS NULL)`,
          ),
        ),
      );

    // Now determine which specific boxes are missing for each item
    return itemsWithMissingVolume.map((item) => {
      const { missingBoxes } = this.hasAnyMissingVolume(item as BricklinkItem);
      return {
        itemId: item.itemId,
        title: item.title,
        missingBoxes,
      };
    });
  }
}

/**
 * Singleton instance for reuse across the application
 */
let detectorInstance: MissingDataDetectorService | null = null;

/**
 * Get the singleton MissingDataDetectorService instance
 */
export function getMissingDataDetector(): MissingDataDetectorService {
  if (!detectorInstance) {
    detectorInstance = new MissingDataDetectorService();
  }
  return detectorInstance;
}
