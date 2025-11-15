/**
 * HttpClientService - Handles HTTP requests with maximum anti-bot protection
 *
 * Responsibilities (Single Responsibility Principle):
 * - Manage browser instances with Puppeteer
 * - Rotate user agents, viewports, and headers
 * - Handle cookies and sessions
 * - Simulate human-like behavior
 * - Provide abstraction for HTTP requests
 *
 * This service follows the Dependency Inversion Principle by depending on
 * abstractions (interfaces) rather than concrete implementations.
 */

import puppeteer, { Browser, HTTPRequest, Page } from "../../lib/puppeteer.ts";
import {
  BROWSER_CONFIG,
  getRandomAcceptLanguage,
  getRandomUserAgent,
  getRandomViewport,
} from "../../config/scraper.config.ts";
import { BricklinkMaintenanceDetector } from "../bricklink/BricklinkMaintenanceDetector.ts";
import { RateLimitError } from "../../types/errors/RateLimitError.ts";
import { rateLimitErrorTracker } from "../../utils/RateLimitErrorTracker.ts";

/**
 * Interface for HTTP request options
 */
export interface HttpRequestOptions {
  url: string;
  waitForSelector?: string;
  timeout?: number;
  javascript?: boolean;
  headers?: Record<string, string>;
  userAgent?: string; // Optional: Use specific user agent instead of random
  referer?: string; // Optional: Set Referer header
}

/**
 * Interface for HTTP response
 */
export interface HttpResponse {
  html: string;
  status: number;
  url: string;
}

/**
 * HttpClientService - Manages browser automation for web scraping
 * with comprehensive anti-bot protection
 */
export class HttpClientService {
  private browser: Browser | null = null;
  private page: Page | null = null;
  private isInitialized = false;
  private initPromise: Promise<void> | null = null;

  /**
   * Initialize the browser instance
   * Thread-safe: Multiple concurrent calls will wait for the same initialization
   */
  initialize(): Promise<void> {
    // If already initialized, return immediately
    if (this.isInitialized) {
      return Promise.resolve();
    }

    // If initialization is in progress, wait for it
    if (this.initPromise) {
      return this.initPromise;
    }

    // Start initialization and store the promise
    this.initPromise = (async () => {
      try {
        this.browser = await puppeteer.launch({
          headless: BROWSER_CONFIG.HEADLESS,
          args: [...BROWSER_CONFIG.ARGS],
        });

        this.isInitialized = true;
        console.log("✅ HttpClientService initialized successfully");
      } catch (error) {
        console.error("❌ Failed to initialize HttpClientService:", error);
        this.initPromise = null; // Reset so initialization can be retried
        throw new Error(`Browser initialization failed: ${error.message}`);
      }
    })();

    return this.initPromise;
  }

  /**
   * Create a new page with anti-detection measures
   */
  private async createPage(): Promise<Page> {
    if (!this.browser) {
      throw new Error("Browser not initialized. Call initialize() first.");
    }

    const page = await this.browser.newPage();

    // Get random configurations for this session
    const userAgent = getRandomUserAgent();
    const viewport = getRandomViewport();
    const acceptLanguage = getRandomAcceptLanguage();

    // Set user agent
    await page.setUserAgent(userAgent);

    // Set viewport
    await page.setViewport(viewport);

    // Set extra HTTP headers
    await page.setExtraHTTPHeaders({
      "Accept-Language": acceptLanguage,
      "Accept":
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
      "Accept-Encoding": "gzip, deflate, br",
      "Connection": "keep-alive",
      "Upgrade-Insecure-Requests": "1",
      "Sec-Fetch-Dest": "document",
      "Sec-Fetch-Mode": "navigate",
      "Sec-Fetch-Site": "none",
      "Sec-Fetch-User": "?1",
      "Cache-Control": "max-age=0",
    });

    // Block images if disabled in config (for faster dev scraping)
    if (!BROWSER_CONFIG.IMAGES_ENABLED) {
      await page.setRequestInterception(true);
      page.on("request", (request: HTTPRequest) => {
        const resourceType = request.resourceType();
        if (
          resourceType === "image" || resourceType === "stylesheet" ||
          resourceType === "font"
        ) {
          request.abort();
        } else {
          request.continue();
        }
      });
      console.log("🚫 Image loading disabled for faster scraping");
    }

    // Remove automation indicators
    await page.evaluateOnNewDocument(() => {
      // Override the navigator.webdriver property
      Object.defineProperty(navigator, "webdriver", {
        get: () => false,
      });

      // Override the navigator.plugins to make it look more real
      Object.defineProperty(navigator, "plugins", {
        get: () => [1, 2, 3, 4, 5],
      });

      // Override the navigator.languages
      Object.defineProperty(navigator, "languages", {
        get: () => ["en-US", "en"],
      });

      // Add chrome object (if Chrome user agent)
      // @ts-ignore: Adding chrome property
      if (!globalThis.chrome) {
        // @ts-ignore: Adding chrome property
        globalThis.chrome = {
          runtime: {},
        };
      }

      // Override permissions API
      // @ts-ignore: Browser-specific API not available in Deno types
      const originalQuery = globalThis.navigator?.permissions?.query;
      // @ts-ignore: Overriding query for anti-bot detection
      if (window.navigator.permissions) {
        // @ts-ignore: Browser permissions API not in Deno types
        window.navigator.permissions.query = (parameters: { name: string }) => (
          parameters.name === "notifications"
            ? Promise.resolve({
              state: "granted",
            })
            : originalQuery
            // @ts-ignore: Type mismatch between browser and Deno types
            ? originalQuery(parameters)
            : Promise.resolve({ state: "granted" })
        );
      }
    });

    console.log(
      `🌐 Created new page with User-Agent: ${userAgent.substring(0, 50)}...`,
    );
    console.log(`📐 Viewport: ${viewport.width}x${viewport.height}`);

    return page;
  }

  /**
   * Simulate human-like behavior with random delays
   */
  private async simulateHumanBehavior(page: Page): Promise<void> {
    // Random mouse movements
    const randomX = Math.floor(Math.random() * 800);
    const randomY = Math.floor(Math.random() * 600);
    await page.mouse.move(randomX, randomY);

    // Small random delay (100-500ms)
    await this.randomDelay(100, 500);

    // Random scroll
    const scrollAmount = Math.floor(Math.random() * 300);
    await page.evaluate((amount) => {
      // @ts-ignore: scrollBy is available in browser context
      globalThis.scrollBy(0, amount);
    }, scrollAmount);

    // Another small delay
    await this.randomDelay(200, 800);
  }

  /**
   * Random delay between min and max milliseconds
   */
  private async randomDelay(min: number, max: number): Promise<void> {
    const delay = Math.floor(Math.random() * (max - min + 1)) + min;
    await new Promise((resolve) => setTimeout(resolve, delay));
  }

  /**
   * Extract domain from URL for rate limit tracking
   */
  private extractDomain(url: string): string {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname;
    } catch {
      return "unknown";
    }
  }

  /**
   * Handle 403 Forbidden response by tracking and throwing RateLimitError
   */
  private async handle403Error(url: string, status: number): Promise<void> {
    if (status === 403) {
      const domain = this.extractDomain(url);
      const consecutive403Count = await rateLimitErrorTracker.increment(domain);
      const delayMs = rateLimitErrorTracker.calculateDelay(consecutive403Count);

      throw new RateLimitError(
        `Rate limit detected (403 Forbidden) for ${domain}. This is consecutive 403 #${consecutive403Count}.`,
        domain,
        consecutive403Count,
        delayMs,
      );
    }
  }

  /**
   * Reset 403 counter on successful request
   */
  private async resetRateLimitCounter(url: string): Promise<void> {
    const domain = this.extractDomain(url);
    await rateLimitErrorTracker.reset(domain);
  }

  /**
   * Fetch a URL with full anti-bot protection
   */
  async fetch(options: HttpRequestOptions): Promise<HttpResponse> {
    if (!this.isInitialized) {
      await this.initialize();
    }

    let page: Page | null = null;

    try {
      // Create a new page for this request
      page = await this.createPage();

      // Set custom timeout if provided
      const timeout = options.timeout || BROWSER_CONFIG.NAVIGATION_TIMEOUT;
      page.setDefaultNavigationTimeout(timeout);
      page.setDefaultTimeout(timeout);

      // Navigate to the URL
      console.log(`🔗 Navigating to: ${options.url}`);
      const response = await page.goto(options.url, {
        waitUntil: "networkidle2",
        timeout,
      });

      if (!response) {
        throw new Error("No response received from page.goto()");
      }

      // Simulate human behavior
      await this.simulateHumanBehavior(page);

      // Wait for specific selector if provided
      if (options.waitForSelector) {
        console.log(`⏳ Waiting for selector: ${options.waitForSelector}`);
        await page.waitForSelector(options.waitForSelector, { timeout });
      }

      // Additional random delay before extracting content
      await this.randomDelay(500, 1500);

      // Get the page HTML
      const html = await page.content();
      const status = response.status();
      const finalUrl = page.url();

      // Check for 403 Forbidden (rate limiting)
      await this.handle403Error(finalUrl, status);

      // Check for Bricklink maintenance page (only for bricklink.com domains)
      if (finalUrl.includes("bricklink.com")) {
        BricklinkMaintenanceDetector.checkAndThrow(html);
      }

      // Reset 403 counter on successful request
      await this.resetRateLimitCounter(finalUrl);

      console.log(`✅ Successfully fetched: ${finalUrl} (Status: ${status})`);

      return {
        html,
        status,
        url: finalUrl,
      };
    } catch (error) {
      console.error(`❌ Failed to fetch ${options.url}:`, error);
      // Re-throw special errors as-is, don't wrap them
      if (error.name === "MaintenanceError" || error.isMaintenanceError) {
        throw error;
      }
      if (error.name === "RateLimitError" || error.isRateLimitError) {
        throw error;
      }
      throw new Error(
        `HTTP request failed: ${error.message}`,
      );
    } finally {
      // Always close the page to free resources
      if (page) {
        await page.close();
      }
    }
  }

  /**
   * Fetch multiple URLs sequentially with delays
   */
  async fetchMultiple(
    urls: string[],
    delayBetweenRequests: number = 2000,
  ): Promise<HttpResponse[]> {
    const results: HttpResponse[] = [];

    for (const url of urls) {
      try {
        const response = await this.fetch({ url });
        results.push(response);

        // Add delay between requests if not the last one
        if (url !== urls[urls.length - 1]) {
          console.log(
            `⏳ Waiting ${delayBetweenRequests}ms before next request...`,
          );
          await new Promise((resolve) =>
            setTimeout(resolve, delayBetweenRequests)
          );
        }
      } catch (error) {
        console.error(`Failed to fetch ${url}:`, error);
        // Continue with next URL even if one fails
      }
    }

    return results;
  }

  /**
   * Simple HTTP fetch without browser automation (for sites that block Puppeteer)
   * Uses native fetch with browser-like headers
   */
  async simpleFetch(options: HttpRequestOptions): Promise<HttpResponse> {
    const userAgent = options.userAgent || getRandomUserAgent();
    const acceptLanguage = getRandomAcceptLanguage();

    try {
      console.log(`🌐 Simple fetch (no browser): ${options.url}`);

      // Build headers with optional Referer and custom Sec-Fetch-Site
      const headers: Record<string, string> = {
        "User-Agent": userAgent,
        "Accept":
          "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": acceptLanguage,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": options.referer ? "same-origin" : "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
      };

      // Add Referer if provided
      if (options.referer) {
        headers["Referer"] = options.referer;
      }

      // Merge with custom headers if provided
      if (options.headers) {
        Object.assign(headers, options.headers);
      }

      const response = await fetch(options.url, {
        headers,
        redirect: "follow",
      });

      const status = response.status;
      const finalUrl = response.url;

      // Check for 403 Forbidden (rate limiting)
      await this.handle403Error(finalUrl, status);

      if (!response.ok && status !== 200) {
        throw new Error(`HTTP ${status}: ${response.statusText}`);
      }

      const html = await response.text();

      // Reset 403 counter on successful request
      await this.resetRateLimitCounter(finalUrl);

      console.log(
        `✅ Successfully fetched (simple): ${finalUrl} (Status: ${status})`,
      );

      return {
        html,
        status,
        url: finalUrl,
      };
    } catch (error) {
      console.error(`❌ Simple fetch failed for ${options.url}:`, error);
      // Re-throw RateLimitError as-is, don't wrap it
      if (error.name === "RateLimitError" || error.isRateLimitError) {
        throw error;
      }
      throw new Error(`HTTP request failed: ${error.message}`);
    }
  }

  /**
   * Close the browser instance
   */
  async close(): Promise<void> {
    if (this.page) {
      await this.page.close();
      this.page = null;
    }

    if (this.browser) {
      await this.browser.close();
      this.browser = null;
    }

    this.isInitialized = false;
    console.log("🔒 HttpClientService closed");
  }

  /**
   * Check if the service is initialized
   */
  isReady(): boolean {
    return this.isInitialized;
  }

  /**
   * Get browser info (for debugging)
   */
  async getBrowserInfo(): Promise<
    {
      version: string;
      userAgent: string;
    } | null
  > {
    if (!this.browser) {
      return null;
    }

    const version = await this.browser.version();
    const page = await this.createPage();
    const userAgent = await page.evaluate(() => navigator.userAgent);
    await page.close();

    return {
      version,
      userAgent,
    };
  }
}

/**
 * Singleton instance for reuse across the application
 * This follows the Dependency Injection principle - consumers can use
 * the singleton or create their own instance for testing
 */
let httpClientInstance: HttpClientService | null = null;

/**
 * Get the singleton HttpClientService instance
 */
export function getHttpClient(): HttpClientService {
  if (!httpClientInstance) {
    httpClientInstance = new HttpClientService();
  }
  return httpClientInstance;
}

/**
 * Close the singleton instance (useful for cleanup)
 */
export async function closeHttpClient(): Promise<void> {
  if (httpClientInstance) {
    await httpClientInstance.close();
    httpClientInstance = null;
  }
}
