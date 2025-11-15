/**
 * RateLimitErrorTracker - Tracks consecutive 403 errors per domain using Redis
 *
 * Responsibilities:
 * - Track consecutive 403 errors per domain
 * - Calculate progressive backoff delays
 * - Reset counter on successful requests
 * - Share state across workers via Redis
 *
 * Progressive backoff schedule:
 * - 1st 403: 1 hour delay
 * - 2nd consecutive 403: 6 hours delay
 * - 3rd+ consecutive 403: 24 hours delay
 */

import { Redis } from "ioredis";
import {
  RATE_LIMIT_ERROR_CONFIG,
  REDIS_CONFIG,
} from "../config/scraper.config.ts";

/**
 * Redis-based 403 error tracker for distributed systems
 */
export class RateLimitErrorTracker {
  private redis: Redis | null = null;
  private fallbackCounters: Map<string, number> = new Map();
  private readonly keyPrefix = "rate-limit-403:";
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
      console.log(
        `✅ RateLimitErrorTracker: Redis connection established`,
      );
      this.isInitialized = true;
    } catch (error) {
      console.warn(
        `⚠️ RateLimitErrorTracker: Redis unavailable, using fallback`,
        error,
      );
      this.redis = null;
      this.isInitialized = true;
    }
  }

  /**
   * Ensure initialized before operations
   */
  private async ensureInitialized(): Promise<void> {
    if (!this.isInitialized) {
      await this.initialize();
    }
  }

  /**
   * Get Redis key for a domain
   */
  private getKey(domain: string): string {
    return `${this.keyPrefix}${domain}`;
  }

  /**
   * Increment 403 counter for a domain and return the new count
   */
  async increment(domain: string): Promise<number> {
    await this.ensureInitialized();

    const key = this.getKey(domain);

    // Use Redis if available
    if (this.redis) {
      try {
        // Increment the counter
        const count = await this.redis.incr(key);

        // Set TTL on first increment
        if (count === 1) {
          await this.redis.pexpire(
            key,
            RATE_LIMIT_ERROR_CONFIG.COUNTER_TTL_MS,
          );
        }

        return count;
      } catch (error) {
        console.warn(
          `⚠️ RateLimitErrorTracker: Redis operation failed for ${domain}, using fallback`,
          error,
        );
        // Fall through to fallback
      }
    }

    // Fallback to in-memory counter
    const currentCount = this.fallbackCounters.get(domain) || 0;
    const newCount = currentCount + 1;
    this.fallbackCounters.set(domain, newCount);
    return newCount;
  }

  /**
   * Get current 403 count for a domain
   */
  async getCount(domain: string): Promise<number> {
    await this.ensureInitialized();

    const key = this.getKey(domain);

    // Use Redis if available
    if (this.redis) {
      try {
        const count = await this.redis.get(key);
        return count ? parseInt(count, 10) : 0;
      } catch (error) {
        console.warn(
          `⚠️ RateLimitErrorTracker: Redis operation failed for ${domain}, using fallback`,
          error,
        );
        // Fall through to fallback
      }
    }

    // Fallback to in-memory counter
    return this.fallbackCounters.get(domain) || 0;
  }

  /**
   * Reset 403 counter for a domain (called on successful request)
   */
  async reset(domain: string): Promise<void> {
    await this.ensureInitialized();

    const key = this.getKey(domain);

    // Use Redis if available
    if (this.redis) {
      try {
        await this.redis.del(key);
        return;
      } catch (error) {
        console.warn(
          `⚠️ RateLimitErrorTracker: Redis operation failed for ${domain}, using fallback`,
          error,
        );
        // Fall through to fallback
      }
    }

    // Fallback to in-memory counter
    this.fallbackCounters.delete(domain);
  }

  /**
   * Calculate delay based on consecutive 403 count
   * Progressive backoff: 1hr -> 6hrs -> 24hrs
   */
  calculateDelay(consecutive403Count: number): number {
    const delays = RATE_LIMIT_ERROR_CONFIG.PROGRESSIVE_DELAYS_MS;
    const index = Math.min(consecutive403Count - 1, delays.length - 1);
    return delays[Math.max(0, index)];
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
    console.log("🔒 RateLimitErrorTracker: Redis connection closed");
  }
}

/**
 * Singleton instance for global use
 */
export const rateLimitErrorTracker = new RateLimitErrorTracker();
