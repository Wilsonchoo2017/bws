/**
 * RateLimiterService - Token bucket rate limiting for scraping
 *
 * Responsibilities (Single Responsibility Principle):
 * - Enforce rate limits with token bucket algorithm
 * - Add random delays (jitter) for natural patterns
 * - Track request timestamps per domain
 * - Prevent bot detection through predictable patterns
 *
 * This service follows SOLID principles:
 * - SRP: Only handles rate limiting logic
 * - OCP: Extensible through configuration
 * - DIP: Depends on configuration abstractions
 */

import {
  getRandomDelay,
  RATE_LIMIT_CONFIG,
} from "../../config/scraper.config.ts";

/**
 * Interface for rate limiter options
 */
export interface RateLimiterOptions {
  domain: string;
  minDelayMs?: number;
  maxDelayMs?: number;
}

/**
 * Interface for tracking request history
 */
interface RequestHistory {
  lastRequestTime: number;
  requestCount: number;
  windowStart: number;
}

/**
 * RateLimiterService - Token bucket implementation for rate limiting
 */
export class RateLimiterService {
  private requestHistory: Map<string, RequestHistory> = new Map();
  private readonly windowDurationMs = 60 * 60 * 1000; // 1 hour window

  /**
   * Wait for the appropriate delay before allowing the next request
   * Implements token bucket with random jitter
   */
  async waitForNextRequest(options: RateLimiterOptions): Promise<void> {
    const { domain } = options;
    const minDelay = options.minDelayMs || RATE_LIMIT_CONFIG.MIN_DELAY_MS;
    const maxDelay = options.maxDelayMs || RATE_LIMIT_CONFIG.MAX_DELAY_MS;

    const history = this.getOrCreateHistory(domain);
    const now = Date.now();

    // Reset window if it has expired
    if (now - history.windowStart >= this.windowDurationMs) {
      history.requestCount = 0;
      history.windowStart = now;
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

    // Update history
    history.lastRequestTime = Date.now();
    history.requestCount++;
  }

  /**
   * Get or create request history for a domain
   */
  private getOrCreateHistory(domain: string): RequestHistory {
    let history = this.requestHistory.get(domain);

    if (!history) {
      history = {
        lastRequestTime: 0,
        requestCount: 0,
        windowStart: Date.now(),
      };
      this.requestHistory.set(domain, history);
    }

    return history;
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
  canMakeRequest(domain: string, minDelayMs?: number): boolean {
    const history = this.requestHistory.get(domain);

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
   * Get the time until the next request can be made
   */
  getTimeUntilNextRequest(
    domain: string,
    minDelayMs?: number,
  ): number {
    const history = this.requestHistory.get(domain);

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
  getStats(domain: string): {
    requestCount: number;
    lastRequestTime: number;
    windowStart: number;
    timeUntilReset: number;
    canMakeRequest: boolean;
  } | null {
    const history = this.requestHistory.get(domain);

    if (!history) {
      return null;
    }

    const now = Date.now();

    return {
      requestCount: history.requestCount,
      lastRequestTime: history.lastRequestTime,
      windowStart: history.windowStart,
      timeUntilReset: this.windowDurationMs - (now - history.windowStart),
      canMakeRequest: this.canMakeRequest(domain),
    };
  }

  /**
   * Reset rate limiter for a specific domain
   */
  reset(domain: string): void {
    this.requestHistory.delete(domain);
    console.log(`🔄 Rate limiter reset for domain: ${domain}`);
  }

  /**
   * Reset all rate limiters
   */
  resetAll(): void {
    this.requestHistory.clear();
    console.log("🔄 All rate limiters reset");
  }

  /**
   * Get all tracked domains
   */
  getTrackedDomains(): string[] {
    return Array.from(this.requestHistory.keys());
  }
}

/**
 * Singleton instance for reuse across the application
 */
let rateLimiterInstance: RateLimiterService | null = null;

/**
 * Get the singleton RateLimiterService instance
 */
export function getRateLimiter(): RateLimiterService {
  if (!rateLimiterInstance) {
    rateLimiterInstance = new RateLimiterService();
  }
  return rateLimiterInstance;
}

/**
 * Reset the singleton instance (useful for testing)
 */
export function resetRateLimiter(): void {
  if (rateLimiterInstance) {
    rateLimiterInstance.resetAll();
  }
}
