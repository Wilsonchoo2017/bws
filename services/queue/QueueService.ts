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
import { getRedditRepository } from "../reddit/RedditRepository.ts";
import {
  createRedditSearchService,
  type SearchResult,
} from "../reddit/RedditSearchService.ts";
import { getBrickRankerRepository } from "../brickranker/BrickRankerRepository.ts";
import {
  createBrickRankerScraperService,
  type ScrapeResult as BrickRankerScrapeResult,
} from "../brickranker/BrickRankerScraperService.ts";

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

export interface RedditSearchJobData {
  setNumber: string;
  subreddit?: string;
  saveToDb?: boolean;
}

export interface BrickRankerScrapeJobData {
  saveToDb?: boolean;
}

/**
 * Job type names
 */
export const JOB_TYPES = {
  SCRAPE_SINGLE: "scrape-single-item",
  SCRAPE_BULK: "scrape-bulk-items",
  SCRAPE_SCHEDULED: "scrape-scheduled-items",
  SEARCH_REDDIT: "search-reddit",
  SCRAPE_BRICKRANKER_RETIREMENT: "scrape-brickranker-retirement",
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
          lockDuration: QUEUE_CONFIG.LOCK_DURATION,
          lockRenewTime: QUEUE_CONFIG.LOCK_RENEW_TIME,
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
  private async processJob(
    job: Job,
  ): Promise<
    | ScrapeResult
    | ScrapeResult[]
    | SearchResult
    | BrickRankerScrapeResult
  > {
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

        case JOB_TYPES.SEARCH_REDDIT:
          return await this.processRedditSearchJob(
            job.data as RedditSearchJobData,
          );

        case JOB_TYPES.SCRAPE_BRICKRANKER_RETIREMENT:
          return await this.processBrickRankerScrapeJob(
            job.data as BrickRankerScrapeJobData,
          );

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
   * Optimized: Enqueues individual jobs instead of processing them sequentially in a single job
   * This allows for better parallelization, fault tolerance, and progress tracking
   */
  private async processBulkScrapeJob(
    data: BulkScrapeJobData,
  ): Promise<ScrapeResult[]> {
    // Prepare individual jobs
    const jobsToEnqueue: ScrapeJobData[] = data.urls.map((url) => {
      // Extract itemId from URL
      const itemIdMatch = url.match(/[?&](?:S|M|G|P)=([^&]+)/);
      const itemId = itemIdMatch ? itemIdMatch[1] : url;

      return {
        url,
        itemId,
        saveToDb: data.saveToDb ?? true,
      };
    });

    try {
      // Enqueue all jobs using bulk operation
      await this.addScrapeJobsBulk(jobsToEnqueue);

      // Return success results
      return jobsToEnqueue.map(() => ({
        success: true,
        data: undefined,
        saved: false,
      }));
    } catch (error) {
      console.error(`❌ Failed to enqueue bulk scrape jobs:`, error);
      // Return failure results
      return jobsToEnqueue.map(() => ({
        success: false,
        error: error.message,
      }));
    }
  }

  /**
   * Process scheduled scrape job - finds items needing scraping
   * Optimized: Uses bulk enqueueing instead of sequential awaits
   */
  private async processScheduledScrapeJob(): Promise<ScrapeResult[]> {
    const repository = getBricklinkRepository();

    // Find items that need scraping
    const items = await repository.findItemsNeedingScraping();
    console.log(`📋 Found ${items.length} items needing scraping`);

    if (items.length === 0) {
      return [];
    }

    // Prepare all jobs for bulk enqueueing
    const jobsToEnqueue: ScrapeJobData[] = items.map((item) => ({
      url:
        `https://www.bricklink.com/v2/catalog/catalogitem.page?${item.itemType}=${item.itemId}`,
      itemId: item.itemId,
      saveToDb: true,
    }));

    try {
      // Enqueue all jobs at once using bulk operation
      await this.addScrapeJobsBulk(jobsToEnqueue);

      // Return success results for all items
      return jobsToEnqueue.map(() => ({
        success: true,
        data: undefined,
        saved: false,
      }));
    } catch (error) {
      console.error(`❌ Failed to enqueue bulk jobs:`, error);
      // Return failure results
      return jobsToEnqueue.map(() => ({
        success: false,
        error: error.message,
      }));
    }
  }

  /**
   * Process Reddit search job
   */
  private async processRedditSearchJob(
    data: RedditSearchJobData,
  ): Promise<SearchResult> {
    const rateLimiter = getRateLimiter();
    const repository = getRedditRepository();

    const searchService = createRedditSearchService(rateLimiter, repository);

    return await searchService.search({
      setNumber: data.setNumber,
      subreddit: data.subreddit,
      saveToDb: data.saveToDb ?? true,
    });
  }

  /**
   * Process BrickRanker retirement tracker scrape job
   */
  private async processBrickRankerScrapeJob(
    _data: BrickRankerScrapeJobData,
  ): Promise<BrickRankerScrapeResult> {
    const httpClient = getHttpClient();
    const rateLimiter = getRateLimiter();
    const repository = getBrickRankerRepository();

    const scraper = createBrickRankerScraperService(
      httpClient,
      rateLimiter,
      repository,
    );

    return await scraper.scrapeAndSave({
      skipRateLimit: false,
    });
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
   * Add multiple scrape jobs to the queue in bulk (optimized for performance)
   * Uses BullMQ's addBulk method for efficient batch enqueueing
   */
  async addScrapeJobsBulk(jobs: ScrapeJobData[]): Promise<Job[]> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    if (jobs.length === 0) {
      return [];
    }

    // Use BullMQ's addBulk for efficient batch operations
    const bulkJobs = jobs.map((data) => ({
      name: JOB_TYPES.SCRAPE_SINGLE,
      data,
    }));

    const addedJobs = await this.queue.addBulk(bulkJobs);
    console.log(`➕ Added ${addedJobs.length} scrape jobs in bulk`);

    return addedJobs;
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
   * Add a Reddit search job to the queue
   */
  async addRedditSearchJob(data: RedditSearchJobData): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    const job = await this.queue.add(JOB_TYPES.SEARCH_REDDIT, data);
    console.log(
      `➕ Added Reddit search job: ${job.id} for set ${data.setNumber}`,
    );

    return job;
  }

  /**
   * Add a BrickRanker retirement tracker scrape job to the queue
   */
  async addBrickRankerScrapeJob(
    data: BrickRankerScrapeJobData = { saveToDb: true },
  ): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    const job = await this.queue.add(
      JOB_TYPES.SCRAPE_BRICKRANKER_RETIREMENT,
      data,
    );
    console.log(
      `➕ Added BrickRanker retirement tracker scrape job: ${job.id}`,
    );

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

  /**
   * Get worker status information
   */
  getWorkerStatus(): {
    isAlive: boolean;
    isPaused: boolean;
    isRunning: boolean;
  } {
    if (!this.worker) {
      return {
        isAlive: false,
        isPaused: false,
        isRunning: false,
      };
    }

    return {
      isAlive: true,
      isPaused: this.worker.isPaused(),
      isRunning: this.worker.isRunning(),
    };
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
