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
import { bricklinkItems, products, type BricklinkItem } from "../../db/schema.ts";
import { eq, isNotNull, notInArray, sql } from "drizzle-orm";
import { getQueueService } from "../queue/QueueService.ts";
import type { PricingBox } from "../bricklink/BricklinkParser.ts";

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

      // Enqueue jobs for each missing item
      for (const product of productsWithMissingData) {
        try {
          const legoSetNumber = product.legoSetNumber!;
          // BrickLink requires -1 suffix for LEGO sets
          const bricklinkItemId = `${legoSetNumber}-1`;
          const url =
            `https://www.bricklink.com/v2/catalog/catalogitem.page?S=${bricklinkItemId}`;

          await queueService.addScrapeJob({
            url,
            itemId: bricklinkItemId,
            saveToDb: true,
          });

          result.jobsEnqueued++;
          console.log(
            `✅ Enqueued Bricklink scraping job for LEGO set ${legoSetNumber} (${product.name})`,
          );
        } catch (error) {
          const errorMsg =
            `Failed to enqueue job for LEGO set ${product.legoSetNumber}: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }
      }

      console.log(
        `✅ Missing Bricklink items: ${result.jobsEnqueued}/${result.missingBricklinkData} jobs enqueued`,
      );

      // Find items with missing volume data
      const itemsWithMissingVolume = await this.findItemsMissingVolumeData();
      result.missingVolumeData = itemsWithMissingVolume.length;
      result.itemsWithMissingVolume = itemsWithMissingVolume;

      console.log(
        `📊 Found ${itemsWithMissingVolume.length} active Bricklink items with missing volume data`,
      );

      if (itemsWithMissingVolume.length > 0) {
        // Enqueue jobs for items with missing volume (one-time catch-up)
        for (const item of itemsWithMissingVolume) {
          try {
            const url =
              `https://www.bricklink.com/v2/catalog/catalogitem.page?S=${item.itemId}`;

            await queueService.addScrapeJob({
              url,
              itemId: item.itemId,
              saveToDb: true,
            });

            result.jobsEnqueued++;
            console.log(
              `✅ Enqueued re-scraping job for ${item.itemId} (${item.title}) - missing: ${item.missingBoxes.join(", ")}`,
            );
          } catch (error) {
            const errorMsg =
              `Failed to enqueue job for ${item.itemId}: ${error.message}`;
            console.error(`❌ ${errorMsg}`);
            result.errors.push(errorMsg);
          }
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
      const bricklinkItem = await db.query.bricklinkItems.findFirst({
        where: eq(bricklinkItems.itemId, product.legoSetNumber),
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
      const bricklinkItemId = `${product.legoSetNumber}-1`;
      const url =
        `https://www.bricklink.com/v2/catalog/catalogitem.page?S=${bricklinkItemId}`;

      await queueService.addScrapeJob({
        url,
        itemId: bricklinkItemId,
        saveToDb: true,
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
   */
  private async findProductsMissingBricklinkData(): Promise<
    Array<{
      productId: string;
      legoSetNumber: string | null;
      name: string | null;
    }>
  > {
    // Get all products with LEGO set numbers
    const productsWithLegoSets = await db.select({
      productId: products.productId,
      legoSetNumber: products.legoSetNumber,
      name: products.name,
    })
      .from(products)
      .where(isNotNull(products.legoSetNumber));

    if (productsWithLegoSets.length === 0) {
      return [];
    }

    // Get all existing Bricklink item IDs
    const existingBricklinkItems = await db.select({
      itemId: bricklinkItems.itemId,
    })
      .from(bricklinkItems);

    const existingItemIds = new Set(
      existingBricklinkItems.map((item) => item.itemId),
    );

    // Filter products that don't have corresponding Bricklink items
    const missingProducts = productsWithLegoSets.filter(
      (product) => !existingItemIds.has(product.legoSetNumber!),
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
   */
  private hasBoxMissingVolume(box: unknown): boolean {
    if (!box) return true; // Box is null/undefined

    const pricingBox = box as PricingBox;

    // Check if total_qty is missing, null, or undefined
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
   */
  private async findItemsMissingVolumeData(): Promise<
    Array<{
      itemId: string;
      title: string | null;
      missingBoxes: string[];
    }>
  > {
    // Get all active Bricklink items
    const activeItems = await db.select()
      .from(bricklinkItems)
      .where(eq(bricklinkItems.watchStatus, "active"));

    // Filter items with missing volume data
    const itemsWithMissingVolume = [];

    for (const item of activeItems) {
      const { hasMissing, missingBoxes } = this.hasAnyMissingVolume(item);

      if (hasMissing) {
        itemsWithMissingVolume.push({
          itemId: item.itemId,
          title: item.title,
          missingBoxes,
        });
      }
    }

    return itemsWithMissingVolume;
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
