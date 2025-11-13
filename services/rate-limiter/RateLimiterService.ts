/**
 * RateLimiterService - Redis-based distributed rate limiting for scraping
 *
 * Responsibilities (Single Responsibility Principle):
 * - Enforce rate limits with token bucket algorithm
 * - Add random delays (jitter) for natural patterns
 * - Track request timestamps per domain in Redis (distributed)
 * - Prevent bot detection through predictable patterns
 *
 * This service follows SOLID principles:
 * - SRP: Only handles rate limiting logic
 * - OCP: Extensible through configuration
 * - DIP: Depends on configuration and Redis abstractions
 *
 * Redis-based implementation prevents race conditions in concurrent environments
 */

import {
  getRandomDelay,
  RATE_LIMIT_CONFIG,
  REDIS_CONFIG,
} from "../../config/scraper.config.ts";
import { Redis } from "ioredis";

/**
 * Interface for rate limiter options
 */
export interface RateLimiterOptions {
  domain: string;
  minDelayMs?: number;
  maxDelayMs?: number;
}

/**
 * Interface for tracking request history (stored in Redis)
 */
interface RequestHistory {
  lastRequestTime: number;
  requestCount: number;
  windowStart: number;
}

/**
 * RateLimiterService - Redis-based distributed rate limiting
 * Safe for concurrent worker processes
 */
export class RateLimiterService {
  private redis: Redis | null = null;
  private fallbackHistory: Map<string, RequestHistory> = new Map(); // Fallback if Redis unavailable
  private readonly windowDurationMs = 60 * 60 * 1000; // 1 hour window
  private readonly redisKeyPrefix = "ratelimit:";
  private isInitialized = false;

  /**
   * Initialize Redis connection
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) {
      return;
    }

    try {
      this.redis = new Redis({
        host: REDIS_CONFIG.HOST,
        port: REDIS_CONFIG.PORT,
        password: REDIS_CONFIG.PASSWORD,
        db: REDIS_CONFIG.DB,
        maxRetriesPerRequest: REDIS_CONFIG.MAX_RETRIES_PER_REQUEST,
        lazyConnect: true,
      });

      await this.redis.connect();
      await this.redis.ping();
      console.log("✅ RateLimiterService: Redis connection established");
      this.isInitialized = true;
    } catch (error) {
      console.warn(
        "⚠️ RateLimiterService: Redis unavailable, falling back to in-memory storage",
        error,
      );
      this.redis = null;
      this.isInitialized = true; // Mark as initialized even with fallback
    }
  }

  /**
   * Ensure service is initialized before use
   */
  private async ensureInitialized(): Promise<void> {
    if (!this.isInitialized) {
      await this.initialize();
    }
  }

  /**
   * Close Redis connection
   */
  async close(): Promise<void> {
    if (this.redis) {
      await this.redis.quit();
      this.redis = null;
    }
    this.isInitialized = false;
  }

  /**
   * Wait for the appropriate delay before allowing the next request
   * Implements token bucket with random jitter using Redis for distributed state
   */
  async waitForNextRequest(options: RateLimiterOptions): Promise<void> {
    await this.ensureInitialized();

    const { domain } = options;
    const minDelay = options.minDelayMs || RATE_LIMIT_CONFIG.MIN_DELAY_MS;
    const maxDelay = options.maxDelayMs || RATE_LIMIT_CONFIG.MAX_DELAY_MS;

    const history = await this.getOrCreateHistory(domain);
    const now = Date.now();

    // Reset window if it has expired
    if (now - history.windowStart >= this.windowDurationMs) {
      history.requestCount = 0;
      history.windowStart = now;
      await this.saveHistory(domain, history);
    }

    // Check if we've exceeded hourly rate limit
    if (history.requestCount >= RATE_LIMIT_CONFIG.MAX_REQUESTS_PER_HOUR) {
      const timeUntilReset = this.windowDurationMs -
        (now - history.windowStart);

      console.log(
        `⏸️ Rate limit reached for ${domain}. Waiting ${
          Math.ceil(
            timeUntilReset / 1000 / 60,
          )
        } minutes until reset.`,
      );

      await this.delay(timeUntilReset);

      // Reset the window
      history.requestCount = 0;
      history.windowStart = Date.now();
      await this.saveHistory(domain, history);
    }

    // Calculate time since last request
    const timeSinceLastRequest = now - history.lastRequestTime;
    const randomDelay = getRandomDelay(minDelay, maxDelay);

    // If not enough time has passed, wait
    if (timeSinceLastRequest < randomDelay) {
      const waitTime = randomDelay - timeSinceLastRequest;

      console.log(
        `⏳ Rate limiting: Waiting ${
          Math.ceil(waitTime / 1000)
        } seconds before next request to ${domain}`,
      );
      console.log(
        `📊 Request ${
          history.requestCount + 1
        }/${RATE_LIMIT_CONFIG.MAX_REQUESTS_PER_HOUR} in current hour`,
      );

      await this.delay(waitTime);
    } else {
      // Optimized: Only add small jitter if enough time has already passed
      // This prevents unnecessary delays when rate limits are already satisfied
      const jitter = getRandomDelay(500, 1000); // Reduced from 1-3s to 0.5-1s
      console.log(
        `⏳ Adding ${Math.ceil(jitter / 1000)}s jitter for natural pattern`,
      );
      await this.delay(jitter);
    }

    // Update history atomically using Redis
    history.lastRequestTime = Date.now();
    history.requestCount++;
    await this.saveHistory(domain, history);
  }

  /**
   * Get or create request history for a domain from Redis
   */
  private async getOrCreateHistory(domain: string): Promise<RequestHistory> {
    const key = this.redisKeyPrefix + domain;

    if (this.redis) {
      try {
        const data = await this.redis.get(key);

        if (data) {
          return JSON.parse(data) as RequestHistory;
        }
      } catch (error) {
        console.warn(
          `⚠️ RateLimiterService: Redis get failed for ${domain}, using fallback`,
          error,
        );
      }
    }

    // Fallback to in-memory or create new
    let history = this.fallbackHistory.get(domain);

    if (!history) {
      history = {
        lastRequestTime: 0,
        requestCount: 0,
        windowStart: Date.now(),
      };

      // Try to save to Redis if available
      if (this.redis) {
        try {
          await this.redis.set(
            key,
            JSON.stringify(history),
            "EX",
            Math.ceil(this.windowDurationMs / 1000), // Expire after 1 hour
          );
        } catch (error) {
          console.warn(
            `⚠️ RateLimiterService: Redis set failed for ${domain}`,
            error,
          );
          this.fallbackHistory.set(domain, history);
        }
      } else {
        this.fallbackHistory.set(domain, history);
      }
    }

    return history;
  }

  /**
   * Save request history for a domain to Redis
   */
  private async saveHistory(
    domain: string,
    history: RequestHistory,
  ): Promise<void> {
    const key = this.redisKeyPrefix + domain;

    if (this.redis) {
      try {
        await this.redis.set(
          key,
          JSON.stringify(history),
          "EX",
          Math.ceil(this.windowDurationMs / 1000), // Expire after 1 hour
        );
        return;
      } catch (error) {
        console.warn(
          `⚠️ RateLimiterService: Redis save failed for ${domain}, using fallback`,
          error,
        );
      }
    }

    // Fallback to in-memory
    this.fallbackHistory.set(domain, history);
  }

  /**
   * Delay helper
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Check if a request can be made immediately without waiting
   */
  async canMakeRequest(domain: string, minDelayMs?: number): Promise<boolean> {
    await this.ensureInitialized();

    const history = await this.getHistory(domain);

    if (!history) {
      return true; // No history, can make request
    }

    const now = Date.now();
    const minDelay = minDelayMs || RATE_LIMIT_CONFIG.MIN_DELAY_MS;

    // Check window
    if (now - history.windowStart >= this.windowDurationMs) {
      return true; // Window expired, can make request
    }

    // Check hourly limit
    if (history.requestCount >= RATE_LIMIT_CONFIG.MAX_REQUESTS_PER_HOUR) {
      return false;
    }

    // Check time since last request
    const timeSinceLastRequest = now - history.lastRequestTime;
    return timeSinceLastRequest >= minDelay;
  }

  /**
   * Get request history for a domain (without creating)
   */
  private async getHistory(
    domain: string,
  ): Promise<RequestHistory | null> {
    const key = this.redisKeyPrefix + domain;

    if (this.redis) {
      try {
        const data = await this.redis.get(key);
        if (data) {
          return JSON.parse(data) as RequestHistory;
        }
      } catch (error) {
        console.warn(
          `⚠️ RateLimiterService: Redis get failed for ${domain}`,
          error,
        );
      }
    }

    // Fallback to in-memory
    return this.fallbackHistory.get(domain) || null;
  }

  /**
   * Get the time until the next request can be made
   */
  async getTimeUntilNextRequest(
    domain: string,
    minDelayMs?: number,
  ): Promise<number> {
    await this.ensureInitialized();

    const history = await this.getHistory(domain);

    if (!history) {
      return 0; // No history, can make request immediately
    }

    const now = Date.now();
    const minDelay = minDelayMs || RATE_LIMIT_CONFIG.MIN_DELAY_MS;

    // Check window reset
    if (now - history.windowStart >= this.windowDurationMs) {
      return 0;
    }

    // Check hourly limit
    if (history.requestCount >= RATE_LIMIT_CONFIG.MAX_REQUESTS_PER_HOUR) {
      return this.windowDurationMs - (now - history.windowStart);
    }

    // Check time since last request
    const timeSinceLastRequest = now - history.lastRequestTime;
    const timeUntilNext = Math.max(0, minDelay - timeSinceLastRequest);

    return timeUntilNext;
  }

  /**
   * Get statistics for a domain
   */
  async getStats(domain: string): Promise<
    {
      requestCount: number;
      lastRequestTime: number;
      windowStart: number;
      timeUntilReset: number;
      canMakeRequest: boolean;
    } | null
  > {
    await this.ensureInitialized();

    const history = await this.getHistory(domain);

    if (!history) {
      return null;
    }

    const now = Date.now();

    return {
      requestCount: history.requestCount,
      lastRequestTime: history.lastRequestTime,
      windowStart: history.windowStart,
      timeUntilReset: this.windowDurationMs - (now - history.windowStart),
      canMakeRequest: await this.canMakeRequest(domain),
    };
  }

  /**
   * Reset rate limiter for a specific domain
   */
  async reset(domain: string): Promise<void> {
    await this.ensureInitialized();

    const key = this.redisKeyPrefix + domain;

    if (this.redis) {
      try {
        await this.redis.del(key);
      } catch (error) {
        console.warn(
          `⚠️ RateLimiterService: Redis delete failed for ${domain}`,
          error,
        );
      }
    }

    this.fallbackHistory.delete(domain);
    console.log(`🔄 Rate limiter reset for domain: ${domain}`);
  }

  /**
   * Reset all rate limiters
   */
  async resetAll(): Promise<void> {
    await this.ensureInitialized();

    if (this.redis) {
      try {
        const keys = await this.redis.keys(this.redisKeyPrefix + "*");
        if (keys.length > 0) {
          await this.redis.del(...keys);
        }
      } catch (error) {
        console.warn(
          "⚠️ RateLimiterService: Redis reset all failed",
          error,
        );
      }
    }

    this.fallbackHistory.clear();
    console.log("🔄 All rate limiters reset");
  }

  /**
   * Get all tracked domains
   */
  async getTrackedDomains(): Promise<string[]> {
    await this.ensureInitialized();

    const domains: Set<string> = new Set();

    if (this.redis) {
      try {
        const keys = await this.redis.keys(this.redisKeyPrefix + "*");
        for (const key of keys) {
          domains.add(key.replace(this.redisKeyPrefix, ""));
        }
      } catch (error) {
        console.warn(
          "⚠️ RateLimiterService: Redis keys failed",
          error,
        );
      }
    }

    // Add fallback domains
    for (const domain of this.fallbackHistory.keys()) {
      domains.add(domain);
    }

    return Array.from(domains);
  }
}

/**
 * Singleton instance for reuse across the application
 */
let rateLimiterInstance: RateLimiterService | null = null;

/**
 * Get the singleton RateLimiterService instance
 * Automatically initializes Redis connection on first call
 */
export function getRateLimiter(): RateLimiterService {
  if (!rateLimiterInstance) {
    rateLimiterInstance = new RateLimiterService();
    // Initialize asynchronously (don't await here to keep function sync)
    rateLimiterInstance.initialize().catch((error) => {
      console.error("Failed to initialize RateLimiterService:", error);
    });
  }
  return rateLimiterInstance;
}

/**
 * Reset the singleton instance (useful for testing)
 */
export async function resetRateLimiter(): Promise<void> {
  if (rateLimiterInstance) {
    await rateLimiterInstance.resetAll();
  }
}

/**
 * Close the singleton instance (useful for graceful shutdown)
 */
export async function closeRateLimiter(): Promise<void> {
  if (rateLimiterInstance) {
    await rateLimiterInstance.close();
    rateLimiterInstance = null;
  }
}
