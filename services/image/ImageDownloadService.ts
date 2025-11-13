/**
 * ImageDownloadService
 *
 * Responsible for downloading images from URLs.
 * Handles retries, timeouts, and validation.
 *
 * Single Responsibility Principle: Only downloads images, doesn't store them.
 */

export interface ImageData {
  data: Uint8Array;
  contentType: string;
  extension: string;
  url: string;
}

export interface DownloadOptions {
  timeoutMs?: number;
  maxRetries?: number;
  retryDelayMs?: number;
  allowedFormats?: string[];
}

export class ImageDownloadService {
  private readonly defaultOptions: Required<DownloadOptions> = {
    timeoutMs: 30000, // 30 seconds
    maxRetries: 3,
    retryDelayMs: 1000,
    allowedFormats: ["jpg", "jpeg", "png", "webp", "gif"],
  };

  /**
   * Downloads a single image from a URL
   */
  async download(
    url: string,
    options: DownloadOptions = {},
  ): Promise<ImageData> {
    const opts = { ...this.defaultOptions, ...options };
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {
      try {
        if (attempt > 0) {
          // Wait before retry
          await this.delay(opts.retryDelayMs * attempt);
          console.log(`Retrying image download (attempt ${attempt + 1}/${opts.maxRetries + 1}): ${url}`);
        }

        const imageData = await this.downloadWithTimeout(url, opts.timeoutMs);
        this.validateImageData(imageData, opts.allowedFormats);

        return imageData;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        console.error(`Image download attempt ${attempt + 1} failed for ${url}:`, lastError.message);
      }
    }

    throw new Error(
      `Failed to download image after ${opts.maxRetries + 1} attempts: ${lastError?.message || "Unknown error"}`,
    );
  }

  /**
   * Downloads multiple images in parallel with concurrency control
   */
  async downloadMultiple(
    urls: string[],
    options: DownloadOptions = {},
    concurrency: number = 5,
  ): Promise<Array<{ url: string; data: ImageData | null; error: string | null }>> {
    const results: Array<{ url: string; data: ImageData | null; error: string | null }> = [];

    // Process in batches to control concurrency
    for (let i = 0; i < urls.length; i += concurrency) {
      const batch = urls.slice(i, i + concurrency);
      const batchResults = await Promise.all(
        batch.map(async (url) => {
          try {
            const data = await this.download(url, options);
            return { url, data, error: null };
          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            return { url, data: null, error: errorMessage };
          }
        }),
      );
      results.push(...batchResults);
    }

    return results;
  }

  /**
   * Downloads image with timeout
   */
  private async downloadWithTimeout(
    url: string,
    timeoutMs: number,
  ): Promise<ImageData> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
      }

      const contentType = response.headers.get("content-type") || "";
      const arrayBuffer = await response.arrayBuffer();
      const data = new Uint8Array(arrayBuffer);

      const extension = this.getExtensionFromContentType(contentType) ||
        this.getExtensionFromUrl(url);

      return {
        data,
        contentType,
        extension,
        url,
      };
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new Error(`Download timeout after ${timeoutMs}ms`);
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Validates downloaded image data
   */
  private validateImageData(
    imageData: ImageData,
    allowedFormats: string[],
  ): void {
    // Check if content type is an image
    if (!imageData.contentType.startsWith("image/")) {
      throw new Error(`Invalid content type: ${imageData.contentType}`);
    }

    // Check if format is allowed
    if (!allowedFormats.includes(imageData.extension)) {
      throw new Error(
        `Unsupported image format: ${imageData.extension}. Allowed: ${allowedFormats.join(", ")}`,
      );
    }

    // Check if data is not empty
    if (imageData.data.length === 0) {
      throw new Error("Downloaded image data is empty");
    }

    // Basic image signature validation
    this.validateImageSignature(imageData.data, imageData.extension);
  }

  /**
   * Validates image file signature (magic bytes)
   */
  private validateImageSignature(data: Uint8Array, extension: string): void {
    const signatures: Record<string, number[][]> = {
      jpg: [[0xFF, 0xD8, 0xFF]],
      jpeg: [[0xFF, 0xD8, 0xFF]],
      png: [[0x89, 0x50, 0x4E, 0x47]],
      gif: [[0x47, 0x49, 0x46, 0x38]],
      webp: [[0x52, 0x49, 0x46, 0x46]], // RIFF header for WebP
    };

    const expectedSignatures = signatures[extension.toLowerCase()];
    if (!expectedSignatures) {
      return; // Skip validation for unknown formats
    }

    const isValid = expectedSignatures.some((signature) =>
      signature.every((byte, index) => data[index] === byte)
    );

    if (!isValid) {
      throw new Error(
        `Invalid ${extension.toUpperCase()} file signature`,
      );
    }
  }

  /**
   * Extracts file extension from content type
   */
  private getExtensionFromContentType(contentType: string): string {
    const match = contentType.match(/image\/(\w+)/);
    if (!match) return "jpg"; // Default fallback

    const type = match[1].toLowerCase();
    // Normalize extensions
    if (type === "jpeg") return "jpg";
    return type;
  }

  /**
   * Extracts file extension from URL
   */
  private getExtensionFromUrl(url: string): string {
    try {
      const pathname = new URL(url).pathname;
      const match = pathname.match(/\.(\w+)$/);
      if (match) {
        const ext = match[1].toLowerCase();
        if (ext === "jpeg") return "jpg";
        return ext;
      }
    } catch {
      // Invalid URL, use default
    }
    return "jpg"; // Default fallback
  }

  /**
   * Delay helper for retries
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// Singleton instance
export const imageDownloadService = new ImageDownloadService();
