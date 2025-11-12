/**
 * SchedulerService - Automated scraping scheduler
 *
 * Responsibilities (Single Responsibility Principle):
 * - Check for items needing scraping
 * - Enqueue scraping jobs for items
 * - Manage scheduling intervals
 *
 * This service should be called periodically (via cron or timer)
 * to automatically scrape items based on their scrape_interval_days
 */

import { getBricklinkRepository } from "../bricklink/BricklinkRepository.ts";
import { getQueueService } from "../queue/QueueService.ts";

/**
 * Result of a scheduler run
 */
export interface SchedulerResult {
  success: boolean;
  itemsFound: number;
  jobsEnqueued: number;
  errors: string[];
  timestamp: Date;
}

/**
 * SchedulerService - Manages automated scraping based on intervals
 */
export class SchedulerService {
  /**
   * Run the scheduler - check for items needing scraping and enqueue jobs
   */
  async run(): Promise<SchedulerResult> {
    const result: SchedulerResult = {
      success: true,
      itemsFound: 0,
      jobsEnqueued: 0,
      errors: [],
      timestamp: new Date(),
    };

    try {
      console.log("🕐 Running scheduled scraping check...");

      const repository = getBricklinkRepository();
      const queueService = getQueueService();

      // Check if queue is ready
      if (!queueService.isReady()) {
        const error = "Queue service is not available";
        console.error(`❌ ${error}`);
        result.success = false;
        result.errors.push(error);
        return result;
      }

      // Find items that need scraping
      const items = await repository.findItemsNeedingScraping();
      result.itemsFound = items.length;

      console.log(`📋 Found ${items.length} items needing scraping`);

      if (items.length === 0) {
        console.log("✅ No items need scraping at this time");
        return result;
      }

      // Enqueue jobs for each item
      for (const item of items) {
        try {
          const url =
            `https://www.bricklink.com/v2/catalog/catalogitem.page?${item.itemType}=${item.itemId}`;

          await queueService.addScrapeJob({
            url,
            itemId: item.itemId,
            saveToDb: true,
          });

          result.jobsEnqueued++;
          console.log(`✅ Enqueued job for ${item.itemId}`);
        } catch (error) {
          const errorMsg =
            `Failed to enqueue job for ${item.itemId}: ${error.message}`;
          console.error(`❌ ${errorMsg}`);
          result.errors.push(errorMsg);
        }
      }

      // Clean old completed jobs from the queue
      try {
        await queueService.cleanOldJobs();
      } catch (error) {
        console.warn("⚠️ Failed to clean old jobs:", error.message);
      }

      console.log(
        `✅ Scheduler run complete: ${result.jobsEnqueued}/${result.itemsFound} jobs enqueued`,
      );
    } catch (error) {
      console.error("❌ Scheduler run failed:", error);
      result.success = false;
      result.errors.push(error.message);
    }

    return result;
  }

  /**
   * Get items that will be scraped in the next run (preview)
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
    const repository = getBricklinkRepository();
    const items = await repository.findItemsNeedingScraping();

    return {
      items: items.map((item) => ({
        itemId: item.itemId,
        itemType: item.itemType,
        title: item.title,
        lastScrapedAt: item.lastScrapedAt,
        nextScrapeAt: item.nextScrapeAt,
        scrapeIntervalDays: item.scrapeIntervalDays,
      })),
      count: items.length,
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
