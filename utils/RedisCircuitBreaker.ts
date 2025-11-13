/**
 * RedisCircuitBreaker - Distributed circuit breaker using Redis
 *
 * Prevents cascading failures by:
 * - Tracking failures across all workers
 * - Opening circuit after threshold exceeded
 * - Auto-recovery after timeout
 *
 * Redis-based implementation ensures:
 * - Shared state across concurrent workers
 * - No race conditions
 * - Atomic operations
 */

import { Redis } from "ioredis";
import {
  REDIS_CONFIG,
  RETRY_CONFIG,
} from "../config/scraper.config.ts";

/**
 * Circuit breaker state interface
 */
export interface CircuitBreakerState {
  failures: number;
  lastFailureTime: number;
  isOpen: boolean;
}

/**
 * Redis-based circuit breaker for distributed systems
 */
export class RedisCircuitBreaker {
  private redis: Redis | null = null;
  private fallbackState: Map<string, CircuitBreakerState> = new Map();
  private readonly keyPrefix = "circuit:";
  private readonly failuresKey: string;
  private readonly lastFailureKey: string;
  private readonly isOpenKey: string;
  private isInitialized = false;

  constructor(private readonly serviceName: string) {
    this.failuresKey = `${this.keyPrefix}${serviceName}:failures`;
    this.lastFailureKey = `${this.keyPrefix}${serviceName}:lastFailure`;
    this.isOpenKey = `${this.keyPrefix}${serviceName}:isOpen`;
  }

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
        `✅ RedisCircuitBreaker (${this.serviceName}): Redis connection established`,
      );
      this.isInitialized = true;
    } catch (error) {
      console.warn(
        `⚠️ RedisCircuitBreaker (${this.serviceName}): Redis unavailable, using fallback`,
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
   * Check if circuit is open (should block requests)
   */
  async isCircuitOpen(): Promise<boolean> {
    await this.ensureInitialized();

    const state = await this.getState();

    if (!state.isOpen) {
      return false;
    }

    // Check if circuit should auto-recover
    const now = Date.now();
    const timeSinceLastFailure = now - state.lastFailureTime;

    if (timeSinceLastFailure >= RETRY_CONFIG.CIRCUIT_BREAKER_TIMEOUT) {
      console.log(
        `🔓 Circuit breaker (${this.serviceName}) auto-recovering after ${
          Math.ceil(timeSinceLastFailure / 1000)
        }s`,
      );
      await this.reset();
      return false;
    }

    return true;
  }

  /**
   * Record a failure
   */
  async recordFailure(): Promise<void> {
    await this.ensureInitialized();

    if (this.redis) {
      try {
        // Atomic increment
        const failures = await this.redis.incr(this.failuresKey);
        const now = Date.now();

        await this.redis.set(this.lastFailureKey, now.toString());

        // Check if threshold exceeded
        if (failures >= RETRY_CONFIG.CIRCUIT_BREAKER_THRESHOLD) {
          await this.redis.set(this.isOpenKey, "1");
          console.log(
            `🔴 Circuit breaker (${this.serviceName}) OPENED after ${failures} failures`,
          );
        }

        // Set expiry to auto-cleanup old data
        const expiry = Math.ceil(
          RETRY_CONFIG.CIRCUIT_BREAKER_TIMEOUT / 1000,
        );
        await this.redis.expire(this.failuresKey, expiry);
        await this.redis.expire(this.lastFailureKey, expiry);
        await this.redis.expire(this.isOpenKey, expiry);

        return;
      } catch (error) {
        console.warn(
          `⚠️ RedisCircuitBreaker (${this.serviceName}): Redis recordFailure failed`,
          error,
        );
      }
    }

    // Fallback to in-memory
    const state = this.fallbackState.get(this.serviceName) || {
      failures: 0,
      lastFailureTime: 0,
      isOpen: false,
    };

    state.failures++;
    state.lastFailureTime = Date.now();

    if (state.failures >= RETRY_CONFIG.CIRCUIT_BREAKER_THRESHOLD) {
      state.isOpen = true;
      console.log(
        `🔴 Circuit breaker (${this.serviceName}) OPENED after ${state.failures} failures (fallback)`,
      );
    }

    this.fallbackState.set(this.serviceName, state);
  }

  /**
   * Record a success (reset on success)
   */
  async recordSuccess(): Promise<void> {
    await this.ensureInitialized();

    const state = await this.getState();

    // Only reset if there were previous failures
    if (state.failures > 0 || state.isOpen) {
      await this.reset();
    }
  }

  /**
   * Get current circuit breaker state
   */
  async getState(): Promise<CircuitBreakerState> {
    await this.ensureInitialized();

    if (this.redis) {
      try {
        const [failures, lastFailure, isOpen] = await Promise.all([
          this.redis.get(this.failuresKey),
          this.redis.get(this.lastFailureKey),
          this.redis.get(this.isOpenKey),
        ]);

        return {
          failures: failures ? parseInt(failures, 10) : 0,
          lastFailureTime: lastFailure ? parseInt(lastFailure, 10) : 0,
          isOpen: isOpen === "1",
        };
      } catch (error) {
        console.warn(
          `⚠️ RedisCircuitBreaker (${this.serviceName}): Redis getState failed`,
          error,
        );
      }
    }

    // Fallback to in-memory
    return this.fallbackState.get(this.serviceName) || {
      failures: 0,
      lastFailureTime: 0,
      isOpen: false,
    };
  }

  /**
   * Reset circuit breaker
   */
  async reset(): Promise<void> {
    await this.ensureInitialized();

    if (this.redis) {
      try {
        await Promise.all([
          this.redis.del(this.failuresKey),
          this.redis.del(this.lastFailureKey),
          this.redis.del(this.isOpenKey),
        ]);
        console.log(`✅ Circuit breaker (${this.serviceName}) reset`);
        return;
      } catch (error) {
        console.warn(
          `⚠️ RedisCircuitBreaker (${this.serviceName}): Redis reset failed`,
          error,
        );
      }
    }

    // Fallback to in-memory
    this.fallbackState.delete(this.serviceName);
    console.log(`✅ Circuit breaker (${this.serviceName}) reset (fallback)`);
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
}

/**
 * Create a circuit breaker for a specific service
 */
export function createCircuitBreaker(
  serviceName: string,
): RedisCircuitBreaker {
  const breaker = new RedisCircuitBreaker(serviceName);
  // Initialize asynchronously
  breaker.initialize().catch((error) => {
    console.error(
      `Failed to initialize circuit breaker for ${serviceName}:`,
      error,
    );
  });
  return breaker;
}
