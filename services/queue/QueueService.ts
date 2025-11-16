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
import { getWorldBricksRepository } from "../worldbricks/WorldBricksRepository.ts";
import { WorldBricksScraperService } from "../worldbricks/WorldBricksScraperService.ts";
import { queueLogger } from "../../utils/logger.ts";
import { MaintenanceError } from "../../types/errors/MaintenanceError.ts";
import { SetNotFoundError } from "../../types/errors/SetNotFoundError.ts";
import { RateLimitError } from "../../types/errors/RateLimitError.ts";

/**
 * Job priority levels
 * Lower number = higher priority (BullMQ convention)
 */
export enum JobPriority {
  HIGH = 1, // Missing data - scrape immediately
  MEDIUM = 5, // Incomplete data - re-scrape soon
  NORMAL = 10, // Regular scheduled scrapes
  LOW = 20, // Set not found - far future retry
}

/**
 * Job data types
 */
export interface ScrapeJobData {
  url: string;
  itemId: string;
  saveToDb?: boolean;
  priority?: JobPriority;
}

export interface BulkScrapeJobData {
  urls: string[];
  saveToDb?: boolean;
  priority?: JobPriority;
}

// Scheduled scrapes don't need additional data, so we use an empty object type
export type ScheduledScrapeJobData = Record<string, never>;

export interface RedditSearchJobData {
  setNumber: string;
  subreddit?: string;
  saveToDb?: boolean;
  priority?: JobPriority;
}

export interface BrickRankerScrapeJobData {
  saveToDb?: boolean;
}

export interface WorldBricksJobData {
  setNumber: string;
  saveToDb?: boolean;
  priority?: JobPriority;
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
  SCRAPE_WORLDBRICKS: "scrape-worldbricks",
} as const;

/**
 * QueueService - Manages BullMQ job queue for scraping
 */
export class QueueService {
  private queue: Queue | null = null;
  private worker: Worker | null = null;
  private connection: Redis | null = null;
  private isInitialized = false;
  private bricklinkSemaphoreKey = "bricklink:scrape:lock";
  private worldbricksSemaphoreKey = "worldbricks:scrape:lock";
  private redditSemaphoreKey = "reddit:scrape:lock";

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
      queueLogger.info("Redis connection established");

      // Create queue
      this.queue = new Queue(QUEUE_CONFIG.QUEUE_NAME, {
        connection: this.connection,
        defaultJobOptions: QUEUE_CONFIG.DEFAULT_JOB_OPTIONS,
      });

      // Create worker
      // Note: We'll handle Bricklink sequential processing via concurrency control in the processJob method
      this.worker = new Worker(
        QUEUE_CONFIG.QUEUE_NAME,
        this.processJob.bind(this),
        {
          connection: this.connection,
          concurrency: QUEUE_CONFIG.WORKER_CONCURRENCY,
          lockDuration: QUEUE_CONFIG.LOCK_DURATION,
          lockRenewTime: QUEUE_CONFIG.LOCK_RENEW_TIME,
          stalledInterval: QUEUE_CONFIG.STALLED_INTERVAL,
        },
      );

      // Worker event listeners
      this.worker.on("completed", (job: Job) => {
        queueLogger.info(`Job ${job.id} completed successfully`, {
          jobId: job.id,
          jobType: job.name,
        });
      });

      this.worker.on("failed", (job: Job | undefined, error: Error) => {
        queueLogger.error(`Job ${job?.id} failed: ${error.message}`, {
          jobId: job?.id,
          jobType: job?.name,
          error: error.message,
          stack: error.stack,
        });
      });

      this.worker.on("active", (job: Job) => {
        queueLogger.info(`Job ${job.id} is now active`, {
          jobId: job.id,
          jobType: job.name,
        });
      });

      this.isInitialized = true;
      queueLogger.info("QueueService initialized successfully");
    } catch (error) {
      queueLogger.error("Failed to initialize QueueService", {
        error: error.message,
        stack: error.stack,
      });
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
    queueLogger.info(`Processing job ${job.id} of type: ${job.name}`, {
      jobId: job.id,
      jobType: job.name,
      jobData: job.data,
    });

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

        case JOB_TYPES.SCRAPE_WORLDBRICKS:
          return await this.processWorldBricksJob(
            job.data as WorldBricksJobData,
          );

        default:
          throw new Error(`Unknown job type: ${job.name}`);
      }
    } catch (error) {
      // Handle maintenance errors specially - reschedule instead of failing
      if (MaintenanceError.isMaintenanceError(error)) {
        await this.handleMaintenanceError(error, job);
        // Return success result to mark job as completed
        return {
          success: true,
          data: undefined,
          saved: false,
          rescheduled: true,
          maintenanceDetected: true,
        } as ScrapeResult;
      }

      // Handle rate limit errors (403) - reschedule with progressive delay
      if (RateLimitError.isRateLimitError(error)) {
        await this.handleRateLimitError(error, job);
        // Return success result to mark job as completed
        return {
          success: true,
          data: undefined,
          saved: false,
          rescheduled: true,
          rateLimitDetected: true,
        } as ScrapeResult;
      }

      // Handle set not found errors - mark as completed, schedule far future retry
      if (SetNotFoundError.isSetNotFoundError(error)) {
        await this.handleSetNotFoundError(error, job);
        // Return success result to mark job as completed (not failed)
        return {
          success: false,
          error: error.message,
          setNotFound: true,
        } as ScrapeResult;
      }

      queueLogger.error(`Job processing error for ${job.id}`, {
        jobId: job.id,
        jobType: job.name,
        error: error.message,
        stack: error.stack,
      });
      throw error;
    }
  }

  /**
   * Handle maintenance error by rescheduling the job
   */
  private async handleMaintenanceError(
    error: MaintenanceError,
    job: Job,
  ): Promise<void> {
    const delayMs = error.estimatedDurationMs;
    const estimatedEndTime = error.getEstimatedEndTime();

    queueLogger.warn(
      `Bricklink maintenance detected - rescheduling job ${job.id}`,
      {
        jobId: job.id,
        jobType: job.name,
        originalJobData: job.data,
        maintenanceMessage: error.message,
        delayMs,
        estimatedEndTime: estimatedEndTime.toISOString(),
        rescheduledFor: new Date(Date.now() + delayMs).toISOString(),
      },
    );

    try {
      if (!this.queue) {
        throw new Error("Queue not initialized");
      }

      // Reschedule the same job with a delay
      await this.queue.add(
        job.name,
        job.data,
        {
          delay: delayMs,
          priority: JobPriority.HIGH, // High priority after maintenance
          attempts: 3,
          backoff: {
            type: "exponential",
            delay: 30000,
          },
        },
      );

      queueLogger.info(
        `Successfully rescheduled job ${job.id} after maintenance`,
        {
          jobId: job.id,
          jobType: job.name,
          delayMs,
          delayMinutes: Math.ceil(delayMs / 60000),
        },
      );
    } catch (rescheduleError) {
      queueLogger.error(
        `Failed to reschedule job ${job.id} after maintenance`,
        {
          jobId: job.id,
          jobType: job.name,
          error: rescheduleError.message,
          stack: rescheduleError.stack,
        },
      );
      throw rescheduleError;
    }
  }

  /**
   * Handle rate limit error (403) by rescheduling the job with progressive delay
   * Progressive backoff: 1hr -> 6hrs -> 24hrs based on consecutive 403 count
   */
  private async handleRateLimitError(
    error: RateLimitError,
    job: Job,
  ): Promise<void> {
    const delayMs = error.delayMs;
    const retryTime = error.getRetryTime();

    queueLogger.warn(
      `Rate limit (403) detected for ${error.domain} - rescheduling job ${job.id}`,
      {
        jobId: job.id,
        jobType: job.name,
        originalJobData: job.data,
        domain: error.domain,
        consecutive403Count: error.consecutive403Count,
        rateLimitMessage: error.message,
        delayMs,
        delayDescription: error.getDelayDescription(),
        retryTime: retryTime.toISOString(),
        rescheduledFor: new Date(Date.now() + delayMs).toISOString(),
      },
    );

    try {
      if (!this.queue) {
        throw new Error("Queue not initialized");
      }

      // Reschedule the same job with progressive backoff delay
      await this.queue.add(
        job.name,
        job.data,
        {
          delay: delayMs,
          priority: JobPriority.MEDIUM, // Medium priority after rate limit
          attempts: 3,
          backoff: {
            type: "exponential",
            delay: 30000,
          },
        },
      );

      queueLogger.info(
        `Successfully rescheduled job ${job.id} after rate limit (403)`,
        {
          jobId: job.id,
          jobType: job.name,
          domain: error.domain,
          consecutive403Count: error.consecutive403Count,
          delayMs,
          delayHours: Math.ceil(delayMs / 3600000),
          delayDescription: error.getDelayDescription(),
        },
      );
    } catch (rescheduleError) {
      queueLogger.error(
        `Failed to reschedule job ${job.id} after rate limit`,
        {
          jobId: job.id,
          jobType: job.name,
          domain: error.domain,
          error: rescheduleError.message,
          stack: rescheduleError.stack,
        },
      );
      throw rescheduleError;
    }
  }

  /**
   * Handle set not found error by scheduling a single retry in 90 days
   * Search returned 200 OK but no results = set doesn't exist NOW
   * But databases can add old sets retroactively, so check again in 90 days
   * No immediate retries - those are skipped by throwing SetNotFoundError
   */
  private async handleSetNotFoundError(
    error: SetNotFoundError,
    job: Job,
  ): Promise<void> {
    const delayMs = 90 * 24 * 60 * 60 * 1000; // 90 days

    queueLogger.warn(
      `Set not found - scheduling single retry in 90 days (no immediate retries)`,
      {
        jobId: job.id,
        jobType: job.name,
        setNumber: error.setNumber,
        source: error.source,
        errorMessage: error.message,
        retryDelayDays: 90,
        rescheduledFor: new Date(Date.now() + delayMs).toISOString(),
      },
    );

    try {
      if (!this.queue) {
        throw new Error("Queue not initialized");
      }

      // Schedule single retry in 90 days
      await this.queue.add(
        job.name,
        job.data,
        {
          delay: delayMs,
          priority: JobPriority.LOW,
          attempts: 1, // Only 1 attempt when it runs in 90 days
          removeOnComplete: true,
        },
      );

      queueLogger.info(
        `Scheduled 90-day retry for set ${error.setNumber}`,
        {
          jobId: job.id,
          setNumber: error.setNumber,
          delayDays: 90,
        },
      );
    } catch (rescheduleError) {
      queueLogger.error(
        `Failed to schedule 90-day retry`,
        {
          jobId: job.id,
          setNumber: error.setNumber,
          error: rescheduleError.message,
        },
      );
      // Don't throw - job still marked as handled
    }
  }

  /**
   * Acquire a lock for Bricklink scraping (ensures sequential processing)
   * Uses Redis SET NX (set if not exists) with expiration
   */
  private async acquireBricklinkLock(
    timeoutMs: number = 300000,
  ): Promise<boolean> {
    if (!this.connection) return false;

    const maxWaitTime = timeoutMs;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitTime) {
      // Try to acquire lock with 5 minute expiration (longer than expected scrape time)
      const acquired = await this.connection.set(
        this.bricklinkSemaphoreKey,
        "locked",
        "EX",
        300, // 5 minutes
        "NX", // Only set if not exists
      );

      if (acquired) {
        queueLogger.info("Acquired Bricklink scraping lock");
        return true;
      }

      // Wait 1 second before retrying
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    queueLogger.warn("Failed to acquire Bricklink lock within timeout");
    return false;
  }

  /**
   * Release the Bricklink scraping lock
   */
  private async releaseBricklinkLock(): Promise<void> {
    if (!this.connection) return;
    await this.connection.del(this.bricklinkSemaphoreKey);
    queueLogger.info("Released Bricklink scraping lock");
  }

  /**
   * Acquire a lock for WorldBricks scraping (ensures sequential processing)
   * Uses Redis SET NX (set if not exists) with expiration
   */
  private async acquireWorldBricksLock(
    timeoutMs: number = 300000,
  ): Promise<boolean> {
    if (!this.connection) return false;

    const maxWaitTime = timeoutMs;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitTime) {
      // Try to acquire lock with 10 minute expiration (longer than expected scrape time with rate limits)
      const acquired = await this.connection.set(
        this.worldbricksSemaphoreKey,
        "locked",
        "EX",
        600, // 10 minutes (longer than BrickLink due to 1-3 minute rate limits)
        "NX", // Only set if not exists
      );

      if (acquired) {
        queueLogger.info("Acquired WorldBricks scraping lock");
        return true;
      }

      // Wait 1 second before retrying
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    queueLogger.warn("Failed to acquire WorldBricks lock within timeout");
    return false;
  }

  /**
   * Release the WorldBricks scraping lock
   */
  private async releaseWorldBricksLock(): Promise<void> {
    if (!this.connection) return;
    await this.connection.del(this.worldbricksSemaphoreKey);
    queueLogger.info("Released WorldBricks scraping lock");
  }

  /**
   * Acquire a distributed lock for Reddit scraping to ensure sequential processing
   */
  private async acquireRedditLock(
    timeoutMs: number = 300000,
  ): Promise<boolean> {
    if (!this.connection) return false;

    const maxWaitTime = timeoutMs;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitTime) {
      // Try to acquire lock with 5 minute expiration (sufficient for Reddit's 5-10s rate limits)
      const acquired = await this.connection.set(
        this.redditSemaphoreKey,
        "locked",
        "EX",
        300, // 5 minutes
        "NX", // Only set if not exists
      );

      if (acquired) {
        queueLogger.info("Acquired Reddit scraping lock");
        return true;
      }

      // Wait 1 second before retrying
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    queueLogger.warn("Failed to acquire Reddit lock within timeout");
    return false;
  }

  /**
   * Release the Reddit scraping lock
   */
  private async releaseRedditLock(): Promise<void> {
    if (!this.connection) return;
    await this.connection.del(this.redditSemaphoreKey);
    queueLogger.info("Released Reddit scraping lock");
  }

  /**
   * Process a single scrape job
   * Uses a distributed lock to ensure only one Bricklink job runs at a time
   */
  private async processSingleScrapeJob(
    data: ScrapeJobData,
  ): Promise<ScrapeResult> {
    // Acquire lock for sequential processing
    const lockAcquired = await this.acquireBricklinkLock();
    if (!lockAcquired) {
      throw new Error(
        "Failed to acquire Bricklink scraping lock - another job may be running",
      );
    }

    try {
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
    } finally {
      // Always release the lock, even if scraping fails
      await this.releaseBricklinkLock();
    }
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
      queueLogger.error("Failed to enqueue bulk scrape jobs", {
        error: error.message,
        stack: error.stack,
        urlCount: data.urls.length,
      });
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
   * Uses a distributed lock to ensure only one Reddit job runs at a time
   */
  private async processRedditSearchJob(
    data: RedditSearchJobData,
  ): Promise<SearchResult> {
    // Acquire lock before scraping
    const lockAcquired = await this.acquireRedditLock();
    if (!lockAcquired) {
      throw new Error(
        "Failed to acquire Reddit scraping lock - another job may be running",
      );
    }

    try {
      const httpClient = getHttpClient();
      const rateLimiter = getRateLimiter();
      const repository = getRedditRepository();

      const searchService = createRedditSearchService(
        httpClient,
        rateLimiter,
        repository,
      );

      const result = await searchService.search({
        setNumber: data.setNumber,
        subreddit: data.subreddit,
        saveToDb: data.saveToDb ?? true,
      });

      // Update next_scrape_at after successful scrape
      if (result.success) {
        await repository.updateNextScrapeAt(
          data.setNumber,
          data.subreddit || "lego",
        );
      }

      return result;
    } finally {
      // Always release the lock, even if scraping failed
      await this.releaseRedditLock();
    }
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
   * Process WorldBricks scrape job
   * Uses a distributed lock to ensure only one WorldBricks job runs at a time
   */
  private async processWorldBricksJob(
    data: WorldBricksJobData,
  ): Promise<{ success: boolean; setNumber: string }> {
    // Acquire lock before scraping
    const lockAcquired = await this.acquireWorldBricksLock();
    if (!lockAcquired) {
      throw new Error(
        "Failed to acquire WorldBricks scraping lock - another job may be running",
      );
    }

    try {
      const httpClient = getHttpClient();
      const rateLimiter = getRateLimiter();
      const repository = getWorldBricksRepository();

      const scraper = new WorldBricksScraperService(
        httpClient,
        rateLimiter,
        repository,
      );

      const result = await scraper.scrape({
        setNumber: data.setNumber,
        saveToDb: data.saveToDb ?? true,
        skipRateLimit: false,
      });

      if (!result.success) {
        throw new Error(result.error || "Unknown scraping error");
      }

      // Update next_scrape_at after successful scrape
      await repository.updateNextScrapeAt(data.setNumber);

      return { success: true, setNumber: data.setNumber };
    } catch (error) {
      queueLogger.error(
        `Failed to scrape WorldBricks set ${data.setNumber}`,
        {
          setNumber: data.setNumber,
          error: error.message,
          stack: error.stack,
        },
      );
      throw error;
    } finally {
      // Always release lock, even if scraping failed
      await this.releaseWorldBricksLock();
    }
  }

  /**
   * Add a scrape job to the queue with smart pre-checks
   * Checks if item was recently scraped (BullMQ handles duplicate jobId automatically)
   * Uses a rate limiter to ensure only 1 Bricklink job runs at a time (sequential processing)
   */
  async addScrapeJob(data: ScrapeJobData): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    let priority = data.priority ?? JobPriority.NORMAL;
    const jobId = `${JOB_TYPES.SCRAPE_SINGLE}-${data.itemId}`;

    // Downgrade priority if monthly data exists or is marked unavailable
    if (priority === JobPriority.HIGH) {
      const bricklinkRepo = getBricklinkRepository();
      const item = await bricklinkRepo.findByItemId(data.itemId);

      // Check if monthly data is marked as unavailable (legitimately doesn't exist)
      if (item?.monthlyDataUnavailable) {
        console.log(
          `⏬ Downgrading priority for ${data.itemId}: monthly data marked unavailable`,
        );
        priority = JobPriority.NORMAL;
      } // Check if monthly data already exists
      else if (await bricklinkRepo.hasMonthlyData(data.itemId)) {
        console.log(
          `⏬ Downgrading priority for ${data.itemId}: monthly data exists`,
        );
        priority = JobPriority.NORMAL;
      } else {
        console.log(
          `✓ Keeping HIGH priority for ${data.itemId}: no monthly data yet`,
        );
      }
    }

    // Check if item was recently scraped (unless HIGH priority)
    if (priority !== JobPriority.HIGH) {
      const wasRecent = await this.wasRecentlyScrapped(data.itemId, 12);
      if (wasRecent) {
        console.log(
          `⏭️  Item ${data.itemId} was recently scraped, skipping`,
        );
        // Return a mock job to indicate it was skipped
        // In practice, you might want to throw or return a special status
        throw new Error(
          `Item ${data.itemId} was scraped within the last 12 hours`,
        );
      }
    }

    // Add the job with jobId - BullMQ prevents duplicates automatically
    // If a job with this ID already exists in waiting/active/delayed state, it returns the existing job
    // Sequential processing is enforced by the worker's limiter configuration
    const job = await this.queue.add(JOB_TYPES.SCRAPE_SINGLE, data, {
      priority,
      jobId,
    });

    const priorityLabel = priority === JobPriority.HIGH
      ? "HIGH"
      : priority === JobPriority.MEDIUM
      ? "MEDIUM"
      : "NORMAL";
    console.log(
      `➕ Added scrape job: ${job.id} for ${data.itemId} (priority: ${priorityLabel})`,
    );

    return job;
  }

  /**
   * Add multiple scrape jobs to the queue in bulk with smart filtering
   * Filters out jobs that were recently scraped (BullMQ handles duplicate jobId automatically)
   */
  async addScrapeJobsBulk(jobs: ScrapeJobData[]): Promise<Job[]> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    if (jobs.length === 0) {
      return [];
    }

    console.log(`🔍 Filtering ${jobs.length} jobs before bulk enqueue...`);

    const bricklinkRepo = getBricklinkRepository();

    // Filter out jobs that were recently scraped
    const filteredJobs: ScrapeJobData[] = [];

    for (const job of jobs) {
      let priority = job.priority ?? JobPriority.NORMAL;

      // Downgrade priority if monthly data exists or is marked unavailable
      if (priority === JobPriority.HIGH) {
        const item = await bricklinkRepo.findByItemId(job.itemId);

        // Check if monthly data is marked as unavailable (legitimately doesn't exist)
        if (item?.monthlyDataUnavailable) {
          console.log(
            `⏬ Downgrading priority for ${job.itemId}: monthly data marked unavailable`,
          );
          priority = JobPriority.NORMAL;
        } // Check if monthly data already exists
        else if (await bricklinkRepo.hasMonthlyData(job.itemId)) {
          console.log(
            `⏬ Downgrading priority for ${job.itemId}: monthly data exists`,
          );
          priority = JobPriority.NORMAL;
        } else {
          console.log(
            `✓ Keeping HIGH priority for ${job.itemId}: no monthly data yet`,
          );
        }
      }

      // Check if recently scraped (unless HIGH priority)
      if (priority !== JobPriority.HIGH) {
        const wasRecent = await this.wasRecentlyScrapped(job.itemId, 12);
        if (wasRecent) {
          console.log(`⏭️  Skipping ${job.itemId} - recently scraped`);
          continue;
        }
      }

      filteredJobs.push({ ...job, priority });
    }

    if (filteredJobs.length === 0) {
      console.log(`✓ All jobs filtered out - nothing to enqueue`);
      return [];
    }

    // Use BullMQ's addBulk for efficient batch operations with jobId
    // BullMQ automatically handles duplicate jobIds - if a job with the same ID already exists,
    // it will not add a duplicate
    // Sequential processing is enforced by the worker's limiter configuration
    const bulkJobs = filteredJobs.map((data) => ({
      name: JOB_TYPES.SCRAPE_SINGLE,
      data,
      opts: {
        priority: data.priority ?? JobPriority.NORMAL,
        jobId: `${JOB_TYPES.SCRAPE_SINGLE}-${data.itemId}`,
      },
    }));

    const addedJobs = await this.queue.addBulk(bulkJobs);
    console.log(
      `➕ Added ${addedJobs.length} scrape jobs in bulk (filtered ${
        jobs.length - filteredJobs.length
      })`,
    );

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
   * Add a scheduled scrape job to the queue with deduplication
   */
  async addScheduledScrapeJob(): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    // Use timestamp-based jobId to allow periodic scheduled scrapes but prevent rapid duplicates
    const timestamp = new Date().toISOString().split("T")[0]; // Daily granularity
    const jobId = `${JOB_TYPES.SCRAPE_SCHEDULED}-${timestamp}`;

    const job = await this.queue.add(JOB_TYPES.SCRAPE_SCHEDULED, {}, {
      jobId,
    });
    console.log(`➕ Added scheduled scrape job: ${job.id}`);

    return job;
  }

  /**
   * Add a Reddit search job to the queue
   * BullMQ handles duplicate jobId automatically
   */
  async addRedditSearchJob(data: RedditSearchJobData): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    const priority = data.priority ?? JobPriority.NORMAL;
    const jobId = `${JOB_TYPES.SEARCH_REDDIT}-${data.setNumber}-${
      data.subreddit || "lego"
    }`;

    // Add the job with jobId - BullMQ prevents duplicates automatically
    const job = await this.queue.add(JOB_TYPES.SEARCH_REDDIT, data, {
      priority,
      jobId,
    });
    console.log(
      `➕ Added Reddit search job: ${job.id} for set ${data.setNumber}`,
    );

    return job;
  }

  /**
   * Add a BrickRanker retirement tracker scrape job to the queue with deduplication
   */
  async addBrickRankerScrapeJob(
    data: BrickRankerScrapeJobData = { saveToDb: true },
  ): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    // Use timestamp-based jobId to allow periodic scrapes but prevent rapid duplicates
    const timestamp = new Date().toISOString().split("T")[0]; // Daily granularity
    const jobId = `${JOB_TYPES.SCRAPE_BRICKRANKER_RETIREMENT}-${timestamp}`;

    const job = await this.queue.add(
      JOB_TYPES.SCRAPE_BRICKRANKER_RETIREMENT,
      data,
      {
        jobId,
      },
    );
    console.log(
      `➕ Added BrickRanker retirement tracker scrape job: ${job.id}`,
    );

    return job;
  }

  /**
   * Add a WorldBricks scrape job to the queue with deduplication
   */
  async addWorldBricksJob(data: WorldBricksJobData): Promise<Job> {
    if (!this.queue) {
      throw new Error("Queue not initialized. Call initialize() first.");
    }

    const priority = data.priority ?? JobPriority.NORMAL;
    const jobId = `${JOB_TYPES.SCRAPE_WORLDBRICKS}-${data.setNumber}`;

    // Add the job with jobId - BullMQ prevents duplicates automatically
    const job = await this.queue.add(JOB_TYPES.SCRAPE_WORLDBRICKS, data, {
      priority,
      jobId,
    });
    console.log(
      `➕ Added WorldBricks scrape job: ${job.id} for set ${data.setNumber}`,
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
   * Check if a job is already queued (waiting or active)
   * Returns the existing job if found, undefined otherwise
   */
  async isJobQueued(jobId: string): Promise<Job | undefined> {
    if (!this.queue) {
      return undefined;
    }

    // Try to get the job by ID
    const existingJob = await this.queue.getJob(jobId);

    // Check if job exists and is in waiting or active state
    if (existingJob) {
      const state = await existingJob.getState();
      if (state === "waiting" || state === "active" || state === "delayed") {
        return existingJob;
      }
    }

    return undefined;
  }

  /**
   * Check if an item was recently scraped
   * @param itemId - The Bricklink item ID
   * @param hoursThreshold - Number of hours to consider "recent" (default: 24)
   * @returns true if item was scraped within the threshold
   */
  async wasRecentlyScrapped(
    itemId: string,
    hoursThreshold: number = 24,
  ): Promise<boolean> {
    try {
      const repository = getBricklinkRepository();
      const item = await repository.findByItemId(itemId);

      if (!item || !item.lastScrapedAt) {
        return false;
      }

      const hoursSinceLastScrape = (Date.now() - item.lastScrapedAt.getTime()) /
        (1000 * 60 * 60);

      return hoursSinceLastScrape < hoursThreshold;
    } catch (error) {
      // If there's an error checking, assume not recently scraped to be safe
      console.warn(
        `Warning: Could not check recent scrape for ${itemId}:`,
        error.message,
      );
      return false;
    }
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
   * Wait for all active jobs to complete
   * @param timeoutMs - Maximum time to wait in milliseconds (default: 5 minutes)
   * @returns Promise that resolves when all active jobs complete or timeout is reached
   */
  async waitForActiveJobs(timeoutMs: number = 300000): Promise<void> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    const startTime = Date.now();
    queueLogger.info("⏳ Waiting for active jobs to complete...");

    while (Date.now() - startTime < timeoutMs) {
      const activeJobs = await this.queue.getActive(0, -1);

      if (activeJobs.length === 0) {
        queueLogger.info("✅ All active jobs completed");
        return;
      }

      queueLogger.info(`⏳ ${activeJobs.length} jobs still active, waiting...`);
      // Wait 2 seconds before checking again
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }

    queueLogger.warn(
      `⚠️ Timeout reached, ${await this.queue
        .getActiveCount()} jobs still active`,
    );
  }

  /**
   * Clean all jobs from the queue (waiting, completed, failed)
   * Active jobs are NOT removed - call waitForActiveJobs() first if needed
   */
  async cleanAllJobs(): Promise<{
    waiting: number;
    completed: number;
    failed: number;
  }> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    queueLogger.info("🧹 Cleaning all jobs from queue...");

    // Get counts before cleaning
    const counts = await this.getJobCounts();

    // Clean completed and failed jobs (age 0 = all)
    await this.queue.clean(0, 0, "completed");
    await this.queue.clean(0, 0, "failed");

    // Drain waiting and delayed jobs
    await this.queue.drain();

    queueLogger.info("✅ All jobs cleaned from queue", {
      waiting: counts.waiting,
      completed: counts.completed,
      failed: counts.failed,
    });

    return {
      waiting: counts.waiting,
      completed: counts.completed,
      failed: counts.failed,
    };
  }

  /**
   * Reset the queue - wait for active jobs, clean all jobs
   * @returns Summary of cleaned jobs
   */
  async resetQueue(): Promise<{
    waiting: number;
    completed: number;
    failed: number;
    active: number;
  }> {
    if (!this.queue) {
      throw new Error("Queue not initialized");
    }

    queueLogger.info("🔄 Starting queue reset (nuclear obliterate mode)...");

    // Get initial counts before obliterating
    const initialCounts = await this.getJobCounts();

    if (initialCounts.active > 0) {
      queueLogger.warn(
        `⚠️  Force-removing ${initialCounts.active} active job(s). Running code may continue but won't affect queue state.`,
      );
    }

    // Pause worker to prevent new jobs from being picked up
    if (this.worker) {
      await this.worker.pause();
      queueLogger.info("⏸️  Worker paused");
    }

    // Nuclear option: obliterate entire queue including active jobs
    await this.queue.obliterate({ force: true });
    queueLogger.info("💥 Queue obliterated (all jobs force-removed)");

    // Reset all rate limiters to clear request history
    const rateLimiter = getRateLimiter();
    await rateLimiter.resetAll();
    queueLogger.info("🔓 Rate limiters reset (all domains cleared)");

    // Resume worker
    if (this.worker) {
      await this.worker.resume();
      queueLogger.info("▶️  Worker resumed");
    }

    queueLogger.info("✅ Queue reset complete", {
      active: initialCounts.active,
      waiting: initialCounts.waiting,
      completed: initialCounts.completed,
      failed: initialCounts.failed,
    });

    return {
      active: initialCounts.active,
      waiting: initialCounts.waiting,
      completed: initialCounts.completed,
      failed: initialCounts.failed,
    };
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
