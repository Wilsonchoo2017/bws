/**
 * QueueService - Bull/BullMQ job queue for asynchronous scraping
 *
 * Responsibilities (Single Responsibility Principle):
 * - Manage job queue with BullMQ
 * - Add scraping jobs
 * - Process jobs with workers
 * - Monitor job status
 * - Handle job failures and retries
 *
 * This service follows SOLID principles:
 * - SRP: Only handles queue management
 * - OCP: Can be extended with new job types
 * - DIP: Depends on Redis abstraction
 */

import { type Job, Queue, Worker } from "bullmq";
import { Redis } from "ioredis";
import { QUEUE_CONFIG, REDIS_CONFIG } from "../../config/scraper.config.ts";
import { getHttpClient } from "../http/HttpClientService.ts";
import { getRateLimiter } from "../rate-limiter/RateLimiterService.ts";
import { getBricklinkRepository } from "../bricklink/BricklinkRepository.ts";
import {
  createBricklinkScraperService,
  type ScrapeOptions,
  type ScrapeResult,
} from "../bricklink/BricklinkScraperService.ts";

/**
 * Job data types
 */
export interface ScrapeJobData {
  url: string;
  itemId: string;
  saveToDb?: boolean;
}

export interface BulkScrapeJobData {
  urls: string[];
  saveToDb?: boolean;
}

// Scheduled scrapes don't need additional data, so we use an empty object type
export type ScheduledScrapeJobData = Record<string, never>;

/**
 * Job type names
 */
export const JOB_TYPES = {
  SCRAPE_SINGLE: "scrape-single-item",
  SCRAPE_BULK: "scrape-bulk-items",
  SCRAPE_SCHEDULED: "scrape-scheduled-items",
} as const;

/**
 * QueueService - Manages BullMQ job queue for scraping
 */
export class QueueService {
  private queue: Queue | null = null;
  private worker: Worker | null = null;
  private connection: Redis | null = null;
  private isInitialized = false;

  /**
   * Initialize the queue service
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) {
      return;
    }

    try {
      // Create Redis connection
      this.connection = new Redis({
        host: REDIS_CONFIG.HOST,
        port: REDIS_CONFIG.PORT,
        password: REDIS_CONFIG.PASSWORD,
        db: REDIS_CONFIG.DB,
        maxRetriesPerRequest: REDIS_CONFIG.MAX_RETRIES_PER_REQUEST,
      });

      // Test connection
      await this.connection.ping();
      console.log("✅ Redis connection established");

      // Create queue
      this.queue = new Queue(QUEUE_CONFIG.QUEUE_NAME, {
        connection: this.connection,
        defaultJobOptions: QUEUE_CONFIG.DEFAULT_JOB_OPTIONS,
      });

      // Create worker
      this.worker = new Worker(
        QUEUE_CONFIG.QUEUE_NAME,
        this.processJob.bind(this),
        {
          connection: this.connection,
          concurrency: QUEUE_CONFIG.WORKER_CONCURRENCY,
        },
      );

      // Worker event listeners
      this.worker.on("completed", (job: Job) => {
        console.log(`✅ Job ${job.id} completed successfully`);
      });

      this.worker.on("failed", (job: Job | undefined, error: Error) => {
        console.error(`❌ Job ${job?.id} failed:`, error.message);
      });

      this.worker.on("active", (job: Job) => {
        console.log(`🔄 Job ${job.id} is now active`);
      });

      this.isInitialized = true;
      console.log("✅ QueueService initialized successfully");
    } catch (error) {
      console.error("❌ Failed to initialize QueueService:", error);
      throw new Error(`Queue initialization failed: ${error.message}`);
    }
  }

  /**
   * Process a job based on its type
   */
  private async processJob(job: Job): Promise<ScrapeResult | ScrapeResult[]> {
    console.log(`🔄 Processing job ${job.id} of type: ${job.name}`);

    try {
      switch (job.name) {
        case JOB_TYPES.SCRAPE_SINGLE:
          return await this.processSingleScrapeJob(job.data as ScrapeJobData);

        case JOB_TYPES.SCRAPE_BULK:
          return await this.processBulkScrapeJob(
            job.data as BulkScrapeJobData,
          );

        case JOB_TYPES.SCRAPE_SCHEDULED:
          return await this.processScheduledScrapeJob();

        default:
          throw new Error(`Unknown job type: ${job.name}`);
      }
    } catch (error) {
      console.error(`❌ Job processing error:`, error);
      throw error;
    }
  }

  /**
   * Process a single scrape job
   */
  private async processSingleScrapeJob(
    data: ScrapeJobData,
  ): Promise<ScrapeResult> {
    const httpClient = getHttpClient();
    const rateLimiter = getRateLimiter();
    const repository = getBricklinkRepository();

    const scraper = createBricklinkScraperService(
      httpClient,
      rateLimiter,
      repository,
    );

    const options: ScrapeOptions = {
      url: data.url,
      saveToDb: data.saveToDb ?? true,
      skipRateLimit: false,
    };

    return await scraper.scrape(options);
  }

  /**
   * Process bulk scrape job
   */
  private async processBulkScrapeJob(
    data: BulkScrapeJobData,
  ): Promise<ScrapeResult[]> {
    const results: ScrapeResult[] = [];

    for (const url of data.urls) {
      // Extract itemId from URL for single scrape job
      const itemIdMatch = url.match(/[?&](?:S|M|G|P)=([^&]+)/);
      const itemId = itemIdMatch ? itemIdMatch[1] : url;

      const result = await this.processSingleScrapeJob({
        url,
        itemId,
        saveToDb: data.saveToDb ?? true,
      });
      results.push(result);
    }

    return results;
  }

  /**
   * Process scheduled scrape job - finds items needing scraping
   */
  private async processScheduledScrapeJob(): Promise<ScrapeResult[]> {
    const repository = getBricklinkRepository();

    // Find items that need scraping
    const items = await repository.findItemsNeedingScraping();
    console.log(`📋 Found ${items.length} items needing scraping`);

    if (items.length === 0) {
      return [];
    }

    const results: ScrapeResult[] = [];

    // Enqueue individual scrape jobs for each item
    for (const item of items) {
      const url =
        `https://www.bricklink.com/v2/catalog/catalogitem.page?${item.itemType}=${item.itemId}`;

      try {
        await this.addScrapeJob({
          url,
          itemId: item.itemId,
          saveToDb: true,
        });

        results.push({
          success: true,
          data: undefined,
          saved: false,
        });
      } catch (error) {
        console.error(`❌ Failed to enqueue job for ${item.itemId}:`, error);
        results.push({
          success: false,
          error: error.message,
        });
      }
    }

    return results;
  }

  /**
   * Add a scrape job to the queue
   */
  async addScrapeJob(data: ScrapeJobData): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    const job = await this.queue.add(JOB_TYPES.SCRAPE_SINGLE, data);
    console.log(`➕ Added scrape job: ${job.id} for ${data.itemId}`);

    return job;
  }

  /**
   * Add a bulk scrape job to the queue
   */
  async addBulkScrapeJob(data: BulkScrapeJobData): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    const job = await this.queue.add(JOB_TYPES.SCRAPE_BULK, data);
    console.log(
      `➕ Added bulk scrape job: ${job.id} for ${data.urls.length} items`,
    );

    return job;
  }

  /**
   * Add a scheduled scrape job to the queue
   */
  async addScheduledScrapeJob(): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    const job = await this.queue.add(JOB_TYPES.SCRAPE_SCHEDULED, {});
    console.log(`➕ Added scheduled scrape job: ${job.id}`);

    return job;
  }

  /**
   * Get job by ID
   */
  async getJob(jobId: string): Promise<Job | undefined> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    return await this.queue.getJob(jobId);
  }

  /**
   * Get job counts
   */
  async getJobCounts(): Promise<{
    waiting: number;
    active: number;
    completed: number;
    failed: number;
    delayed: number;
  }> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    const counts = await this.queue.getJobCounts();
    return {
      waiting: counts.waiting || 0,
      active: counts.active || 0,
      completed: counts.completed || 0,
      failed: counts.failed || 0,
      delayed: counts.delayed || 0,
    };
  }

  /**
   * Get waiting jobs
   */
  async getWaitingJobs(start = 0, end = 10): Promise<Job[]> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    return await this.queue.getWaiting(start, end);
  }

  /**
   * Get active jobs
   */
  async getActiveJobs(start = 0, end = 10): Promise<Job[]> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    return await this.queue.getActive(start, end);
  }

  /**
   * Get completed jobs
   */
  async getCompletedJobs(start = 0, end = 10): Promise<Job[]> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    return await this.queue.getCompleted(start, end);
  }

  /**
   * Get failed jobs
   */
  async getFailedJobs(start = 0, end = 10): Promise<Job[]> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    return await this.queue.getFailed(start, end);
  }

  /**
   * Clean old jobs
   */
  async cleanOldJobs(): Promise<void> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    // Clean completed jobs older than 1 day
    await this.queue.clean(86400000, 1000, "completed");

    // Clean failed jobs older than 7 days
    await this.queue.clean(604800000, 1000, "failed");

    console.log("🧹 Cleaned old jobs from queue");
  }

  /**
   * Close the queue service
   */
  async close(): Promise<void> {
    if (this.worker) {
      await this.worker.close();
      this.worker = null;
    }

    if (this.queue) {
      await this.queue.close();
      this.queue = null;
    }

    if (this.connection) {
      await this.connection.quit();
      this.connection = null;
    }

    this.isInitialized = false;
    console.log("🔒 QueueService closed");
  }

  /**
   * Check if service is ready
   */
  isReady(): boolean {
    return this.isInitialized;
  }
}

/**
 * Singleton instance for reuse across the application
 */
let queueServiceInstance: QueueService | null = null;

/**
 * Get the singleton QueueService instance
 */
export function getQueueService(): QueueService {
  if (!queueServiceInstance) {
    queueServiceInstance = new QueueService();
  }
  return queueServiceInstance;
}

/**
 * Close the singleton instance (useful for cleanup)
 */
export async function closeQueueService(): Promise<void> {
  if (queueServiceInstance) {
    await queueServiceInstance.close();
    queueServiceInstance = null;
  }
}
