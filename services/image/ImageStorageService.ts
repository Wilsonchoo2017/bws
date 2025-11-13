/**
 * ImageStorageService
 *
 * Responsible for storing images to local filesystem with distributed file locking.
 * Generates unique filenames and manages directory structure.
 *
 * Single Responsibility Principle: Only handles storage, not downloading.
 * Dependency Inversion Principle: Could be swapped with cloud storage implementation.
 *
 * Features:
 * - Distributed file locking to prevent concurrent writes across workers
 * - Content-based filename generation for automatic deduplication
 * - Atomic file operations with Redis coordination
 */

import { ensureDir } from "https://deno.land/std@0.208.0/fs/ensure_dir.ts";
import { join } from "https://deno.land/std@0.208.0/path/join.ts";
import { getFileLockManager } from "../../utils/FileLockManager.ts";

export interface StorageResult {
  relativePath: string; // Path relative to static directory (for DB storage)
  absolutePath: string; // Full filesystem path
  filename: string;
  url: string; // Public URL to access the image
}

export interface StorageOptions {
  baseDir?: string;
  publicPath?: string;
}

export class ImageStorageService {
  private readonly baseDir: string;
  private readonly publicPath: string;

  constructor(options: StorageOptions = {}) {
    this.baseDir = options.baseDir ||
      join(Deno.cwd(), "static", "images", "products");
    this.publicPath = options.publicPath || "/images/products";
  }

  /**
   * Stores an image to the filesystem with distributed file locking
   * @param imageData - Raw image data
   * @param originalUrl - Original URL (used for generating hash-based filename)
   * @param productId - Optional product ID for directory organization
   */
  async store(
    imageData: Uint8Array,
    originalUrl: string,
    extension: string,
    productId?: string,
  ): Promise<StorageResult> {
    // Generate unique filename based on URL hash
    const filename = await this.generateFilename(originalUrl, extension);

    // Determine storage directory
    const storageDir = productId ? join(this.baseDir, productId) : this.baseDir;

    // Full file path
    const absolutePath = join(storageDir, filename);

    // Use file lock to prevent concurrent writes of the same file
    const lockManager = getFileLockManager();
    return await lockManager.withLock(
      absolutePath,
      async () => {
        // Check if file already exists (deduplication)
        // Note: Double-check inside lock to handle race condition
        if (await this.fileExists(absolutePath)) {
          console.log(`Image already exists, skipping: ${filename}`);
          return this.createStorageResult(
            absolutePath,
            storageDir,
            filename,
            productId,
          );
        }

        // Ensure directory exists
        await ensureDir(storageDir);

        // Write file to disk
        await Deno.writeFile(absolutePath, imageData);
        console.log(`Image stored: ${absolutePath}`);

        return this.createStorageResult(
          absolutePath,
          storageDir,
          filename,
          productId,
        );
      },
      {
        timeoutMs: 10000, // Wait up to 10 seconds for lock
        expiryMs: 30000, // Lock expires after 30 seconds
      },
    );
  }

  /**
   * Stores multiple images
   */
  async storeMultiple(
    images: Array<{ data: Uint8Array; url: string; extension: string }>,
    productId?: string,
  ): Promise<StorageResult[]> {
    const results: StorageResult[] = [];

    for (const image of images) {
      try {
        const result = await this.store(
          image.data,
          image.url,
          image.extension,
          productId,
        );
        results.push(result);
      } catch (error) {
        console.error(`Failed to store image ${image.url}:`, error);
        // Continue with other images even if one fails
      }
    }

    return results;
  }

  /**
   * Deletes an image from the filesystem
   */
  async delete(relativePath: string): Promise<void> {
    const absolutePath = join(
      this.baseDir,
      "..",
      relativePath.replace(this.publicPath, ""),
    );

    try {
      await Deno.remove(absolutePath);
      console.log(`Image deleted: ${absolutePath}`);
    } catch (error) {
      if (error instanceof Deno.errors.NotFound) {
        console.warn(`Image not found for deletion: ${absolutePath}`);
      } else {
        throw error;
      }
    }
  }

  /**
   * Checks if a file exists
   */
  private async fileExists(path: string): Promise<boolean> {
    try {
      await Deno.stat(path);
      return true;
    } catch (error) {
      if (error instanceof Deno.errors.NotFound) {
        return false;
      }
      throw error;
    }
  }

  /**
   * Generates a unique filename based on URL hash
   * This ensures the same image URL always generates the same filename (deduplication)
   */
  private async generateFilename(
    url: string,
    extension: string,
  ): Promise<string> {
    // Create hash from URL
    const encoder = new TextEncoder();
    const data = encoder.encode(url);
    const hashBuffer = await crypto.subtle.digest("SHA-256", data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join(
      "",
    );

    // Use first 16 characters of hash for filename
    const shortHash = hashHex.substring(0, 16);

    return `${shortHash}.${extension}`;
  }

  /**
   * Creates a StorageResult object with all path information
   */
  private createStorageResult(
    absolutePath: string,
    storageDir: string,
    filename: string,
    productId?: string,
  ): StorageResult {
    // Calculate relative path from baseDir
    const relativePath = productId
      ? join(this.publicPath, productId, filename)
      : join(this.publicPath, filename);

    // Public URL for accessing the image
    const url = relativePath;

    return {
      relativePath,
      absolutePath,
      filename,
      url,
    };
  }

  /**
   * Gets the absolute path for a relative path
   */
  getAbsolutePath(relativePath: string): string {
    const cleanPath = relativePath.replace(this.publicPath, "");
    return join(this.baseDir, "..", cleanPath);
  }

  /**
   * Gets storage statistics
   */
  async getStats(): Promise<{
    totalImages: number;
    totalSizeBytes: number;
  }> {
    let totalImages = 0;
    let totalSizeBytes = 0;

    try {
      for await (const entry of this.walkDir(this.baseDir)) {
        if (entry.isFile) {
          totalImages++;
          const stat = await Deno.stat(entry.path);
          totalSizeBytes += stat.size;
        }
      }
    } catch (error) {
      console.error("Error calculating storage stats:", error);
    }

    return { totalImages, totalSizeBytes };
  }

  /**
   * Recursively walks a directory
   */
  private async *walkDir(
    dir: string,
  ): AsyncGenerator<{ path: string; isFile: boolean }> {
    try {
      for await (const entry of Deno.readDir(dir)) {
        const path = join(dir, entry.name);
        if (entry.isDirectory) {
          yield* this.walkDir(path);
        } else if (entry.isFile) {
          yield { path, isFile: true };
        }
      }
    } catch (error) {
      if (!(error instanceof Deno.errors.NotFound)) {
        throw error;
      }
    }
  }
}

// Singleton instance
export const imageStorageService = new ImageStorageService();
