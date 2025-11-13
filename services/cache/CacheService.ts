/**
 * CacheService - In-memory caching service for expensive operations
 *
 * Features:
 * - TTL-based expiration
 * - Automatic cleanup of expired entries
 * - Type-safe cache operations
 * - Cache statistics for monitoring
 */

interface CacheEntry<T> {
  data: T;
  expires: number;
  created: number;
}

interface CacheStats {
  hits: number;
  misses: number;
  size: number;
  hitRate: number;
}

export class CacheService {
  private cache = new Map<string, CacheEntry<unknown>>();
  private stats = {
    hits: 0,
    misses: 0,
  };

  /**
   * Get or compute a cached value
   * @param key - Cache key
   * @param computeFn - Function to compute value if not in cache
   * @param ttl - Time to live in milliseconds (default: 5 minutes)
   * @returns Cached or computed value
   */
  async getOrCompute<T>(
    key: string,
    computeFn: () => Promise<T>,
    ttl: number = 300000, // 5 minutes default
  ): Promise<T> {
    const cached = this.get<T>(key);

    if (cached !== null) {
      this.stats.hits++;
      console.debug(`[CacheService] Cache HIT for key: ${key}`);
      return cached;
    }

    this.stats.misses++;
    console.debug(`[CacheService] Cache MISS for key: ${key}, computing...`);

    const data = await computeFn();
    this.set(key, data, ttl);
    return data;
  }

  /**
   * Get a value from cache
   * @param key - Cache key
   * @returns Cached value or null if not found/expired
   */
  get<T>(key: string): T | null {
    const entry = this.cache.get(key);

    if (!entry) {
      return null;
    }

    // Check if expired
    if (entry.expires < Date.now()) {
      this.cache.delete(key);
      console.debug(`[CacheService] Expired and removed key: ${key}`);
      return null;
    }

    return entry.data as T;
  }

  /**
   * Set a value in cache
   * @param key - Cache key
   * @param data - Data to cache
   * @param ttl - Time to live in milliseconds
   */
  set<T>(key: string, data: T, ttl: number): void {
    const now = Date.now();
    const entry: CacheEntry<T> = {
      data,
      expires: now + ttl,
      created: now,
    };

    this.cache.set(key, entry);
    console.debug(
      `[CacheService] Set key: ${key}, TTL: ${ttl}ms, expires: ${
        new Date(entry.expires).toISOString()
      }`,
    );
  }

  /**
   * Invalidate a specific cache key
   * @param key - Cache key to invalidate
   * @returns true if key was found and removed
   */
  invalidate(key: string): boolean {
    const deleted = this.cache.delete(key);
    if (deleted) {
      console.info(`[CacheService] Invalidated key: ${key}`);
    }
    return deleted;
  }

  /**
   * Invalidate all keys matching a pattern
   * @param pattern - RegExp pattern to match keys
   * @returns Number of keys invalidated
   */
  invalidatePattern(pattern: RegExp): number {
    let count = 0;

    for (const key of this.cache.keys()) {
      if (pattern.test(key)) {
        this.cache.delete(key);
        count++;
      }
    }

    if (count > 0) {
      console.info(
        `[CacheService] Invalidated ${count} keys matching pattern: ${pattern}`,
      );
    }

    return count;
  }

  /**
   * Clear all cache entries
   */
  clear(): void {
    const size = this.cache.size;
    this.cache.clear();
    console.info(`[CacheService] Cleared all ${size} cache entries`);
  }

  /**
   * Remove expired entries from cache
   * @returns Number of entries removed
   */
  cleanup(): number {
    const now = Date.now();
    let removed = 0;

    for (const [key, entry] of this.cache.entries()) {
      if (entry.expires < now) {
        this.cache.delete(key);
        removed++;
      }
    }

    if (removed > 0) {
      console.debug(
        `[CacheService] Cleanup removed ${removed} expired entries`,
      );
    }

    return removed;
  }

  /**
   * Get cache statistics
   * @returns Cache statistics including hits, misses, size, hit rate
   */
  getStats(): CacheStats {
    const total = this.stats.hits + this.stats.misses;
    const hitRate = total > 0 ? (this.stats.hits / total) * 100 : 0;

    return {
      hits: this.stats.hits,
      misses: this.stats.misses,
      size: this.cache.size,
      hitRate: Math.round(hitRate * 10) / 10,
    };
  }

  /**
   * Reset cache statistics
   */
  resetStats(): void {
    this.stats.hits = 0;
    this.stats.misses = 0;
    console.info("[CacheService] Statistics reset");
  }

  /**
   * Check if a key exists in cache (and is not expired)
   * @param key - Cache key
   * @returns true if key exists and is valid
   */
  has(key: string): boolean {
    const entry = this.cache.get(key);
    if (!entry) return false;

    if (entry.expires < Date.now()) {
      this.cache.delete(key);
      return false;
    }

    return true;
  }

  /**
   * Get remaining TTL for a key in milliseconds
   * @param key - Cache key
   * @returns Remaining TTL or -1 if not found/expired
   */
  getTTL(key: string): number {
    const entry = this.cache.get(key);
    if (!entry) return -1;

    const remaining = entry.expires - Date.now();
    return remaining > 0 ? remaining : -1;
  }
}

/**
 * Singleton instance for global cache
 */
export const globalCache = new CacheService();

/**
 * Start automatic cleanup interval
 * Runs cleanup every 5 minutes by default
 */
export function startCacheCleanup(intervalMs: number = 300000): number {
  const intervalId = setInterval(() => {
    globalCache.cleanup();
  }, intervalMs);

  console.info(
    `[CacheService] Started automatic cleanup (interval: ${intervalMs}ms)`,
  );

  return intervalId;
}
