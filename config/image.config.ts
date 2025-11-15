/**
 * Image Download and Storage Configuration
 *
 * Centralized configuration for image handling across all scrapers.
 */

export const IMAGE_CONFIG = {
  /**
   * Storage configuration
   */
  STORAGE: {
    TYPE: "local" as const, // local | supabase | r2
    LOCAL_BASE_DIR: Deno.env.get("IMAGE_STORAGE_PATH") || "static/images/products",
    PUBLIC_PATH: "/images/products",
  },

  /**
   * Download configuration
   */
  DOWNLOAD: {
    TIMEOUT_MS: 30000, // 30 seconds
    MAX_RETRIES: 3,
    RETRY_DELAY_MS: 1000,
    CONCURRENCY: 5, // Number of simultaneous downloads
  },

  /**
   * Image validation
   */
  VALIDATION: {
    ALLOWED_FORMATS: ["jpg", "jpeg", "png", "webp", "gif"],
    MAX_SIZE_MB: 10,
    MIN_SIZE_BYTES: 100, // Minimum file size to avoid broken images
  },

  /**
   * Feature flags
   */
  FEATURES: {
    ENABLE_DEDUPLICATION: true, // Use hash-based filenames for deduplication
    SKIP_EXISTING: true, // Skip download if local file already exists
    FALLBACK_TO_EXTERNAL: true, // Use external URL if download fails
    DELETE_ON_PRODUCT_DELETE: false, // Keep images even if product is deleted
  },

  /**
   * Backfill configuration
   */
  BACKFILL: {
    BATCH_SIZE: 50, // Number of products to process in each batch
    DELAY_BETWEEN_BATCHES_MS: 2000, // Delay between batches to avoid overwhelming server
    CONCURRENCY: 3, // Number of simultaneous downloads during backfill
  },
} as const;

/**
 * Image status enum for tracking download state
 */
export enum ImageDownloadStatus {
  PENDING = "pending",
  DOWNLOADING = "downloading",
  COMPLETED = "completed",
  FAILED = "failed",
  SKIPPED = "skipped",
}

/**
 * Type-safe access to configuration
 */
export type ImageConfig = typeof IMAGE_CONFIG;
