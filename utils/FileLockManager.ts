/**
 * FileLockManager - Redis-based distributed file locking
 *
 * Prevents concurrent downloads/writes of the same file across multiple workers.
 * Uses Redis SET with NX (not exists) and EX (expiry) for atomic lock acquisition.
 *
 * Benefits:
 * - Distributed: Works across multiple worker processes
 * - Atomic: Redis SET NX ensures only one process acquires lock
 * - Auto-expiry: Locks automatically expire to prevent deadlocks
 * - Efficient: Single Redis operation per lock/unlock
 */

import { Redis } from "ioredis";
import { REDIS_CONFIG } from "../config/scraper.config.ts";

export interface FileLockOptions {
  /**
   * Maximum time to wait for lock acquisition (milliseconds)
   * Default: 5000ms (5 seconds)
   */
  timeoutMs?: number;

  /**
   * Lock expiry time (milliseconds)
   * Default: 60000ms (60 seconds)
   */
  expiryMs?: number;

  /**
   * Retry interval when waiting for lock (milliseconds)
   * Default: 100ms
   */
  retryIntervalMs?: number;
}

/**
 * Redis-based file lock manager for distributed file operations
 */
export class FileLockManager {
  private redis: Redis | null = null;
  private readonly keyPrefix = "filelock:";
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
      console.log("✅ FileLockManager: Redis connection established");
      this.isInitialized = true;
    } catch (error) {
      console.warn(
        "⚠️ FileLockManager: Redis unavailable, locks will not be enforced",
        error,
      );
      this.redis = null;
      this.isInitialized = true;
    }
  }

  /**
   * Ensure service is initialized
   */
  private async ensureInitialized(): Promise<void> {
    if (!this.isInitialized) {
      await this.initialize();
    }
  }

  /**
   * Acquire a lock for a file path
   * @param filePath - Unique identifier for the file
   * @param options - Lock acquisition options
   * @returns Lock token if acquired, null if failed
   */
  async acquireLock(
    filePath: string,
    options: FileLockOptions = {},
  ): Promise<string | null> {
    await this.ensureInitialized();

    const {
      timeoutMs = 5000,
      expiryMs = 60000,
      retryIntervalMs = 100,
    } = options;

    // Generate unique lock token
    const lockToken = `${Date.now()}-${
      Math.random().toString(36).substring(7)
    }`;
    const lockKey = `${this.keyPrefix}${this.normalizeFilePath(filePath)}`;

    if (!this.redis) {
      // Redis unavailable - allow operation without lock (best effort)
      console.warn(
        `⚠️ FileLockManager: Redis unavailable, proceeding without lock for ${filePath}`,
      );
      return lockToken;
    }

    const startTime = Date.now();
    const expirySeconds = Math.ceil(expiryMs / 1000);

    while (Date.now() - startTime < timeoutMs) {
      try {
        // Try to acquire lock using Redis SET with NX (not exists) and EX (expiry)
        const result = await this.redis.set(
          lockKey,
          lockToken,
          "EX",
          expirySeconds,
          "NX",
        );

        if (result === "OK") {
          console.log(`🔒 Acquired file lock: ${filePath}`);
          return lockToken;
        }

        // Lock already held by another process, wait and retry
        await this.delay(retryIntervalMs);
      } catch (error) {
        console.error(
          `FileLockManager: Error acquiring lock for ${filePath}`,
          error,
        );
        return null;
      }
    }

    // Timeout waiting for lock
    console.warn(
      `⏱️ FileLockManager: Timeout waiting for lock: ${filePath}`,
    );
    return null;
  }

  /**
   * Release a lock
   * @param filePath - File path that was locked
   * @param lockToken - Token returned from acquireLock
   */
  async releaseLock(filePath: string, lockToken: string): Promise<void> {
    await this.ensureInitialized();

    if (!this.redis) {
      return; // Redis unavailable - nothing to release
    }

    const lockKey = `${this.keyPrefix}${this.normalizeFilePath(filePath)}`;

    try {
      // Lua script to ensure we only delete our own lock (check token matches)
      const script = `
        if redis.call("get", KEYS[1]) == ARGV[1] then
          return redis.call("del", KEYS[1])
        else
          return 0
        end
      `;

      const result = await this.redis.eval(script, 1, lockKey, lockToken);

      if (result === 1) {
        console.log(`🔓 Released file lock: ${filePath}`);
      } else {
        console.warn(
          `⚠️ FileLockManager: Lock already expired or held by another process: ${filePath}`,
        );
      }
    } catch (error) {
      console.error(
        `FileLockManager: Error releasing lock for ${filePath}`,
        error,
      );
    }
  }

  /**
   * Execute a function with file lock protection
   * Automatically acquires lock, executes function, and releases lock
   * @param filePath - File to lock
   * @param fn - Function to execute while holding lock
   * @param options - Lock options
   * @returns Result of fn
   */
  async withLock<T>(
    filePath: string,
    fn: () => Promise<T>,
    options: FileLockOptions = {},
  ): Promise<T> {
    const lockToken = await this.acquireLock(filePath, options);

    if (!lockToken) {
      throw new Error(
        `Failed to acquire lock for file: ${filePath}`,
      );
    }

    try {
      return await fn();
    } finally {
      await this.releaseLock(filePath, lockToken);
    }
  }

  /**
   * Check if a file is currently locked
   * @param filePath - File path to check
   * @returns true if locked, false otherwise
   */
  async isLocked(filePath: string): Promise<boolean> {
    await this.ensureInitialized();

    if (!this.redis) {
      return false;
    }

    const lockKey = `${this.keyPrefix}${this.normalizeFilePath(filePath)}`;

    try {
      const exists = await this.redis.exists(lockKey);
      return exists === 1;
    } catch (error) {
      console.error(
        `FileLockManager: Error checking lock for ${filePath}`,
        error,
      );
      return false;
    }
  }

  /**
   * Normalize file path for consistent key naming
   */
  private normalizeFilePath(filePath: string): string {
    // Remove leading/trailing slashes, normalize separators
    return filePath.replace(/^\/+|\/+$/g, "").replace(/\/+/g, "/");
  }

  /**
   * Delay helper
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
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
 * Singleton instance
 */
let fileLockManagerInstance: FileLockManager | null = null;

/**
 * Get the singleton FileLockManager instance
 */
export function getFileLockManager(): FileLockManager {
  if (!fileLockManagerInstance) {
    fileLockManagerInstance = new FileLockManager();
    // Initialize asynchronously
    fileLockManagerInstance.initialize().catch((error) => {
      console.error("Failed to initialize FileLockManager:", error);
    });
  }
  return fileLockManagerInstance;
}

/**
 * Close the singleton instance
 */
export async function closeFileLockManager(): Promise<void> {
  if (fileLockManagerInstance) {
    await fileLockManagerInstance.close();
    fileLockManagerInstance = null;
  }
}
