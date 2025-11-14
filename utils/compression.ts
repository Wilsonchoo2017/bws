/**
 * Compression utilities for storing raw HTML/API responses
 * Uses gzip compression to reduce storage size by ~70-90%
 */

import { gunzip, gzip } from "https://deno.land/x/compress@v0.4.6/mod.ts";

/**
 * Compresses HTML string using gzip and encodes as base64 for database storage
 * @param html - Raw HTML string to compress
 * @returns Object with base64-encoded compressed data and size metrics
 */
export function compressHtml(
  html: string,
): {
  compressed: string;
  originalSize: number;
  compressedSize: number;
  compressionRatio: number;
} {
  // Convert string to Uint8Array
  const encoder = new TextEncoder();
  const htmlBytes = encoder.encode(html);
  const originalSize = htmlBytes.length;

  // Compress using gzip
  const compressedBytes = gzip(htmlBytes);
  const compressedSize = compressedBytes.length;

  // Convert to base64 for database storage
  const base64 = btoa(String.fromCharCode(...compressedBytes));

  // Calculate compression ratio
  const compressionRatio = originalSize > 0
    ? (compressedSize / originalSize)
    : 0;

  return {
    compressed: base64,
    originalSize,
    compressedSize,
    compressionRatio,
  };
}

/**
 * Decompresses base64-encoded gzipped data back to original HTML string
 * @param compressed - Base64-encoded gzipped data from database
 * @returns Original HTML string
 */
export function decompressHtml(compressed: string): string {
  // Decode from base64
  const compressedBytes = Uint8Array.from(
    atob(compressed),
    (c) => c.charCodeAt(0),
  );

  // Decompress using gunzip
  const decompressedBytes = gunzip(compressedBytes);

  // Convert back to string
  const decoder = new TextDecoder();
  return decoder.decode(decompressedBytes);
}

/**
 * Calculates compression statistics for analytics
 * @param originalSize - Original size in bytes
 * @param compressedSize - Compressed size in bytes
 * @returns Statistics object with human-readable values
 */
export function getCompressionStats(
  originalSize: number,
  compressedSize: number,
): {
  originalSizeKB: number;
  compressedSizeKB: number;
  savedBytes: number;
  savedKB: number;
  compressionRatio: number;
  compressionPercent: number;
} {
  const savedBytes = originalSize - compressedSize;
  const compressionRatio = originalSize > 0
    ? (compressedSize / originalSize)
    : 0;
  const compressionPercent = originalSize > 0
    ? ((1 - compressionRatio) * 100)
    : 0;

  return {
    originalSizeKB: Math.round(originalSize / 1024 * 100) / 100,
    compressedSizeKB: Math.round(compressedSize / 1024 * 100) / 100,
    savedBytes,
    savedKB: Math.round(savedBytes / 1024 * 100) / 100,
    compressionRatio: Math.round(compressionRatio * 1000) / 1000,
    compressionPercent: Math.round(compressionPercent * 100) / 100,
  };
}
