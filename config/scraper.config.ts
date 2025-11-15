/**
 * Comprehensive scraper configuration for anti-bot protection and rate limiting
 * Following SOLID principles with clear separation of concerns
 */

/**
 * Redis configuration for Bull/BullMQ job queue
 */
export const REDIS_CONFIG = {
  HOST: Deno.env.get("REDIS_HOST") || "localhost",
  PORT: parseInt(Deno.env.get("REDIS_PORT") || "6379"),
  PASSWORD: Deno.env.get("REDIS_PASSWORD") || undefined,
  DB: parseInt(Deno.env.get("REDIS_DB") || "0"),
  MAX_RETRIES_PER_REQUEST: null, // Must be null for BullMQ blocking operations
} as const;

/**
 * Rate limiting configuration - Balanced approach (10-30 seconds per item)
 */
export const RATE_LIMIT_CONFIG = {
  /** Minimum delay between requests in milliseconds (10 seconds) */
  MIN_DELAY_MS: 10 * 1000,
  /** Maximum delay between requests in milliseconds (30 seconds) */
  MAX_DELAY_MS: 30 * 1000,
  /** Maximum concurrent scraping jobs */
  MAX_CONCURRENT_JOBS: 1,
  /** Maximum requests per hour (conservative) */
  MAX_REQUESTS_PER_HOUR: 15,
} as const;

/**
 * User agent pool for rotation - Mix of browsers and devices
 */
export const USER_AGENTS = [
  // Chrome on Windows
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",

  // Chrome on macOS
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",

  // Firefox on Windows
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",

  // Firefox on macOS
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:119.0) Gecko/20100101 Firefox/119.0",

  // Safari on macOS
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",

  // Edge on Windows
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",

  // Chrome on Linux
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",

  // Firefox on Linux
  "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
  "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",

  // Chrome on Android
  "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
  "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",

  // Safari on iOS
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",

  // Chrome on iPad
  "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",

  // Samsung Internet
  "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36",

  // Opera
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
] as const;

/**
 * Accept-Language headers pool for rotation
 */
export const ACCEPT_LANGUAGES = [
  "en-US,en;q=0.9",
  "en-GB,en;q=0.9",
  "en-US,en;q=0.9,es;q=0.8",
  "en-US,en;q=0.9,fr;q=0.8",
  "en-GB,en;q=0.9,en-US;q=0.8",
  "en,en-US;q=0.9",
] as const;

/**
 * Browser viewport configurations for rotation
 */
export const VIEWPORTS = [
  { width: 1920, height: 1080 }, // Full HD
  { width: 1366, height: 768 }, // Common laptop
  { width: 1536, height: 864 }, // Common laptop
  { width: 2560, height: 1440 }, // 2K
  { width: 1440, height: 900 }, // MacBook
  { width: 1280, height: 720 }, // HD
] as const;

/**
 * Puppeteer/Browser automation configuration
 */
export const BROWSER_CONFIG = {
  /** Use headless mode (new headless) */
  HEADLESS: true,
  /** Browser arguments for better anti-detection */
  ARGS: [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    // Anti-detection flags
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
  ],
  /** Default navigation timeout in milliseconds */
  NAVIGATION_TIMEOUT: 60000,
  /** Default page load timeout in milliseconds */
  PAGE_TIMEOUT: 60000,
  /** Enable JavaScript */
  JAVASCRIPT_ENABLED: true,
  /** Enable images loading (disabled in dev mode for faster scraping, enabled in production) */
  IMAGES_ENABLED: Deno.env.get("DENO_ENV") !== "development",
} as const;

/**
 * Retry and circuit breaker configuration
 */
export const RETRY_CONFIG = {
  /** Maximum number of retry attempts for failed scrapes */
  MAX_RETRIES: 3,
  /** Initial backoff delay in milliseconds */
  INITIAL_BACKOFF_MS: 30000, // 30 seconds
  /** Maximum backoff delay in milliseconds */
  MAX_BACKOFF_MS: 300000, // 5 minutes
  /** Backoff multiplier for exponential backoff */
  BACKOFF_MULTIPLIER: 2,
  /** Circuit breaker - failures before opening circuit */
  CIRCUIT_BREAKER_THRESHOLD: 5,
  /** Circuit breaker - time to wait before retry in milliseconds */
  CIRCUIT_BREAKER_TIMEOUT: 600000, // 10 minutes
} as const;

/**
 * Maintenance detection and handling configuration
 */
export const MAINTENANCE_CONFIG = {
  /** Safety multiplier for parsed maintenance duration (e.g., 1.5x the stated duration) */
  SAFETY_MULTIPLIER: 1.5,
  /** Safety buffer to add to parsed duration in milliseconds (1 minute) */
  SAFETY_BUFFER_MS: 60000, // 1 minute
  /** Default delay when maintenance duration cannot be parsed (5 minutes) */
  DEFAULT_DELAY_MS: 300000, // 5 minutes
} as const;

/**
 * Rate limit error (403) handling configuration
 * Progressive backoff: 1 hour -> 6 hours -> 24 hours
 */
export const RATE_LIMIT_ERROR_CONFIG = {
  /** Progressive delay durations for consecutive 403 errors (in milliseconds) */
  PROGRESSIVE_DELAYS_MS: [
    3600000, // 1 hour (1st 403)
    21600000, // 6 hours (2nd consecutive 403)
    86400000, // 24 hours (3rd+ consecutive 403)
  ],
  /** Maximum consecutive 403s to track (after this, use the last delay) */
  MAX_CONSECUTIVE_COUNT: 3,
  /** TTL for 403 counter in Redis (reset after 48 hours of no 403s) */
  COUNTER_TTL_MS: 172800000, // 48 hours
} as const;

/**
 * Proxy configuration (for future use)
 */
export const PROXY_CONFIG = {
  /** Enable proxy rotation */
  ENABLED: Deno.env.get("PROXY_ENABLED") === "true",
  /** Proxy list (comma-separated in env) */
  PROXY_LIST: Deno.env.get("PROXY_LIST")?.split(",") || [],
  /** Proxy rotation strategy */
  ROTATION_STRATEGY: "round-robin" as "round-robin" | "random",
} as const;

/**
 * Job queue configuration
 */
export const QUEUE_CONFIG = {
  /** Queue name for Bricklink scraping jobs */
  QUEUE_NAME: "bricklink-scraper",
  /** Default job options */
  DEFAULT_JOB_OPTIONS: {
    attempts: 3,
    backoff: {
      type: "exponential" as const,
      delay: 30000, // 30 seconds
    },
    removeOnComplete: {
      age: 86400, // Keep completed jobs for 24 hours
      count: 1000, // Keep last 1000 jobs
    },
    removeOnFail: {
      age: 604800, // Keep failed jobs for 7 days
    },
  },
  /** Worker concurrency - Allow multiple jobs for different domains to run in parallel */
  WORKER_CONCURRENCY: 3, // Process up to 3 jobs concurrently (rate limiter enforces per-domain limits)
  /** Lock duration for jobs (must be longer than expected job duration) */
  LOCK_DURATION: 300000, // 5 minutes (BrickLink scraping takes ~20-60s with rate limiting: 10-30s × 2 requests + processing)
  /** Lock renewal interval (renew lock every 30s to prevent stalling) */
  LOCK_RENEW_TIME: 30000, // 30 seconds
  /** Stalled job check interval (how often worker checks for stalled jobs) - BullMQ default is 30000ms */
  STALLED_INTERVAL: 30000, // 30 seconds (default)
} as const;

/**
 * Reddit API configuration
 */
export const REDDIT_CONFIG = {
  /** Rate limiting for Reddit API (unauthenticated) */
  /** Reddit allows ~60 requests per minute for unauthenticated requests */
  /** We'll be conservative: 1 request per 5 seconds = 12 per minute */
  MIN_DELAY_MS: 5000, // 5 seconds
  MAX_DELAY_MS: 10000, // 10 seconds
  /** Maximum posts to fetch per search */
  MAX_POSTS_PER_SEARCH: 100,
  /** Default subreddit for LEGO searches */
  DEFAULT_SUBREDDIT: "lego",
  /** Alternative subreddits to search */
  ALTERNATIVE_SUBREDDITS: [
    "legostarwars",
    "legotechnic",
    "afol",
    "legomarket",
    "legodeals",
  ],
} as const;

/**
 * Reddit scraping intervals configuration
 */
export const REDDIT_INTERVALS = {
  /** Default scrape interval in days (monthly) */
  DEFAULT_INTERVAL_DAYS: 30,
  /** Minimum allowed interval in days */
  MIN_INTERVAL_DAYS: 1,
  /** Maximum allowed interval in days */
  MAX_INTERVAL_DAYS: 365,
} as const;

/**
 * Scraping intervals configuration (Bricklink)
 */
export const SCRAPE_INTERVALS = {
  /** Default scrape interval in days */
  DEFAULT_INTERVAL_DAYS: 30,
  /** Minimum allowed interval in days */
  MIN_INTERVAL_DAYS: 1,
  /** Maximum allowed interval in days */
  MAX_INTERVAL_DAYS: 365,
} as const;

/**
 * BrickRanker retirement tracker configuration
 */
export const BRICKRANKER_CONFIG = {
  /** Base URL for retirement tracker page */
  BASE_URL: "https://brickranker.com/retirement-tracker",
  /** Rate limiting - Less aggressive than Bricklink (monthly scraping) */
  RATE_LIMIT_MIN_DELAY_MS: 60000, // 1 minute
  RATE_LIMIT_MAX_DELAY_MS: 180000, // 3 minutes
  /** Scraping schedule - Monthly updates */
  SCHEDULE_INTERVAL_DAYS: 30,
  /** Maximum requests per hour (less aggressive) */
  MAX_REQUESTS_PER_HOUR: 30,
} as const;

/**
 * WorldBricks LEGO set database configuration
 */
export const WORLDBRICKS_CONFIG = {
  /** Base URL for WorldBricks */
  BASE_URL: "https://www.worldbricks.com",
  /** Rate limiting - Conservative approach (quarterly scraping) */
  RATE_LIMIT_MIN_DELAY_MS: 60000, // 1 minute
  RATE_LIMIT_MAX_DELAY_MS: 180000, // 3 minutes
  /** Scraping schedule - Quarterly updates (LEGO set data doesn't change often) */
  SCHEDULE_INTERVAL_DAYS: 90,
  /** Maximum requests per hour */
  MAX_REQUESTS_PER_HOUR: 30,
  /** Default language code */
  LANGUAGE: "en",
} as const;

/**
 * Helper function to get a random user agent
 */
export function getRandomUserAgent(): string {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

/**
 * Helper function to get a random Accept-Language header
 */
export function getRandomAcceptLanguage(): string {
  return ACCEPT_LANGUAGES[
    Math.floor(Math.random() * ACCEPT_LANGUAGES.length)
  ];
}

/**
 * Helper function to get a random viewport
 */
export function getRandomViewport(): { width: number; height: number } {
  return VIEWPORTS[Math.floor(Math.random() * VIEWPORTS.length)];
}

/**
 * Helper function to get a random delay between min and max
 */
export function getRandomDelay(
  min: number = RATE_LIMIT_CONFIG.MIN_DELAY_MS,
  max: number = RATE_LIMIT_CONFIG.MAX_DELAY_MS,
): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * Helper function to calculate exponential backoff delay
 */
export function calculateBackoff(attempt: number): number {
  const delay = RETRY_CONFIG.INITIAL_BACKOFF_MS *
    Math.pow(RETRY_CONFIG.BACKOFF_MULTIPLIER, attempt - 1);
  return Math.min(delay, RETRY_CONFIG.MAX_BACKOFF_MS);
}
