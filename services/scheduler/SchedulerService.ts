/**
 * SchedulerService - Automated scraping scheduler with priority support
 *
 * Responsibilities (Single Responsibility Principle):
 * - Check for items needing scraping
 * - Prioritize missing/incomplete data
 * - Enqueue scraping jobs with appropriate priorities
 * - Manage scheduling intervals
 * - Schedule Reddit searches automatically
 *
 * This service should be called periodically (via cron or timer)
 * to automatically scrape items based on their scrape_interval_days
 */

import { getBricklinkRepository } from "../bricklink/BricklinkRepository.ts";
import { getRedditRepository } from "../reddit/RedditRepository.ts";
import { getWorldBricksRepository } from "../worldbricks/WorldBricksRepository.ts";
import { getQueueService, JobPriority } from "../queue/QueueService.ts";
import { getMissingDataDetector } from "../missing-data/MissingDataDetectorService.ts";
import {
  asBaseSetNumber,
  asBricklinkItemId,
  buildBricklinkCatalogUrl,
  toBricklinkItemId,
} from "../../types/lego-set.ts";

/**
 * Result of a scheduler run
 */
export interface SchedulerResult {
  success: boolean;
  itemsFound: number;
  jobsEnqueued: number;
  errors: string[];
  timestamp: Date;
  breakdown?: {
    highPriority: number;
    mediumPriority: number;
    normalPriority: number;
  };
}

/**
 * SchedulerService - Manages automated scraping based on intervals and priorities
 */
export class SchedulerService {
  /**
   * Run the Bricklink scheduler with priority-based logic
   */
  async runBricklink(): Promise<SchedulerResult> {
    const result: SchedulerResult = {
      success: true,
      itemsFound: 0,
      jobsEnqueued: 0,
      errors: [],
      timestamp: new Date(),
      breakdown: {
        highPriority: 0,
        mediumPriority: 0,
        normalPriority: 0,
      },
    };

    try {
      console.log("🕐 Running Bricklink scheduled scraping check...");

      const repository = getBricklinkRepository();
      const queueService = getQueueService();
      const missingDataDetector = getMissingDataDetector();

      // Check if queue is ready
      if (!queueService.isReady()) {
        const error = "Queue service is not available";
        console.error(`❌ ${error}`);
        result.success = false;
        result.errors.push(error);
        return result;
      }

      // PRIORITY 1 & 2: Check for missing/incomplete data using the detector service
      console.log("🔍 Running missing data detection...");
      const missingDataResult = await missingDataDetector.run();

      // Process products missing Bricklink data entirely (HIGH priority)
      const missingProducts = missingDataResult.productsWithMissingData;
      console.log(
        `📋 Found ${missingProducts.length} products missing Bricklink data`,
      );

      for (const product of missingProducts) {
        try {
          const setNumber = product.legoSetNumber;
          if (!setNumber) {
            console.warn(
              `⚠️ Skipping product ${product.productId} - no set number`,
            );
            continue;
          }

          // BrickLink requires -1 suffix for LEGO sets
          const baseSetNumber = asBaseSetNumber(setNumber);
          const bricklinkItemId = toBricklinkItemId(baseSetNumber);
          const url = buildBricklinkCatalogUrl(bricklinkItemId);

          await queueService.addScrapeJob({
            url,
            itemId: bricklinkItemId,
            saveToDb: true,
            priority: JobPriority.HIGH,
          });

          result.jobsEnqueued++;
          result.breakdown!.highPriority++;
          console.log(`✅ Enqueued HIGH priority job for ${setNumber}`);
        } catch (error) {
          const errorMsg =
            `Failed to enqueue HIGH priority job: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }
      }

      // Process items with missing volume data (MEDIUM priority)
      const incompleteItems = missingDataResult.itemsWithMissingVolume;
      console.log(
        `📋 Found ${incompleteItems.length} items with incomplete volume data`,
      );

      for (const item of incompleteItems) {
        try {
          // Missing data result includes itemId and missingBoxes but not itemType
          // Default to 'S' for LEGO sets
          // item.itemId is already in Bricklink format (e.g., "60365-1")
          const bricklinkItemId = asBricklinkItemId(item.itemId);
          const url = buildBricklinkCatalogUrl(bricklinkItemId);

          await queueService.addScrapeJob({
            url,
            itemId: item.itemId,
            saveToDb: true,
            priority: JobPriority.MEDIUM,
          });

          result.jobsEnqueued++;
          result.breakdown!.mediumPriority++;
          console.log(`✅ Enqueued MEDIUM priority job for ${item.itemId}`);
        } catch (error) {
          const errorMsg =
            `Failed to enqueue MEDIUM priority job for ${item.itemId}: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }
      }

      // PRIORITY 3: Regular scheduled scrapes (NORMAL priority)
      console.log("🔍 Checking for regular scheduled scrapes...");
      const scheduledItems = await repository.findItemsNeedingScraping();
      console.log(
        `📋 Found ${scheduledItems.length} items for regular scraping`,
      );

      for (const item of scheduledItems) {
        try {
          // item.itemId is already in Bricklink format (e.g., "60365-1")
          const bricklinkItemId = asBricklinkItemId(item.itemId);
          const url = buildBricklinkCatalogUrl(
            bricklinkItemId,
            item.itemType,
          );

          await queueService.addScrapeJob({
            url,
            itemId: item.itemId,
            saveToDb: true,
            priority: JobPriority.NORMAL,
          });

          result.jobsEnqueued++;
          result.breakdown!.normalPriority++;
          console.log(`✅ Enqueued NORMAL priority job for ${item.itemId}`);
        } catch (error) {
          const errorMsg =
            `Failed to enqueue NORMAL priority job for ${item.itemId}: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }
      }

      result.itemsFound = missingProducts.length + incompleteItems.length +
        scheduledItems.length;

      // Clean old completed jobs from the queue
      try {
        await queueService.cleanOldJobs();
      } catch (error) {
        console.warn("⚠️ Failed to clean old jobs:", error.message);
      }

      console.log(
        `✅ Bricklink scheduler run complete: ${result.jobsEnqueued}/${result.itemsFound} jobs enqueued`,
      );
      console.log(
        `   - HIGH priority: ${result.breakdown!.highPriority}`,
      );
      console.log(
        `   - MEDIUM priority: ${result.breakdown!.mediumPriority}`,
      );
      console.log(
        `   - NORMAL priority: ${result.breakdown!.normalPriority}`,
      );
    } catch (error) {
      console.error("❌ Bricklink scheduler run failed:", error);
      result.success = false;
      result.errors.push(error.message);
    }

    return result;
  }

  /**
   * Run the Reddit scheduler for automated searches
   */
  async runReddit(): Promise<SchedulerResult> {
    const result: SchedulerResult = {
      success: true,
      itemsFound: 0,
      jobsEnqueued: 0,
      errors: [],
      timestamp: new Date(),
    };

    try {
      console.log("🕐 Running Reddit scheduled search check...");

      const redditRepository = getRedditRepository();
      const queueService = getQueueService();

      // Check if queue is ready
      if (!queueService.isReady()) {
        const error = "Queue service is not available";
        console.error(`❌ ${error}`);
        result.success = false;
        result.errors.push(error);
        return result;
      }

      // Find searches that need to be updated
      const searchesNeeded = await redditRepository
        .findSearchesNeedingScraping();
      result.itemsFound = searchesNeeded.length;

      console.log(
        `📋 Found ${searchesNeeded.length} Reddit searches needing update`,
      );

      if (searchesNeeded.length === 0) {
        console.log("✅ No Reddit searches need updating at this time");
        return result;
      }

      // Enqueue jobs for each search
      for (const search of searchesNeeded) {
        try {
          await queueService.addRedditSearchJob({
            setNumber: search.legoSetNumber,
            subreddit: search.subreddit,
            saveToDb: true,
            priority: JobPriority.NORMAL,
          });

          result.jobsEnqueued++;
          console.log(
            `✅ Enqueued Reddit search job for ${search.legoSetNumber}`,
          );
        } catch (error) {
          const errorMsg =
            `Failed to enqueue Reddit search for ${search.legoSetNumber}: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }
      }

      console.log(
        `✅ Reddit scheduler run complete: ${result.jobsEnqueued}/${result.itemsFound} jobs enqueued`,
      );
    } catch (error) {
      console.error("❌ Reddit scheduler run failed:", error);
      result.success = false;
      result.errors.push(error.message);
    }

    return result;
  }

  /**
   * Run the WorldBricks scheduler for automated LEGO set scraping
   */
  async runWorldBricks(): Promise<SchedulerResult> {
    const result: SchedulerResult = {
      success: true,
      itemsFound: 0,
      jobsEnqueued: 0,
      errors: [],
      timestamp: new Date(),
      breakdown: {
        highPriority: 0,
        mediumPriority: 0,
        normalPriority: 0,
      },
    };

    try {
      console.log("🕐 Running WorldBricks scheduled scraping check...");

      const worldBricksRepository = getWorldBricksRepository();
      const queueService = getQueueService();

      // Check if queue is ready
      if (!queueService.isReady()) {
        const error = "Queue service is not available";
        console.error(`❌ ${error}`);
        result.success = false;
        result.errors.push(error);
        return result;
      }

      // PRIORITY 1: Find products without WorldBricks entries (HIGH priority - initial scraping)
      console.log("🔍 Checking for products without WorldBricks entries...");
      const newProducts = await worldBricksRepository
        .findProductsWithoutWorldBricksEntries();
      console.log(
        `📋 Found ${newProducts.length} products without WorldBricks entries`,
      );

      for (const product of newProducts) {
        try {
          await queueService.addWorldBricksJob({
            setNumber: product.setNumber,
            saveToDb: true,
            priority: JobPriority.HIGH,
          });

          result.jobsEnqueued++;
          result.breakdown!.highPriority++;
          console.log(
            `✅ Enqueued HIGH priority WorldBricks job for new set ${product.setNumber}`,
          );
        } catch (error) {
          const errorMsg =
            `Failed to enqueue HIGH priority WorldBricks job for ${product.setNumber}: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }
      }

      // PRIORITY 2: Find sets that need re-scraping (NORMAL priority - scheduled updates)
      console.log("🔍 Checking for sets needing scheduled scraping...");
      const setsNeeded = await worldBricksRepository.findSetsNeedingScraping();
      console.log(
        `📋 Found ${setsNeeded.length} WorldBricks sets needing scheduled scraping`,
      );

      for (const set of setsNeeded) {
        try {
          await queueService.addWorldBricksJob({
            setNumber: set.setNumber,
            saveToDb: true,
            priority: JobPriority.NORMAL,
          });

          result.jobsEnqueued++;
          result.breakdown!.normalPriority++;
          console.log(
            `✅ Enqueued NORMAL priority WorldBricks job for set ${set.setNumber}`,
          );
        } catch (error) {
          const errorMsg =
            `Failed to enqueue NORMAL priority WorldBricks job for ${set.setNumber}: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }
      }

      result.itemsFound = newProducts.length + setsNeeded.length;

      console.log(
        `✅ WorldBricks scheduler run complete: ${result.jobsEnqueued}/${result.itemsFound} jobs enqueued`,
      );
      console.log(
        `   - HIGH priority (new sets): ${result.breakdown!.highPriority}`,
      );
      console.log(
        `   - NORMAL priority (scheduled): ${result.breakdown!.normalPriority}`,
      );
    } catch (error) {
      console.error("❌ WorldBricks scheduler run failed:", error);
      result.success = false;
      result.errors.push(error.message);
    }

    return result;
  }

  /**
   * Run all schedulers (Bricklink, Reddit, and WorldBricks)
   */
  async runAll(): Promise<{
    bricklink: SchedulerResult;
    reddit: SchedulerResult;
    worldbricks: SchedulerResult;
  }> {
    console.log("🚀 Running all schedulers...");

    const [bricklink, reddit, worldbricks] = await Promise.all([
      this.runBricklink(),
      this.runReddit(),
      this.runWorldBricks(),
    ]);

    console.log("✅ All schedulers complete");
    return { bricklink, reddit, worldbricks };
  }

  /**
   * Legacy method for backwards compatibility
   * Delegates to runBricklink()
   */
  async run(): Promise<SchedulerResult> {
    return await this.runBricklink();
  }

  /**
   * Get items that will be scraped in the next Bricklink run (preview)
   */
  async previewBricklink(): Promise<{
    items: Array<{
      itemId: string;
      itemType: string;
      title: string | null;
      lastScrapedAt: Date | null;
      nextScrapeAt: Date | null;
      scrapeIntervalDays: number;
      priority: string;
    }>;
    count: number;
  }> {
    const repository = getBricklinkRepository();
    const missingDataDetector = getMissingDataDetector();

    const missingDataResult = await missingDataDetector.run();
    const scheduledItems = await repository.findItemsNeedingScraping();

    const items = [
      ...missingDataResult.productsWithMissingData.map((p) => ({
        itemId: p.legoSetNumber || "unknown",
        itemType: "S",
        title: p.name,
        lastScrapedAt: null,
        nextScrapeAt: null,
        scrapeIntervalDays: 30,
        priority: "HIGH",
      })),
      ...missingDataResult.itemsWithMissingVolume.map((item) => ({
        itemId: item.itemId,
        itemType: "S",
        title: item.title,
        lastScrapedAt: null,
        nextScrapeAt: null,
        scrapeIntervalDays: 30,
        priority: "MEDIUM",
      })),
      ...scheduledItems.map((item) => ({
        itemId: item.itemId,
        itemType: item.itemType,
        title: item.title,
        lastScrapedAt: item.lastScrapedAt,
        nextScrapeAt: item.nextScrapeAt,
        scrapeIntervalDays: item.scrapeIntervalDays,
        priority: "NORMAL",
      })),
    ];

    return {
      items,
      count: items.length,
    };
  }

  /**
   * Get searches that will be updated in the next Reddit run (preview)
   */
  async previewReddit(): Promise<{
    searches: Array<{
      legoSetNumber: string;
      subreddit: string;
      lastScrapedAt: Date | null;
      nextScrapeAt: Date | null;
      totalPosts: number;
    }>;
    count: number;
  }> {
    const redditRepository = getRedditRepository();
    const searches = await redditRepository.findSearchesNeedingScraping();

    return {
      searches: searches.map((search) => ({
        legoSetNumber: search.legoSetNumber,
        subreddit: search.subreddit,
        lastScrapedAt: search.lastScrapedAt ?? null,
        nextScrapeAt: search.nextScrapeAt ?? null,
        totalPosts: search.totalPosts,
      })),
      count: searches.length,
    };
  }

  /**
   * Legacy preview method for backwards compatibility
   */
  async preview(): Promise<{
    items: Array<{
      itemId: string;
      itemType: string;
      title: string | null;
      lastScrapedAt: Date | null;
      nextScrapeAt: Date | null;
      scrapeIntervalDays: number;
    }>;
    count: number;
  }> {
    const bricklinkPreview = await this.previewBricklink();
    return {
      items: bricklinkPreview.items.map(({ priority: _, ...item }) => item),
      count: bricklinkPreview.count,
    };
  }
}

/**
 * Singleton instance for reuse across the application
 */
let schedulerInstance: SchedulerService | null = null;

/**
 * Get the singleton SchedulerService instance
 */
export function getScheduler(): SchedulerService {
  if (!schedulerInstance) {
    schedulerInstance = new SchedulerService();
  }
  return schedulerInstance;
}
